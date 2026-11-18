"""Schema contracts for the mapped holdings layer.

Run: cd project_1 && uv run pytest -q
These read data/mapped/, so run `python -m breadth.holdings` first.
"""

from __future__ import annotations

import pandas as pd
import pytest

from breadth import holdings

EXPECTED = {
    "form",
    "available_at",
    "accession",
    "period",
    "name",
    "ticker",
    "cusip",
    "shares",
    "holding_value",
    "index_weight",
    "ticker_source",
    "issuer_id",
    "unresolved",
    "split_factor",
    "excluded",
    "asset_cat",
    "payoff_profile",
}


@pytest.fixture(scope="module")
def mapped() -> pd.DataFrame:
    df = holdings.load()
    if df.empty:
        pytest.skip("no mapped data - run `python -m breadth.holdings`")
    return df


def test_columns(mapped: pd.DataFrame) -> None:
    assert set(mapped.columns) == EXPECTED
    assert "value" not in mapped.columns  # renamed to holding_value


def test_dtypes(mapped: pd.DataFrame) -> None:
    assert mapped["period"].dtype == "datetime64[ns]"
    assert mapped["available_at"].dtype == "datetime64[ns]"
    for col in ["ticker", "cusip", "issuer_id", "ticker_source", "form"]:
        assert mapped[col].dtype == "string", col
    assert mapped["shares"].dtype == "int64"
    assert mapped["holding_value"].dtype == "int64"
    assert mapped["index_weight"].dtype == "float64"
    assert mapped["split_factor"].dtype == "float64"
    assert mapped["unresolved"].dtype == "bool"
    assert mapped["excluded"].dtype == "bool"


def test_periods_are_month_ends(mapped: pd.DataFrame) -> None:
    periods = mapped["period"].dt.strftime("%Y-%m-%d").unique()
    assert len(periods) == 62
    assert all(p.endswith(("03-31", "06-30", "09-30", "12-31")) for p in periods)


def test_available_after_period(mapped: pd.DataFrame) -> None:
    assert (mapped["available_at"] > mapped["period"]).all()


def test_weights_sum_to_100(mapped: pd.DataFrame) -> None:
    totals = mapped.groupby("period")["holding_value"].sum()
    assert (totals > 0).all()
    weights = mapped.groupby("period")["index_weight"].sum()
    assert weights.sub(100).abs().max() < 0.01


def test_no_holdings_without_value(mapped: pd.DataFrame) -> None:
    assert (mapped["holding_value"] > 0).all()
    assert (mapped["shares"] > 0).all()
    assert mapped["cusip"].dropna().ne("000000000").all()


def test_share_classes_collapse_to_one_issuer(mapped: pd.DataFrame) -> None:
    issuer = holdings.to_issuer_level(mapped)
    assert not issuer.duplicated(["period", "issuer_id"]).any()
    assert (issuer["n_listings"] >= 1).all()
    # nothing is lost or invented by the aggregation
    assert issuer.groupby("period")["holding_value"].sum().sub(
        mapped.groupby("period")["holding_value"].sum()
    ).abs().max() == 0
    assert issuer.groupby("period")["index_weight"].sum().sub(100).abs().max() < 0.01


def test_known_dual_listing_collapses(mapped: pd.DataFrame) -> None:
    latest = mapped["period"].max()
    rows = mapped[(mapped["period"] == latest) & (mapped["issuer_id"] == "alphabet")]
    if len(rows) > 1:
        issuer = holdings.to_issuer_level(mapped)
        one = issuer[(issuer["period"] == latest) & (issuer["issuer_id"] == "alphabet")]
        assert len(one) == 1
        assert one["holding_value"].iloc[0] == rows["holding_value"].sum()


