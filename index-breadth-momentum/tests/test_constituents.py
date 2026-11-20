"""Contracts for the daily constituent table (C1/C2).

Run: cd project_1 && uv run pytest -q
Reads data/constituents/sp500_constituents_daily.parquet, so run `python -m breadth.constituents` first.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from breadth import constituents, prices

COLUMNS = [
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


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    df = constituents.load()
    if df.empty:
        pytest.skip("no constituent table - run `python -m breadth.constituents`")
    return df


def test_columns(table: pd.DataFrame) -> None:
    assert list(table.columns) == COLUMNS
    assert (table["index_name"] == "SP500").all()


def test_one_row_per_issuer_per_day(table: pd.DataFrame) -> None:
    assert not table.duplicated(["date", "issuer_id"]).any()
    assert table["date"].dtype == "datetime64[ns]"


def test_no_constituent_list_from_the_future(table: pd.DataFrame) -> None:
    """days_since_filing >= 0 means the filing was already public on that day."""
    assert (table["days_since_filing"] >= 0).all()


def test_weights_sum_to_100_per_day(table: pd.DataFrame) -> None:
    totals = table.groupby("date")["index_weight"].sum()
    assert totals.sub(100).abs().max() < 0.01


def test_dates_are_trading_days(table: pd.DataFrame) -> None:
    spy = pd.read_parquet(prices.DIR / "SPY.parquet", columns=["date"])
    calendar = set(pd.to_datetime(spy["date"]).astype("datetime64[ns]"))
    assert set(table["date"]).issubset(calendar)


def test_coverage_columns_agree(table: pd.DataFrame) -> None:
    """Both gates are 80%, each measured on its own denominator."""
    assert table["coverage_names"].between(0, 100).all()
    assert table["coverage_weight"].between(0, 100.001).all()
    assert (table["weighted_ok"] == (table["coverage_weight"] >= 80)).all()
    assert (table["equal_weight_ok"] == (table["coverage_names"] >= 80)).all()


def test_price_and_ticker_travel_together(table: pd.DataFrame) -> None:
    priced = table["close"].notna()
    assert table.loc[priced, "ticker"].notna().all()
    assert table.loc[~priced, "close"].isna().all()


def test_known_weights_on_a_known_date(table: pd.DataFrame) -> None:
    """2026-09-01 is the first day the 2026-06-30 filing was public."""
    day = table[table["date"] == pd.Timestamp("2026-09-01")].set_index("issuer_id")
    assert day["days_since_filing"].iloc[0] == 4  # filed 2026-08-28
    assert day.loc["nvidia", "index_weight"] == pytest.approx(7.52, abs=0.02)
    assert day.loc["apple", "index_weight"] == pytest.approx(6.59, abs=0.02)
    assert len(day) >= 495


def test_constituent_list_lags_the_filing(table: pd.DataFrame) -> None:
    """Before a filing is public, the previous quarter's weights are still in force."""
    before = table[table["date"] == pd.Timestamp("2026-06-30")].set_index("issuer_id")
    after = table[table["date"] == pd.Timestamp("2026-09-01")].set_index("issuer_id")
    assert before.loc["nvidia", "index_weight"] != after.loc["nvidia", "index_weight"]
    assert before["days_since_filing"].iloc[0] > after["days_since_filing"].iloc[0]


def test_modern_days_clear_both_floors(table: pd.DataFrame) -> None:
    recent = table[table["date"] >= "2024-01-01"]
    assert recent["weighted_ok"].all()
    assert recent["equal_weight_ok"].all()


def test_weighted_reading_starts_before_equal_weight(table: pd.DataFrame) -> None:
    """Weight coverage recovers before name coverage does."""
    weighted = table.loc[table["weighted_ok"], "date"].min()
    equal = table.loc[table["equal_weight_ok"], "date"].min()
    assert weighted < equal
    assert equal - weighted > pd.Timedelta(days=365)


def test_no_non_equity_rows(table: pd.DataFrame) -> None:
    """C3: only common equity reaches the constituent table."""
    from breadth import holdings

    mapped = holdings.load()
    if mapped.empty:
        pytest.skip("no mapped data")
    non_equity = mapped["asset_cat"].notna() & (mapped["asset_cat"] != "EC")
    if not non_equity.any():
        pytest.skip("no non-equity line in this dataset version")
    bad_issuers = set(mapped.loc[non_equity, "issuer_id"])
    assert not set(table["issuer_id"]) & bad_issuers
