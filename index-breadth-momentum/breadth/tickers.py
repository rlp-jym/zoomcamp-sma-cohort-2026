"""CUSIP/name -> ticker for the holdings store.

2019+ filings carry a CUSIP, so those map exactly (OpenFIGI, free, no key).
Older filings only have a name, so they borrow the CUSIP of the same company in a
later filing. The mapping is cached in config/tickers.csv, which is committed, so
later runs do not call the API.

    uv run python -m breadth.tickers

Prints ticker coverage (by count and by weight) for every period.
"""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

from breadth import edgar

API = "https://api.openfigi.com/v3/mapping"
SEC_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE = Path(__file__).resolve().parents[1] / "config" / "tickers.csv"
SEC_CACHE = CACHE.parent / "sec_tickers.csv"
SUFFIX = r"\b(inc|corp|corporation|co|company|cos|ltd|plc|holdings|group|the|class [abc]|com|new|del|sa|nv|ag)\b"


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _openfigi(cusips: list[str]) -> pd.DataFrame:
    cache = pd.read_csv(CACHE, dtype=str) if CACHE.exists() else pd.DataFrame(columns=["cusip", "ticker", "name"])
    seen = set(cache["cusip"])
    todo = [c for c in cusips if c not in seen]
    print(f"{len(todo)} new CUSIPs to resolve ({len(cache)} cached)")

    rows = []
    for i in range(0, len(todo), 10):
        batch = todo[i : i + 10]
        for attempt in range(5):
            r = requests.post(API, json=[{"idType": "ID_CUSIP", "idValue": c} for c in batch], timeout=60)
            if r.status_code == 200:
                break
            time.sleep(10 * (attempt + 1))  # 25 req/min without a key
        r.raise_for_status()
        for cusip, result in zip(batch, r.json()):
            data = result.get("data") or []
            us = [d for d in data if str(d.get("exchCode", "")).startswith("U")]  # US venues
            pick = next((d for d in us if d.get("securityType") == "Common Stock"), us[0] if us else None)
            ticker = pick["ticker"] if pick else ""
            if not re.fullmatch(r"[A-Z]{1,5}([.\-][A-Z]{1,2})?", ticker):
                ticker = ""  # foreign listing or a non-equity identifier
            rows.append({"cusip": cusip, "ticker": ticker, "name": pick["name"] if ticker else ""})
        if i % 100 == 0:
            print(f"  {i + len(batch)}/{len(todo)}")
        time.sleep(2.5)

    out = pd.concat([cache, pd.DataFrame(rows)], ignore_index=True)
    out = out.drop_duplicates("cusip", keep="last")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE, index=False)
    return out[out["ticker"].notna() & (out["ticker"] != "")]


def _sec_tickers() -> dict[str, str]:
    """Name -> ticker from the SEC's own list of listed companies."""
    if SEC_CACHE.exists():
        d = pd.read_csv(SEC_CACHE, dtype=str)
    else:
        raw = requests.get(SEC_URL, headers={"User-Agent": edgar.UA}, timeout=90).json()
        d = pd.DataFrame(raw.values())[["ticker", "title"]]
        d["n"] = d["title"].map(norm_name)
        d = d.drop_duplicates("n")
        SEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
        d.to_csv(SEC_CACHE, index=False)
    return _keyed(zip(d["title"], d["ticker"]))


def _rank(ticker: str) -> tuple:
    """Prefer the plainest symbol: no suffix, then shortest, then alphabetical.

    The SEC list carries several instruments per company (PCG and PCG-PE), so a naive
    dict overwrite picks whichever row came last.
    """
    return (bool(re.search(r"[-.]", ticker)), len(ticker), ticker)


def _keyed(pairs) -> dict[str, str]:
    """Name -> ticker, keyed with and without spaces ('ExxonMobil' vs 'Exxon Mobil')."""
    out: dict[str, str] = {}
    for name, ticker in pairs:
        n = norm_name(name)
        if not n:
            continue
        for key in (n, n.replace(" ", "")):
            if key not in out or _rank(ticker) < _rank(out[key]):
                out[key] = ticker
    return out


def _lookup(name: str, table: dict[str, str]) -> str | None:
    n = norm_name(name)
    return table.get(n) or table.get(n.replace(" ", ""))


def map_tickers(df: pd.DataFrame) -> pd.DataFrame:
    """Fill df['ticker'] from CUSIP, then company name, then the SEC name list."""
    df = df.copy()
    df["cusip"] = df["cusip"].replace({"000000000": None})  # foreign issuers report a dummy

    known = _openfigi(sorted(df["cusip"].dropna().unique()))
    by_cusip = dict(zip(known["cusip"], known["ticker"]))

    # name -> ticker, learned from rows whose CUSIP resolved (covers share classes)
    learns = df[df["cusip"].map(by_cusip).notna()].copy()
    learns["n"] = learns["name"].map(norm_name)
    best = learns.sort_values("index_weight").drop_duplicates("n", keep="last")
    by_name = _keyed(zip(best["name"], best["cusip"].map(by_cusip)))

    df["ticker"] = df["cusip"].map(by_cusip)
    df["ticker_source"] = None
    df.loc[df["ticker"].notna(), "ticker_source"] = "cusip"

    by_name_ticker = df["name"].map(lambda n: _lookup(n, by_name))
    df["ticker"] = df["ticker"].fillna(by_name_ticker)
    df.loc[df["ticker_source"].isna() & by_name_ticker.notna(), "ticker_source"] = "name"

    sec = _sec_tickers()
    by_sec = df["name"].map(lambda n: _lookup(n, sec))
    df["ticker"] = df["ticker"].fillna(by_sec)
    df.loc[df["ticker_source"].isna() & by_sec.notna(), "ticker_source"] = "sec"

    # a preferred line (PCG-PE) resolves to the parent common stock when it exists
    plain = {str(t) for t in sec.values() if isinstance(t, str) and t.isalpha() and len(t) <= 5}

    def root(ticker):
        if isinstance(ticker, str) and "-" in ticker:
            base = ticker.split("-")[0]
            if base in plain:
                return base
        return ticker

    df["ticker"] = df["ticker"].map(root)
    return df


def main() -> None:
    df = map_tickers(edgar.load())
    df["resolved"] = df["ticker"].notna()
    df["w"] = df["index_weight"].where(df["resolved"], 0)
    report = df.groupby("period").agg(rows=("name", "size"), by_count=("resolved", "mean"), by_weight=("w", "sum"))
    report["by_count"] = (100 * report["by_count"]).round(0)
    report["by_weight"] = report["by_weight"].round(1)
    print(f"\n{CACHE} -> {df['ticker'].nunique()} tickers")
    print(report.tail(16).to_string())
    unresolved = df.loc[~df["resolved"], "name"].value_counts()
    print(f"\n{len(unresolved)} unresolved names, top 10:\n{unresolved.head(10).to_string()}")


if __name__ == "__main__":
    main()
