"""Odd-instrument filter (B5).

A ticker is not the same thing as a holding. `PCG-PE` is a PG&E preferred, not the common
stock; warrants and units also come back from name matching. Gaps, zero prices and NaN
closes mean the series cannot be trusted either.

Run: cd project_1 && uv run pytest -q
"""

from __future__ import annotations

import pandas as pd
import pytest

from breadth import prices


def write(path, dates, close=1.0) -> None:
    n = len(dates)
    pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "adj_close": close,
            "volume": 1,
        }
    ).to_parquet(path, index=False)


@pytest.fixture
def store(tmp_path):
    cal = pd.bdate_range(end="2026-06-30", periods=40)
    write(tmp_path / "SPY.parquet", cal)
    write(tmp_path / "AAPL.parquet", cal)
    write(tmp_path / "BRK-B.parquet", cal)  # hyphenated class is legitimate
    write(tmp_path / "PCG-PE.parquet", cal)  # preferred line
    write(tmp_path / "GAPPY.parquet", cal.delete(range(15, 26)))  # a two-week hole
    write(tmp_path / "ZERO.parquet", cal, close=0.0)
    return tmp_path


def test_odd_symbols_are_rejected(store) -> None:
    odd = prices.odd_tickers(store)
    assert odd["PCG-PE"] == "not_common_stock"
    assert "AAPL" not in odd
    assert "BRK-B" not in odd  # one-letter class suffix is a real share class


def test_gaps_and_bad_prices_are_rejected(store) -> None:
    odd = prices.odd_tickers(store, max_gap=10)
    assert odd["GAPPY"].startswith("gap_")
    assert odd["ZERO"] == "non_positive_close"


def test_nan_close_is_rejected(tmp_path) -> None:
    cal = pd.bdate_range(end="2026-06-30", periods=10)
    write(tmp_path / "SPY.parquet", cal)
    path = tmp_path / "BNAN.parquet"
    write(path, cal)
    d = pd.read_parquet(path)
    d.loc[3, "close"] = float("nan")
    d.to_parquet(path, index=False)
    assert prices.odd_tickers(tmp_path)["BNAN"] == "missing_close"


def test_clean_excludes_odd_and_stale(store) -> None:
    usable = prices.clean("2026-06-30", prices_dir=store)
    assert "PCG-PE" not in usable
    assert "GAPPY" not in usable
    assert "ZERO" not in usable
    assert {"SPY", "AAPL", "BRK-B"} <= set(usable)


def test_dimson_mapped_tickers_are_plain() -> None:
    """No holding may carry a preferred/warrant style symbol after B5."""
    import re

    from breadth import holdings

    mapped = holdings.load()
    if mapped.empty:
        pytest.skip("no mapped data - run `python -m breadth.holdings`")
    bad = {
        t
        for t in mapped["ticker"].dropna().unique()
        if not re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", str(t))
    }
    assert not bad, bad

