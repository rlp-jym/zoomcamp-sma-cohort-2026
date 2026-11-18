"""SPY holdings from SEC EDGAR.

Two sources, one output:

* N-30D (semi-annual report, 1996-2019) - holdings table is HTML or fixed-width text
* N-PORT (quarterly, 2019-)            - holdings are XML

Nothing is cached except the final parquet: fetch -> parse -> one row per holding.

    uv run python -m breadth.edgar

Output: project_1/data/holdings.parquet
    period        fiscal date the holdings describe
    available_at  filing date (public date) - use this for point-in-time joins
    form, accession
    name, ticker, cusip, shares, holding_value, index_weight
"""

from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from lxml import etree, html as lxml_html

CIK = "0000884394"  # SPDR S&P 500 ETF Trust
UA = "Mozilla/5.0 (research; ralph@example.com)"
FORMS = {"N-30D", "N-CSR", "NPORT-P"}
RANK = {"N-30D": 0, "N-CSR": 1, "NPORT-P": 2}  # ties on period: keep the better source
DIR = Path(__file__).resolve().parents[1] / "data" / "holdings"
MANIFEST = DIR / "_accessions.txt"  # filings already fetched, incl. ones superseded by a better source

HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
SUBMISSIONS = f"https://data.sec.gov/submissions/CIK{CIK}.json"
ARCHIVES = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}"

CASH = re.compile(r"navigator|money market|short.term|repurchase|cash|affiliated", re.I)
HEADER = re.compile(r"shares|value|schedule|continued|total|^\s*[*<(]|^[-\s=<>/]+$", re.I)
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"


def _get(session: requests.Session, url: str) -> bytes:
    for attempt in range(3):
        r = session.get(url, timeout=90)
        if r.status_code == 200:
            time.sleep(0.15)  # SEC allows 10 req/s; stay well under
            return r.content
        time.sleep(1 + attempt)
    r.raise_for_status()
    return b""


def filings(session: requests.Session) -> list[dict]:
    recent = session.get(SUBMISSIONS, timeout=90).json()["filings"]["recent"]
    out = [
        {
            "form": form,
            "available_at": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "doc": recent["primaryDocument"][i],
        }
        for i, form in enumerate(recent["form"])
        if form in FORMS
    ]
    return sorted(out, key=lambda f: f["available_at"])


def _doc_url(session: requests.Session, item: dict) -> str:
    """Older filings have no primaryDocument, so pick the largest file in the index."""
    acc = item["accession"].replace("-", "")
    if item["doc"]:
        return f"{ARCHIVES}/{acc}/{item['doc'].split('/')[-1]}"
    index = session.get(f"{ARCHIVES}/{acc}/index.json", timeout=90).json()
    files = [f for f in index["directory"]["item"] if f["name"].lower().endswith((".txt", ".htm"))]
    files = [f for f in files if "index" not in f["name"].lower()]
    best = max(files, key=lambda f: int(f["size"] or 0))
    return f"{ARCHIVES}/{acc}/{best['name']}"


def _num(text: str) -> int | None:
    t = str(text).replace(",", "").replace("$", "").replace("\xa0", "").strip()
    return int(t) if t.isdigit() else None


def _name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\s*\([a-z]\)\s*$", "", text)  # footnote "(a) affiliated issuer"
    return re.sub(r"\s+", " ", text).strip(" .*")


def _period(text: str, fallback: str) -> str:
    """Fiscal date printed above the schedule, else filing date minus ~90 days."""
    i = text.upper().find("SCHEDULE OF INVESTMENTS")
    window = text[i : i + 600] if i >= 0 else text[:600]
    m = re.search(rf"({MONTHS})\s+(\d{{1,2}}),?\s*(\d{{4}})", window, re.I)
    if m:
        try:
            return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date().isoformat()
        except ValueError:
            pass
    return (dt.date.fromisoformat(fallback) - dt.timedelta(days=90)).isoformat()


def _record(
    meta: dict,
    period: str,
    name: str,
    shares: int,
    holding_value: int,
    asset_cat: str | None = None,
    payoff_profile: str | None = None,
    check_price: bool = True,
) -> dict | None:
    name = _name(name)
    if len(name) < 4 or CASH.search(name) or name.lower().startswith("total"):
        return None
    if shares <= 0:
        return None
    # sanity: a common share's implied price is between 50c and $50k. Derivatives and
    # other instruments are not priced per share, so they skip this and are filtered later.
    if check_price and not (0.5 <= holding_value / shares <= 50_000):
        return None
    return {
        **meta,
        "period": period,
        "name": name,
        "ticker": None,
        "cusip": None,
        "shares": shares,
        "holding_value": holding_value,
        "asset_cat": asset_cat,
        "payoff_profile": payoff_profile,
    }


def parse_text(raw: bytes, meta: dict) -> list[dict]:
    """1996-2009: 'NAME .......... SHARES $ VALUE', names may wrap onto the next line."""
    text = raw.decode("utf-8", "replace")
    period = _period(text, meta["available_at"])
    row = re.compile(r"^(?P<name>.*?)\s*(?:\.\s*){3,}\s*(?P<shares>[\d,]+)\s+\$?\s*(?P<pval>[\d,]+)$")
    out: list[dict] = []
    pending = ""
    for line in text.splitlines():
        s = line.strip()
        m = row.match(s)
        if m:
            rec = _record(
                meta,
                period,
                f"{pending} {m['name']}",
                int(m["shares"].replace(",", "")),
                int(m["pval"].replace(",", "")),
            )
            pending = ""
            if rec:
                out.append(rec)
        elif not s or re.search(r"\d", s) or HEADER.search(s) or len(pending) > 80:
            pending = ""
        else:
            pending = f"{pending} {s}".strip()  # wrapped company name
    return out


