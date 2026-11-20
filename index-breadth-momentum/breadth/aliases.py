"""Curated name -> ticker aliases, accepted only when the price agrees.

The name lookup cannot bridge a renamed company (`Adobe Systems` -> `Adobe Inc`) or a
missing SEC entry (`AVB` is absent from `company_tickers.json`). Aliases fill that gap, but
each one is checked against the fund's own reported price before it is used:

    holding_value / shares  vs  close x split_factor  ~ 1.0

    uv run python -m breadth.aliases

Writes config/aliases.csv. tickers.map_tickers applies rows with ok=True.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from breadth import holdings, prices

OUT = Path(__file__).resolve().parents[1] / "config" / "aliases.csv"
TOLERANCE = 0.10

# name as printed in the filing -> ticker today. Deliberately short: only names where the
# successor is unambiguous. Acquired companies are left out; they have nothing to point at.
CANDIDATES = [
    ("Adobe Systems, Inc", "ADBE"),
    ("Wal-Mart Stores, Inc", "WMT"),
    ("Wal Mart Stores, Inc", "WMT"),
    ("AvalonBay Communities Inc", "AVB"),
    ("Simon Property Group, Inc. REIT", "SPG"),
    ("American Tower Corp. REIT", "AMT"),
    ("NXP Semiconductors NV", "NXPI"),
    ("Mattel, Inc", "MAT"),
    ("Torchmark Corp", "GL"),
    ("United Technologies Corp", "RTX"),
    ("Raytheon Co", "RTN"),
    ("Kellogg Co", "K"),
    ("Discover Financial Services", "DFS"),
    ("Electronic Arts Inc", "EA"),
]


def _prices_for(tickers: list[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        path = prices.DIR / f"{t}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path, columns=["date", "close"]).assign(ticker=t))
    if not frames:
        return pd.DataFrame(columns=["date", "close", "ticker"])
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    px["ticker"] = px["ticker"].astype(str)
    return px.sort_values("date")


def _ensure_prices(tickers: list[str]) -> None:
    """Fetch any candidate the pipeline never downloaded (it only fetches mapped ones)."""
    import yfinance as yf

    missing = [t for t in tickers if not (prices.DIR / f"{t}.parquet").exists()]
    if not missing:
        return
    for t in missing:  # one at a time: a batch download misaligns when a symbol fails
        data = yf.download(t, start=prices.START, auto_adjust=False, actions=False,
                           progress=False, threads=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        prices._save(t, data)
    print(f"fetched {len(missing)} price series for alias checks")


def check() -> pd.DataFrame:
    df = holdings.load()
    if df.empty:
        raise SystemExit("no mapped data - run `python -m breadth.holdings` first")
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"]).astype("datetime64[ns]")
    df["implied"] = df["holding_value"] / df["shares"]

    names = {name for name, _ in CANDIDATES}
    rows = df[df["name"].isin(names)].copy()
    rows["ticker"] = rows["name"].map(dict(CANDIDATES))
    rows["ticker"] = rows["ticker"].astype(str)
    # unresolved rows carry no split factor (no ticker to look up), so recompute for the
    # candidate symbol before comparing prices
    rows["split_factor"] = holdings.split_factors(rows, holdings.load_splits())

    _ensure_prices(sorted({t for _, t in CANDIDATES}))
    px = _prices_for(sorted({t for _, t in CANDIDATES}))
    merged = pd.merge_asof(
        rows.sort_values("period"),
        px.rename(columns={"date": "period"}),
        on="period",
        by="ticker",
        direction="nearest",
        tolerance=pd.Timedelta("10D"),
    ).dropna(subset=["close"])

    merged["ratio"] = merged["implied"] / (merged["close"] * merged["split_factor"])
    stats = merged.groupby("ticker")["ratio"].agg(["median", "size"]).rename(columns={"size": "n_priced"})

    out = pd.DataFrame(CANDIDATES, columns=["name", "ticker"]).merge(
        stats, left_on="ticker", right_index=True, how="left"
    )
    out["n_priced"] = out["n_priced"].fillna(0).astype(int)
    out["ok"] = out["n_priced"].gt(0) & (out["median"].sub(1).abs() <= TOLERANCE)
    return out.sort_values(["ok", "name"], ascending=[False, True]).reset_index(drop=True)


def load() -> pd.DataFrame:
    if not OUT.exists():
        return pd.DataFrame(columns=["name", "ticker", "median", "n_priced", "ok"])
    return pd.read_csv(OUT, dtype={"ticker": str, "name": str})


def main() -> None:
    out = check()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    accepted = out[out["ok"]]
    print(f"{len(accepted)}/{len(out)} aliases accepted -> {OUT}")
    print(accepted[["name", "ticker", "median", "n_priced"]].round(3).to_string(index=False))
    rejected = out[~out["ok"]]
    if len(rejected):
        print("\nrejected (price does not agree):")
        print(rejected[["name", "ticker", "median", "n_priced"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
