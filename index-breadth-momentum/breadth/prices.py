"""Daily bars for every resolved holding, plus SPY.

One parquet per symbol, so a rerun only touches what is missing or stale.

    uv run python -m breadth.prices

Output: data/prices/{ticker}.parquet
    date, open, high, low, close, adj_close, volume
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd
import yfinance as yf

from breadth import edgar
from breadth.tickers import map_tickers

DIR = Path(__file__).resolve().parents[1] / "data" / "prices"
SPLITS = Path(__file__).resolve().parents[1] / "data" / "splits.parquet"
START = "2014-06-01"  # 200-day MA must be warm by the 2016 cutoff
CHUNK = 40


def update_splits(tickers: list[str]) -> None:
    """Split factors per ticker, needed to compare reported prices with Yahoo closes."""
    frames = []
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i : i + CHUNK]
        data = yf.download(chunk, period="max", group_by="ticker", auto_adjust=False,
                           actions=True, progress=False, threads=True)
        for t in chunk:
            try:
                sub = data[t]
            except KeyError:
                continue
            if "Stock Splits" not in sub:
                continue
            s = sub["Stock Splits"]
            s = s[s > 0]
            if len(s):
                frames.append(pd.DataFrame({"ticker": t, "date": s.index, "ratio": s.values}))
    if frames:
        pd.concat(frames, ignore_index=True).to_parquet(SPLITS, index=False)
        print(f"splits -> {SPLITS}")


def symbols() -> list[str]:
    df = map_tickers(edgar.load())
    tickers = sorted(df["ticker"].dropna().unique())
    return ["SPY", *tickers]


def _stale(path: Path, end: str) -> bool:
    if not path.exists():
        return True
    last = pd.read_parquet(path, columns=["date"])["date"].max()
    return last < pd.Timestamp(end) - pd.Timedelta(days=4)


def last_dates(prices_dir: Path = DIR) -> pd.Series:
    """Latest date with a price, per ticker."""
    out = {}
    for path in prices_dir.glob("*.parquet"):
        dates = pd.read_parquet(path, columns=["date"])["date"]
        if len(dates):
            out[path.stem] = pd.to_datetime(dates).max()
    return pd.Series(out, dtype="datetime64[ns]").sort_values()


def _calendar(prices_dir: Path, asof: pd.Timestamp) -> pd.DatetimeIndex:
    """Trading days, taken from SPY; falls back to business days if SPY is missing."""
    spy = prices_dir / "SPY.parquet"
    if spy.exists():
        dates = pd.to_datetime(pd.read_parquet(spy, columns=["date"])["date"])
        return pd.DatetimeIndex(sorted(d for d in dates.unique() if d <= asof))
    return pd.bdate_range(end=asof, periods=260)


def stale(asof: str | None = None, max_age: int = 5, prices_dir: Path = DIR) -> list[str]:
    """Tickers whose last price is more than `max_age` trading days before `asof`.

    A delisted name keeps its last row forever, so without this check it would sit in the
    panel at a frozen price. Call it whenever the panel is built (B4).
    """
    asof = pd.Timestamp(asof or dt.date.today())
    cal = _calendar(prices_dir, asof)
    last = last_dates(prices_dir)
    if last.empty or not len(cal):
        return []
    # how many trading days exist after each ticker's last price
    pos = cal.searchsorted(last.to_numpy(), side="right")
    remaining = len(cal) - pos
    return sorted(last.index[remaining > max_age])


def odd_tickers(prices_dir: Path = DIR, max_gap: int = 10) -> dict[str, str]:
    """Symbols that are not a clean common-stock series, with the reason.

    Preferred shares, warrants and units look like tickers but are different instruments
    (`PCG-PE` is a preferred, not PG&E common). Gaps and zero prices are usually a fetch
    problem or a halted/delisted line. Run this before trusting a price file (B5).
    """
    plain = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
    found: dict[str, str] = {}
    for path in prices_dir.glob("*.parquet"):
        ticker = path.stem
        if not plain.fullmatch(ticker):
            found[ticker] = "not_common_stock"
            continue
        d = pd.read_parquet(path, columns=["date", "close"])
        if d["close"].isna().any():
            found[ticker] = "missing_close"
            continue
        if (d["close"] <= 0).any():
            found[ticker] = "non_positive_close"
            continue
        dates = pd.to_datetime(d["date"]).sort_values()
        if dates.duplicated().any():
            found[ticker] = "duplicate_dates"
            continue
        gap = dates.diff().dt.days.max()
        if pd.notna(gap) and gap > max_gap:
            found[ticker] = f"gap_{int(gap)}d"
    return dict(sorted(found.items()))


def clean(asof: str | None = None, prices_dir: Path = DIR, max_age: int = 5) -> list[str]:
    """Tickers a panel may use on `asof`: plain instrument, clean series, still trading."""
    unusable = set(odd_tickers(prices_dir)) | set(stale(asof, max_age, prices_dir))
    return sorted(p.stem for p in prices_dir.glob("*.parquet") if p.stem not in unusable)


def _save(ticker: str, data: pd.DataFrame) -> bool:
    data = data.rename(
        columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close",
                 "Adj Close": "adj_close", "Volume": "volume"}
    ).dropna(subset=["close"])
    if data.empty:
        return False
    data.rename_axis("date").reset_index().to_parquet(DIR / f"{ticker}.parquet", index=False)
    return True


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    end = dt.date.today().isoformat()
    wanted = symbols()
    todo = [t for t in wanted if _stale(DIR / f"{t}.parquet", end)]
    print(f"{len(wanted)} symbols, {len(todo)} to fetch")

    ok, failed = 0, []
    for i in range(0, len(todo), CHUNK):
        chunk = todo[i : i + CHUNK]
        data = yf.download(chunk, start=START, end=end, group_by="ticker", auto_adjust=False,
                           actions=False, progress=False, threads=True)
        for t in chunk:
            try:
                sub = data[t] if len(chunk) > 1 else data
                if _save(t, sub):
                    ok += 1
                else:
                    failed.append(t)
            except KeyError:
                failed.append(t)
        print(f"  {min(i + CHUNK, len(todo))}/{len(todo)}  saved={ok} failed={len(failed)}")

    files = list(DIR.glob("*.parquet"))
    print(f"\n{len(files)} symbol files in {DIR}")
    if failed:
        print(f"no data ({len(failed)}): {', '.join(failed[:20])}")
    update_splits(sorted({p.stem for p in files}))

    behind = stale(end)
    print(f"stale as of {end} (>5 trading days behind): {len(behind)}"
          + (f" - {', '.join(behind[:10])}" if behind else ""))
    odd = odd_tickers()
    print(f"not common stock / dirty series: {len(odd)}"
          + (f" - {', '.join(f'{k} ({v})' for k, v in list(odd.items())[:10])}" if odd else ""))


if __name__ == "__main__":
    main()
