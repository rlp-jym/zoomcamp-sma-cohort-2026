"""Data access: cached constituent table, refreshed daily bars, SPY benchmark."""

import time

import pandas as pd
import yfinance as yf

from . import config

CONSTITUENTS = config.LOCAL / "constituents.parquet"
SPY_FILE = config.LOCAL / "spy.parquet"
PRICE_FILE = config.LOCAL / "prices.parquet"

PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
PRICE_FIELDS = ["open", "high", "low", "close", "adj_close", "volume"]


def load_base(refresh: bool = False) -> pd.DataFrame:
    """The release constituent table, cached locally so the cron does not re-download it."""
    if CONSTITUENTS.exists() and not refresh:
        return pd.read_parquet(CONSTITUENTS)
    print("downloading constituent table ...")
    df = pd.read_parquet(config.CONSTITUENTS_URL)
    df.to_parquet(CONSTITUENTS, index=False)
    return df


def load_spy(refresh: bool = False) -> pd.DataFrame:
    if SPY_FILE.exists() and not refresh:
        return pd.read_parquet(SPY_FILE)
    print("downloading SPY ...")
    df = pd.read_parquet(config.SPY_URL)
    df.to_parquet(SPY_FILE, index=False)
    return df


def universe(base: pd.DataFrame) -> tuple[pd.Timestamp, pd.DataFrame]:
    """Tickers and weights as of the last filing snapshot."""
    last = pd.to_datetime(base["date"]).max()
    snap = base.loc[pd.to_datetime(base["date"]) == last,
                    ["issuer_id", "ticker", "index_weight", "name"]]
    snap = snap[snap["ticker"].notna()].drop_duplicates(subset="ticker").copy()
    return last, snap


def _chunks(items, size=40):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def download_prices(tickers, lookback_days: int = 420) -> pd.DataFrame:
    """Daily bars for the ticker list, long format. Empty frame on total failure."""
    tickers = sorted({t for t in tickers if isinstance(t, str) and t})
    if not tickers:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    end = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=lookback_days)
    frames = []

    for chunk in _chunks(tickers):
        try:
            raw = yf.download(list(chunk), start=start, end=end, group_by="ticker",
                              auto_adjust=False, progress=False, threads=True)
        except Exception as exc:  # rate limits, delisted tickers, network
            print(f"  download failed for {len(chunk)} tickers: {exc}")
            time.sleep(2)
            continue
        if raw.empty:
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in chunk:
                if ticker not in raw.columns.get_level_values(0):
                    continue
                part = raw[ticker].dropna(subset=["Close"]).reset_index()
                if part.empty:
                    continue
                part["ticker"] = ticker
                frames.append(part)
        else:
            part = raw.dropna(subset=["Close"]).reset_index()
            part["ticker"] = chunk[0]
            frames.append(part)

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    out = pd.concat(frames, ignore_index=True)
    out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
    for col in PRICE_COLUMNS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[PRICE_COLUMNS]


def extend_base(base: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Overwrite recent prices and append sessions after the last filing date."""
    base = base.copy()
    base["date"] = pd.to_datetime(base["date"])
    last_date, snap = universe(base)

    fresh = prices.copy()
    if fresh.empty:
        return base
    fresh["date"] = pd.to_datetime(fresh["date"])
    fresh = fresh.drop_duplicates(subset=["date", "ticker"], keep="last")

    # 1. refresh prices the base already has (merge handles NaN tickers safely)
    recent = fresh.loc[fresh["date"] <= last_date,
                       ["date", "ticker"] + [c for c in PRICE_FIELDS if c in fresh.columns]]
    if not recent.empty:
        base = base.merge(recent, on=["date", "ticker"], how="left", suffixes=("", "_new"))
        for col in PRICE_FIELDS:
            new = f"{col}_new"
            if new not in base.columns:
                continue
            base[col] = base[new].where(base[new].notna(), base[col])
            base = base.drop(columns=new)

    # 2. append new sessions using the last snapshot's weights
    new_dates = sorted(d for d in fresh["date"].unique() if d > last_date)
    if not new_dates:
        return base.sort_values(["date", "issuer_id"]).reset_index(drop=True)

    rows_by_date = {d: fresh[fresh["date"] == d].set_index("ticker") for d in new_dates}
    new_rows = []
    for date, day in rows_by_date.items():
        rows = snap.copy()
        rows["date"] = date
        for col in PRICE_FIELDS:
            rows[col] = rows["ticker"].map(day[col]) if col in day.columns else float("nan")
        new_rows.append(rows.dropna(subset=["close"]))

    added = pd.concat(new_rows, ignore_index=True)
    for col in base.columns:
        if col not in added.columns:
            added[col] = float("nan")
    added = added[base.columns]

    out = pd.concat([base, added], ignore_index=True)
    return out.sort_values(["date", "issuer_id"]).reset_index(drop=True)


def save_snapshot(base: pd.DataFrame, prices: pd.DataFrame, spy: pd.DataFrame | None = None) -> None:
    base.to_parquet(CONSTITUENTS, index=False)
    if not prices.empty:
        prices.to_parquet(PRICE_FILE, index=False)
    if spy is not None and not spy.empty:
        spy.to_parquet(SPY_FILE, index=False)
