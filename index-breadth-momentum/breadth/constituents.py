"""Daily constituents of the index, with prices and index weights.

One row per issuer per trading day. Membership and weights come from the most recent
filing that was public on that day, so the table never uses a constituent list before
the market could have known it.

    uv run python -m breadth.constituents

Output: data/constituents/daily.parquet
    date, index_name, issuer_id, name, ticker,
    close, adj_close, volume, index_weight,
    coverage_names, coverage_weight, equal_weight_ok, days_since_filing
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from breadth import holdings, prices

OUT = Path(__file__).resolve().parents[1] / "data" / "constituents" / "daily.parquet"
INDEX_NAME = "SP500"
MIN_WEIGHT_COVERAGE = 80.0  # percent of index weight needed for the weighted reading
MIN_NAME_COVERAGE = 80.0  # percent of constituents needed for the equal-weight reading


def _prices() -> pd.DataFrame:
    odd = set(prices.odd_tickers())
    frames = []
    for path in prices.DIR.glob("*.parquet"):
        if path.stem in odd:
            continue
        d = pd.read_parquet(path, columns=["date", "open", "high", "low", "close", "adj_close", "volume"])
        d["ticker"] = path.stem
        frames.append(d)
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    return px


def _trading_days(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    spy = pd.read_parquet(prices.DIR / "SPY.parquet", columns=["date"])
    dates = pd.to_datetime(spy["date"]).astype("datetime64[ns]")
    dates = dates[(dates >= start) & (dates <= end)]
    return pd.DataFrame({"date": sorted(dates.unique())})


def build() -> pd.DataFrame:
    mapped = holdings.load()
    if mapped.empty:
        raise SystemExit("no mapped data - run `python -m breadth.holdings` first")
    # only common equity: N-PORT tags every holding, and SPY's lone non-equity line is a
    # contingent value right. Pre-2019 filings carry no tag, so those rows are kept as-is.
    equity = mapped["asset_cat"].isna() | (mapped["asset_cat"] == "EC")
    # one row per issuer: Alphabet is two listings (GOOGL, GOOG) and must count once
    members = holdings.to_issuer_level(mapped[equity])

    px = _prices()
    start = px["date"].min()
    end = px["date"].max()

    # each trading day borrows the constituent list that was public by then
    days = _trading_days(start, end)
    snapshots = members[["available_at"]].drop_duplicates().sort_values("available_at")
    days = pd.merge_asof(days, snapshots, left_on="date", right_on="available_at", direction="backward")

    grid = days.merge(members, on="available_at", how="inner")
    grid = grid.merge(px, on=["date", "ticker"], how="left")

    grid["index_name"] = INDEX_NAME
    grid["days_since_filing"] = (grid["date"] - grid["available_at"]).dt.days
    grid["priced"] = grid["close"].notna()

    w_priced = grid["index_weight"].where(grid["priced"], 0)
    cov = (
        grid.assign(w_priced=w_priced)
        .groupby("date")
        .agg(coverage_names=("priced", "mean"), coverage_weight=("w_priced", "sum"))
    )
    cov["coverage_names"] = (100 * cov["coverage_names"]).round(1)
    cov["coverage_weight"] = cov["coverage_weight"].round(1)
    cov["weighted_ok"] = cov["coverage_weight"] >= MIN_WEIGHT_COVERAGE
    cov["equal_weight_ok"] = cov["coverage_names"] >= MIN_NAME_COVERAGE

    grid = grid.merge(cov, left_on="date", right_index=True, how="left")

    cols = [
        "date",
        "index_name",
        "issuer_id",
        "name",
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "index_weight",
        "coverage_names",
        "coverage_weight",
        "weighted_ok",
        "equal_weight_ok",
        "days_since_filing",
    ]
    return (
        grid[cols]
        .sort_values(["date", "index_weight"], ascending=[True, False])
        .reset_index(drop=True)
    )


def load() -> pd.DataFrame:
    if not OUT.exists():
        return pd.DataFrame()
    return pd.read_parquet(OUT)


def main() -> None:
    df = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)

    days = df["date"].nunique()
    print(f"{len(df):,} rows over {days:,} trading days -> {OUT}")
    print(f"issuers: {df['issuer_id'].nunique():,} | tickers: {df['ticker'].nunique():,}")
    print(f"date range: {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"priced rows: {df['close'].notna().mean():.1%}")

    latest = df[df["date"] == df["date"].max()]
    print(f"\nlatest day ({latest['date'].iloc[0].date()}): {len(latest)} constituents, "
          f"coverage {latest['coverage_names'].iloc[0]}% names / "
          f"{latest['coverage_weight'].iloc[0]}% weight, "
          f"weighted_ok={latest['weighted_ok'].iloc[0]}, "
          f"equal_weight_ok={latest['equal_weight_ok'].iloc[0]}")
    print(latest.head(5)[["issuer_id", "ticker", "close", "index_weight"]].to_string(index=False))
    if df["weighted_ok"].any():
        print(f"\nweighted usable from:      {df.loc[df['weighted_ok'], 'date'].min().date()}")
    if df["equal_weight_ok"].any():
        print(f"equal-weight usable from:  {df.loc[df['equal_weight_ok'], 'date'].min().date()}")


if __name__ == "__main__":
    main()

