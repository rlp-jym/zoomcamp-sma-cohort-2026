"""Stale-price guard (B4).

A delisted ticker keeps whatever history Yahoo had when it was last fetched. Nothing in
the file says "this stopped trading", so the panel would happily quote it at a frozen
price. `prices.stale()` finds those symbols.

Run: cd project_1 && uv run pytest -q
"""

from __future__ import annotations

import pandas as pd
import pytest

from breadth import prices


def write(path, dates) -> None:
    pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "adj_close": 1.0,
            "volume": 1,
        }
    ).to_parquet(path, index=False)


@pytest.fixture
def fake_store(tmp_path):
    calendar = pd.bdate_range(end="2026-06-30", periods=60)
    write(tmp_path / "SPY.parquet", calendar)
    write(tmp_path / "FRESH.parquet", calendar[:-2])  # last price 2 sessions back
    write(tmp_path / "EDGE.parquet", calendar[:-5])  # exactly 5 sessions back
    write(tmp_path / "STALE.parquet", calendar[:-20])  # last price 20 sessions back
    return tmp_path


def test_stale_flags_only_old_series(fake_store) -> None:
    found = prices.stale("2026-06-30", max_age=5, prices_dir=fake_store)
    assert found == ["STALE"]


def test_boundary_is_inclusive(fake_store) -> None:
    """Exactly `max_age` trading days behind is still considered current."""
    assert "EDGE" not in prices.stale("2026-06-30", max_age=5, prices_dir=fake_store)
    assert "EDGE" in prices.stale("2026-06-30", max_age=4, prices_dir=fake_store)


def test_last_dates_reports_every_file(fake_store) -> None:
    last = prices.last_dates(fake_store)
    assert set(last.index) == {"SPY", "FRESH", "EDGE", "STALE"}
    assert last["FRESH"] == pd.Timestamp("2026-06-26")


def test_weekend_asof_does_not_flag_everything(fake_store) -> None:
    # 2026-06-28 is a Sunday; the calendar stops at Friday 2026-06-26
    assert "FRESH" not in prices.stale("2026-06-28", max_age=5, prices_dir=fake_store)