def parse_html(raw: bytes, meta: dict) -> list[dict]:
    """2009+: holdings sit in side-by-side tables headed 'Common Stocks ... Shares ... Value'."""
    doc = lxml_html.fromstring(raw)
    period = _period(doc.text_content(), meta["available_at"])
    out: list[dict] = []
    for table in doc.xpath("//table"):
        head = table.text_content()[:600].lower()
        if "common stock" not in head or "share" not in head:
            continue
        for tr in table.xpath(".//tr"):
            cells = [c.text_content() for c in tr.xpath("./td|./th")]
            nums = [n for n in (_num(c) for c in cells) if n is not None]
            if len(nums) < 2:
                continue
            name = next((c.strip() for c in cells if c.strip() and _num(c) is None), "")
            rec = _record(meta, period, name, nums[-2], nums[-1])
            if rec:
                out.append(rec)
    return out


def parse_nport(raw: bytes, meta: dict) -> list[dict]:
    root = etree.fromstring(raw)
    period = root.findtext(".//{*}repPdDate") or meta["available_at"]
    out = []
    for sec in root.iter("{*}invstOrSec"):

        def field(tag: str) -> str:
            return (sec.findtext(f"{{*}}{tag}") or "").strip()

        asset_cat = field("assetCat") or None
        rec = _record(
            meta,
            period,
            field("name"),
            int(float(field("balance") or 0)),
            int(float(field("valUSD") or 0)),
            asset_cat=asset_cat,
            payoff_profile=field("payoffProfile") or None,
            check_price=asset_cat in (None, "EC"),
        )
        if rec:
            ticker = sec.find(".//{*}ticker")  # not always present; cusip is the reliable key
            rec["ticker"] = ticker.get("value") if ticker is not None else None
            cusip = field("cusip")
            rec["cusip"] = None if cusip in ("", "000000000") else cusip  # dummy for foreign issuers
            out.append(rec)
    return out


def parse(raw: bytes, meta: dict) -> list[dict]:
    if meta["form"] == "NPORT-P":
        return parse_nport(raw, meta)
    if b"</td>" in raw.lower():
        return parse_html(raw, meta)
    return parse_text(raw, meta)


def collect() -> pd.DataFrame:
    """Fetch filings that are not in the store yet and write one file per period."""
    session = requests.Session()
    session.headers.update(HEADERS)

    done = set(MANIFEST.read_text(encoding="utf-8").split()) if MANIFEST.exists() else set()
    items = [f for f in filings(session) if f["accession"] not in done]
    print(f"{len(items)} new filings ({len(done)} already stored)")
    if not items:
        return pd.DataFrame()

    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        parsed = parse(_get(session, _doc_url(session, item)), item)
        print(f"{i:3d}/{len(items)} {item['available_at']} {item['form']:8s} {len(parsed):4d} rows")
        rows += parsed

    DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(f["accession"] for f in items) + "\n")

    df = pd.DataFrame(rows)
    # same fiscal period reported twice (e.g. N-30D + N-PORT): keep the better source
    df["_rank"] = df["form"].map(RANK)
    df = df[df["_rank"] == df.groupby("period")["_rank"].transform("max")]
    df = df.drop(columns=["_rank", "doc"])
    df["index_weight"] = df["holding_value"] / df.groupby("period")["holding_value"].transform("sum") * 100
    return df.sort_values(["period", "holding_value"], ascending=[True, False]).reset_index(drop=True)


def store(df: pd.DataFrame) -> None:
    """Append-only: one parquet per period, never rewritten."""
    DIR.mkdir(parents=True, exist_ok=True)
    for period, group in df.groupby("period"):
        path = DIR / f"period={period}.parquet"
        if path.exists():
            print(f"  {period} already stored, skipped")
            continue
        group.to_parquet(path, index=False)


def load() -> pd.DataFrame:
    """Read the store; if a period was refiled, keep the better/later source."""
    best: dict[str, tuple[tuple[int, str], pd.DataFrame]] = {}
    for path in sorted(DIR.glob("period=*.parquet")):
        d = pd.read_parquet(path)
        period = d["period"].iloc[0]
        key = (RANK[d["form"].iloc[0]], d["available_at"].iloc[0])
        if period not in best or key > best[period][0]:
            best[period] = (key, d)
    if not best:
        return pd.DataFrame()
    df = pd.concat([d for _, d in best.values()], ignore_index=True)
    return df.sort_values(["period", "holding_value"], ascending=[True, False]).reset_index(drop=True)


def main() -> None:
    df = collect()
    if not df.empty:
        store(df)
    holdings = load()
    print(f"\n{len(holdings):,} rows in {DIR} ({holdings.period.nunique()} periods)")
    print(holdings.groupby("period").size().tail(5).to_string())


if __name__ == "__main__":
    main()
