"""Find rows whose ticker no longer refers to the company that was held.

`holding_value / shares` is a real price. If it disagrees with `close x split_factor`,
either the ticker was reused by a different company (`IR` was Ingersoll-Rand plc until
2020, then Ingersoll Rand Inc) or a second share class was mapped onto the first class's
ticker (`UAA` was used for both Class A and Class C).

    uv run python -m breadth.exclusions

Writes config/exclusions.csv; `python -m breadth.holdings` applies it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from breadth import edgar, holdings
from breadth.tickers import map_tickers

DATA = Path(__file__).resolve().parents[1] / "data"
PRICES = DATA / "prices"
OUT = Path(__file__).resolve().parents[1] / "config" / "exclusions.csv"
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
    px["ticker"] = px["ticker"].astype(str)
    return px.sort_values("date")


def detect(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where the reported price cannot be reconciled with the ticker's series."""
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"]).astype("datetime64[ns]")
    df["implied"] = df["holding_value"] / df["shares"]
    df["ticker"] = df["ticker"].astype(str)

    px = load_prices(sorted(df["ticker"].dropna().unique()))
    if px.empty:
        return pd.DataFrame(columns=["period", "name", "ticker", "ratio", "reason"])

    keyed = df[df["ticker"] != "nan"].sort_values("period")
    merged = pd.merge_asof(
        keyed,
        px.rename(columns={"date": "period"}),
        on="period",
        by="ticker",
        direction="nearest",
        tolerance=pd.Timedelta("10D"),
    )
    merged = merged.dropna(subset=["close"])
    merged["ratio"] = merged["implied"] / (merged["close"] * merged["split_factor"])

    bad = merged[(merged["ratio"] - 1).abs() > TOLERANCE].copy()
    if bad.empty:
        return pd.DataFrame(columns=["period", "name", "ticker", "ratio", "reason"])

    # two listings of one issuer carrying the same ticker -> a share class was mapped
    # onto the other class's ticker; anything else needs a human to look at it
    per_issuer = merged.groupby(["period", "issuer_id"])["name"].transform("size")
    merged["dup_listing"] = per_issuer.gt(1)
    bad["dup_listing"] = merged.loc[bad.index, "dup_listing"]
    bad["reason"] = bad["dup_listing"].map({True: "share_class", False: "unexplained"})

    return bad[["period", "name", "ticker", "ratio", "reason"]].sort_values(["period", "ticker"])


def apply(df: pd.DataFrame, exclusions: pd.DataFrame) -> pd.Series:
    """Boolean mask of rows to exclude, matched on (period, name, ticker)."""
    if exclusions.empty:
        return pd.Series(False, index=df.index)
    keys = exclusions.assign(period=pd.to_datetime(exclusions["period"]).astype("datetime64[ns]"))
    keys["ticker"] = keys["ticker"].astype(str)
    keys["name"] = keys["name"].astype(str)
    keys = keys.drop_duplicates(["period", "name", "ticker"])
    left = df[["period", "name", "ticker"]].copy()
    left["period"] = pd.to_datetime(left["period"]).astype("datetime64[ns]")
    left["ticker"] = left["ticker"].astype(str)
    left["name"] = left["name"].astype(str)
    probe = left.merge(keys, on=["period", "name", "ticker"], how="left", indicator=True)
    return (probe["_merge"] == "both").to_numpy()


def load() -> pd.DataFrame:
    if not OUT.exists():
        return pd.DataFrame(columns=["period", "name", "ticker", "ratio", "reason"])
    return pd.read_csv(OUT, dtype={"ticker": str})


def main() -> None:
    df = map_tickers(edgar.load())
    df["issuer_id"] = df["name"].map(holdings.norm_name)
    df["split_factor"] = holdings.split_factors(df, holdings.load_splits())
    found = detect(df)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    found.to_csv(OUT, index=False)
    print(f"{len(found)} rows -> {OUT}")
    if len(found):
        print(found.assign(ratio=found["ratio"].round(2)).to_string(index=False))
        print("\nRun `python -m breadth.holdings` to apply them.")


if __name__ == "__main__":
    main()
