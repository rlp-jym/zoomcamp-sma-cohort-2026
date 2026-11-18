"""Check parsed holdings against real prices.

`holding_value / shares` is the price the fund reported on the period date. Yahoo closes
are split-adjusted, so multiply by every split after that date and the two must agree.
That is the only check that catches both a bad parse and a wrong company mapped to a name.

    uv run python -m breadth.verify

Writes data/verify_report.csv and prints coverage per period:
    coverage_names   % of holdings with a price near the period date
    coverage_weight  % of index weight those holdings represent
    match_names      % of priced holdings whose implied price agrees within 10%
    match_weight     % of index weight that agrees
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from breadth import holdings
from breadth.holdings import load_splits, split_factors

DATA = Path(__file__).resolve().parents[1] / "data"
PRICES = DATA / "prices"
REPORT = DATA / "verify_report.csv"
TOLERANCE = 0.10


def load_prices(tickers: list[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        path = PRICES / f"{t}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path, columns=["date", "close"]).assign(ticker=t))
    if not frames:
        return pd.DataFrame(columns=["date", "close", "ticker"])
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    return px.sort_values("date")


def reconcile() -> pd.DataFrame:
    """Every holding with its market price, split factor and match flag."""
    df = holdings.load()
    if df.empty:
        raise SystemExit("no mapped data - run `python -m breadth.holdings` first")
    df["period"] = pd.to_datetime(df["period"]).astype("datetime64[ns]")
    df["implied"] = df["holding_value"] / df["shares"]

    px = load_prices(sorted(df["ticker"].dropna().unique()))
    if px.empty:
        raise SystemExit("no price files - run `python -m breadth.prices` first")

    # merge only the rows that have a ticker, then join the result back so that
    # coverage is measured against every holding in the filing
    keyed = df[df["ticker"].notna()].copy()
    keyed["ticker"] = keyed["ticker"].astype(str)
    keyed = keyed.sort_values("period")
    merged = pd.merge_asof(
        keyed,
        px.rename(columns={"date": "period"}),
        on="period",
        by="ticker",
        direction="nearest",
        tolerance=pd.Timedelta("10D"),
    )
    df = df.merge(
        merged.drop_duplicates(["period", "ticker"])[["period", "ticker", "close"]],
        on=["period", "ticker"],
        how="left",
    )

    df["factor"] = split_factors(df, load_splits())
    df["actual"] = df["close"] * df["factor"]
    df["priced"] = df["actual"].notna()
    df["match"] = df["priced"] & ((df["implied"] / df["actual"] - 1).abs() <= TOLERANCE)
    return df


def report(df: pd.DataFrame) -> pd.DataFrame:
    """Coverage and accuracy per period, by count and by portfolio weight."""
    df = df.assign(
        w_priced=df["index_weight"].where(df["priced"], 0),
        w_matched=df["index_weight"].where(df["match"], 0),
    )
    rep = df.groupby(df["period"].dt.strftime("%Y-%m-%d")).agg(
        holdings=("name", "size"),
        coverage_names=("priced", "mean"),
        match_names=("match", "mean"),
        coverage_weight=("w_priced", "sum"),
        match_weight=("w_matched", "sum"),
    )
    for col in ["coverage_names", "match_names"]:
        rep[col] = (100 * rep[col]).round(0)
    rep[["coverage_weight", "match_weight"]] = rep[["coverage_weight", "match_weight"]].round(1)
    return rep


def mismatch_share(df: pd.DataFrame) -> float:
    """Share of portfolio weight that is priced but cannot be reconciled (B6 metric)."""
    bad = df.loc[df["priced"] & ~df["match"], "index_weight"].sum()
    return float(bad / df["index_weight"].sum() * 100) if len(df) else 0.0


def main() -> None:
    df = reconcile()
    rep = report(df)
    rep.to_csv(REPORT)

    print(rep.loc["2016-01-01":].to_string())
    bad = df.loc[df["priced"] & ~df["match"]]
    print(f"\n{len(df):,} rows, {len(bad):,} priced but off by >{TOLERANCE:.0%} "
          f"({mismatch_share(df):.2f}% of weight)")
    print(f"first period with 90% weight coverage: "
          f"{rep.loc[rep['coverage_weight'] >= 90].index.min()}")


if __name__ == "__main__":
    main()