def test_split_factor_known_cases(mapped: pd.DataFrame) -> None:
    """A row before a split carries the cumulative factor of that split and later ones."""
    assert (mapped["split_factor"] > 0).all()

    def factor(ticker: str, period: str) -> float:
        rows = mapped[(mapped["ticker"] == ticker) & (mapped["period"] == pd.Timestamp(period))]
        return float(rows["split_factor"].iloc[0])

    assert factor("GOOGL", "2020-09-30") == pytest.approx(20.0)  # 20:1 on 2022-07-18
    assert factor("WMT", "2023-09-30") == pytest.approx(3.0)  # 3:1 on 2024-02-26
    assert factor("GE", "2020-12-31") == pytest.approx(0.125 * 1.281 * 1.253, rel=1e-6)
    # once every split is in the past, the row is already on today's basis
    assert factor("GOOGL", "2026-06-30") == pytest.approx(1.0)


def test_split_factor_reconciles_with_prices(mapped: pd.DataFrame) -> None:
    """holding_value / shares == close x split_factor, i.e. B2's acceptance test."""
    import pathlib

    prices = pathlib.Path(__file__).resolve().parents[1] / "data" / "prices"
    for ticker in ["GE", "GOOGL", "WMT"]:
        path = prices / f"{ticker}.parquet"
        if not path.exists():
            pytest.skip("no price files - run `python -m breadth.prices`")
        px = pd.read_parquet(path, columns=["date", "close"]).dropna()
        px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
        rows = mapped[mapped["ticker"] == ticker].sort_values("period")
        joined = pd.merge_asof(
            rows,
            px.rename(columns={"date": "period"}).sort_values("period"),
            on="period",
            direction="nearest",
            tolerance=pd.Timedelta("10D"),
        ).dropna(subset=["close"])
        if joined.empty:
            continue
        implied = joined["holding_value"] / joined["shares"]
        ratio = implied / (joined["close"] * joined["split_factor"])
        assert ratio.median() == pytest.approx(1.0, abs=0.01), ticker


def test_exclusions_are_applied(mapped: pd.DataFrame) -> None:
    """Every row listed in config/exclusions.csv is stripped of its ticker."""
    from breadth import exclusions

    listed = exclusions.load()
    if listed.empty:
        pytest.skip("no exclusion list")

    assert int(mapped["excluded"].sum()) == len(listed)
    assert mapped.loc[mapped["excluded"], "ticker"].isna().all()
    assert (mapped.loc[mapped["excluded"], "ticker_source"] == "excluded").all()

    periods = mapped["period"].dt.strftime("%Y-%m-%d")
    for row in listed.itertuples():
        hit = mapped[(periods == row.period) & (mapped["name"].astype(str) == row.name)]
        assert len(hit) >= 1, f"{row.period} {row.name} not found"
        assert hit["excluded"].all()


def test_no_priced_row_is_off_by_more_than_10pct(mapped: pd.DataFrame) -> None:
    """B3 acceptance: after exclusions, every priced row reconciles."""
    import pathlib

    prices = pathlib.Path(__file__).resolve().parents[1] / "data" / "prices"
    rows = mapped.dropna(subset=["ticker"]).copy()
    if rows.empty:
        pytest.skip("no mapped tickers")
    rows["ticker"] = rows["ticker"].astype(str)

    frames = []
    for ticker in rows["ticker"].unique():
        path = prices / f"{ticker}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path, columns=["date", "close"]).assign(ticker=ticker))
    if not frames:
        pytest.skip("no price files - run `python -m breadth.prices`")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    px["ticker"] = px["ticker"].astype(str)

    joined = pd.merge_asof(
        rows.sort_values("period"),
        px.sort_values("date").rename(columns={"date": "period"}),
        on="period",
        by="ticker",
        direction="nearest",
        tolerance=pd.Timedelta("10D"),
    ).dropna(subset=["close"])
    implied = joined["holding_value"] / joined["shares"]
    ratio = implied / (joined["close"] * joined["split_factor"])
    bad = joined[(ratio - 1).abs() > 0.10]
    assert len(bad) == 0, bad[["period", "ticker"]].head(5).to_string()
