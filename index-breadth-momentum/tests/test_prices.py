"""Price file contracts: the two price bases must stay distinguishable.

Run: cd project_1 && uv run pytest -q
Reads data/prices/, so run `python -m breadth.prices` first.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PRICES = Path(__file__).resolve().parents[1] / "data" / "prices"
COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]


@pytest.fixture(scope="module")
def files() -> list[Path]:
    found = sorted(PRICES.glob("*.parquet"))
    if not found:
        pytest.skip("no price files - run `python -m breadth.prices`")
    return found


@pytest.fixture(scope="module")
def spy() -> pd.DataFrame:
    return pd.read_parquet(PRICES / "SPY.parquet")


def test_columns_and_dtypes(spy: pd.DataFrame) -> None:
    assert list(spy.columns) == COLUMNS
    assert spy["date"].dtype == "datetime64[ms]"
    assert spy["volume"].dtype == "int64"
    for col in ["open", "high", "low", "close", "adj_close"]:
        assert spy[col].dtype == "float64", col


def test_dates_are_trading_days(spy: pd.DataFrame) -> None:
    assert spy["date"].is_monotonic_increasing
    assert not spy["date"].duplicated().any()
    assert (spy["date"].dt.dayofweek < 5).all()


def test_prices_are_positive(spy: pd.DataFrame) -> None:
    assert (spy[["open", "high", "low", "close", "adj_close"]] > 0).all().all()
    assert (spy["volume"] >= 0).all()


def test_volume_times_close_is_turnover(spy: pd.DataFrame) -> None:
    turnover = spy["volume"] * spy["close"]
    # sanity: never negative, and never larger than SPY's whole market cap in one day
    assert (turnover >= 0).all()
    assert turnover.max() < 1e12


def test_adjusted_close_never_exceeds_close(files: list[Path]) -> None:
    """Dividends only ever pull the adjusted series down."""
    for path in files:
        d = pd.read_parquet(path, columns=["adj_close", "close"]).dropna()
        if d.empty:
            continue
        assert (d["adj_close"] <= d["close"] * 1.001).all(), path.stem


def test_dividend_factor_is_non_decreasing(files: list[Path]) -> None:
    """adj/close rises forward in time, because fewer future dividends remain.

    This is what makes the two columns different, and it is the step that a moving
    average must not be computed on.
    """
    for path in files:
        d = pd.read_parquet(path, columns=["adj_close", "close"]).dropna()
        if len(d) < 2:
            continue
        ratio = (d["adj_close"] / d["close"]).to_numpy()
        ratio = ratio[np.isfinite(ratio)]  # PCG-PE carries zero prices; removed under B5
        if len(ratio) < 2:
            continue
        step = np.diff(ratio).min()
        # tolerance absorbs Yahoo's 6-decimal rounding; a real error would be >=0.1%
        assert ratio[-1] >= ratio[0] - 1e-3, path.stem  # adjustment accumulates forward
        assert step >= -1e-3, f"{path.stem} steps back by {step:.6f}"


def test_bases_differ_for_dividend_payers(files: list[Path]) -> None:
    """If adj_close always equals close, the download is broken or dividends are missing."""
    differs = 0
    for path in files:
        d = pd.read_parquet(path, columns=["adj_close", "close"]).dropna()
        if not d.empty and (d["adj_close"] != d["close"]).any():
            differs += 1
    assert differs > 0.5 * len(files)

