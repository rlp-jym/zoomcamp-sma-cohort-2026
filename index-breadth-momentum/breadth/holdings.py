"""Derived holdings layer: the same rows with ticker, source and issuer filled in.

The raw store stays as parsed; this layer is rebuilt from it every run, so improving
the mapping does not require touching `data/holdings/`.

    uv run python -m breadth.holdings

Output: data/mapped/period=YYYY-MM-DD.parquet
    every holdings column, plus
    ticker         filled from cusip, then name, then the SEC list
    ticker_source  cusip | name | sec | None
    issuer_id      normalised name - collapses share classes (GOOGL/GOOG) to one issuer
    unresolved     True when no ticker could be found
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from breadth import edgar
from breadth import exclusions
from breadth.tickers import map_tickers, norm_name

DIR = Path(__file__).resolve().parents[1] / "data" / "mapped"
SPLITS = Path(__file__).resolve().parents[1] / "data" / "splits.parquet"

DATE_COLS = ["period", "available_at"]
STRING_COLS = ["form", "accession", "name", "ticker", "cusip", "ticker_source", "issuer_id", "asset_cat", "payoff_profile"]


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """One dtype convention for everything downstream."""
    df = df.copy()
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col]).astype("datetime64[ns]")
    for col in STRING_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string")
    df["shares"] = df["shares"].astype("int64")
    df["holding_value"] = df["holding_value"].astype("int64")
    df["index_weight"] = df["index_weight"].astype("float64")
    df["unresolved"] = df["unresolved"].fillna(False).astype(bool)
    if "excluded" in df.columns:
        df["excluded"] = df["excluded"].fillna(False).astype(bool)
    if "split_factor" in df.columns:
        df["split_factor"] = df["split_factor"].astype("float64")
    return df


def load_splits() -> pd.DataFrame:
    if not SPLITS.exists():
        return pd.DataFrame(columns=["ticker", "date", "ratio"])
    splits = pd.read_parquet(SPLITS)
    splits["date"] = splits["date"].astype("datetime64[ns]")
    return splits


def split_factors(df: pd.DataFrame, splits: pd.DataFrame) -> np.ndarray:
    """Product of every split after the row's period.

    `close` is restated for splits that happened later, but `shares` and `holding_value`
    are as reported on the day. This factor moves the row onto today's share basis, and it
    is what makes `holding_value / shares` comparable with `close` (B2).
    """
    out = np.ones(len(df))
    for ticker, idx in df.groupby("ticker").groups.items():
        sp = splits[splits["ticker"] == ticker].sort_values("date")
        if sp.empty:
            continue
        dates = sp["date"].values.astype("datetime64[ns]")
        ratios = sp["ratio"].values
        suffix = np.append(np.cumprod(ratios[::-1])[::-1], 1.0)  # suffix[k] = prod(ratios[k:])
        # side="right": a split dated on the period date is already in that day's price
        k = np.searchsorted(
            dates, df.loc[idx, "period"].values.astype("datetime64[ns]"), side="right"
        )
        out[df.index.get_indexer(idx)] = suffix[k]
    return out


def to_issuer_level(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse share classes into one row per issuer per period.

    Alphabet is reported twice (GOOGL, GOOG); breadth must count it once.
    """
    return (
        df.groupby(["period", "issuer_id"], as_index=False)
        .agg(
            available_at=("available_at", "first"),
            name=("name", "first"),
            ticker=("ticker", lambda s: s.dropna().min() if s.notna().any() else pd.NA),
            holding_value=("holding_value", "sum"),
            shares=("shares", "sum"),
            index_weight=("index_weight", "sum"),
            n_listings=("name", "size"),
        )
        .sort_values(["period", "holding_value"], ascending=[True, False])
        .reset_index(drop=True)
    )


def build() -> pd.DataFrame:
    df = map_tickers(edgar.load())
    df["issuer_id"] = df["name"].map(norm_name)
    df["unresolved"] = df["ticker"].isna()
    df = normalise(df)
    df["split_factor"] = split_factors(df, load_splits())

    # ticker reuse and share-class mixups are excluded, never silently averaged in
    df["excluded"] = exclusions.apply(df, exclusions.load())
    df.loc[df["excluded"], "ticker"] = pd.NA
    df.loc[df["excluded"], "ticker_source"] = "excluded"
    df["unresolved"] = df["ticker"].isna()
    return df.sort_values(["period", "holding_value"], ascending=[True, False]).reset_index(drop=True)


def store(df: pd.DataFrame) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    for path in DIR.glob("period=*.parquet"):
        path.unlink()  # derived layer: rebuilt wholesale, never trusted as history
    for period, group in df.groupby(df["period"].dt.strftime("%Y-%m-%d")):
        group.to_parquet(DIR / f"period={period}.parquet", index=False)


def load() -> pd.DataFrame:
    files = sorted(DIR.glob("period=*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def main() -> None:
    df = build()
    store(df)
    resolved = ~df["unresolved"]
    w = df["index_weight"].where(resolved, 0)
    rep = df.groupby("period").agg(rows=("name", "size"), tickers=("ticker", "nunique"),
                                   by_count=("unresolved", lambda s: 100 * (1 - s.mean())),
                                   by_weight=("index_weight", lambda s: w.loc[s.index].sum()))
    print(f"{len(df):,} rows -> {DIR}")
    print(f"sources: {df['ticker_source'].fillna('none').value_counts().to_dict()}")
    print(f"issuers: {df['issuer_id'].nunique():,}, tickers: {df['ticker'].nunique()}")
    print(rep.loc["2016-01-01":].round(1).to_string())
    print(f"\nunresolved: {int(df['unresolved'].sum()):,} rows, "
          f"{df.loc[df['unresolved'], 'name'].nunique():,} names")
    issuer = to_issuer_level(df)
    print(f"issuer level: {len(issuer):,} rows, "
          f"{df['issuer_id'].nunique():,} issuers, "
          f"{(issuer['n_listings'] > 1).sum():,} collapsed listings")


if __name__ == "__main__":
    main()
