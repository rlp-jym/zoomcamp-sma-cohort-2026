"""The parquet cache must be atomic, idempotent and honest about missing files."""

from pathlib import Path

import pandas as pd

from crypto_cross_pred.io import storage


def _frame(timestamps: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"ts": pd.to_datetime(timestamps, utc=True), "value": values}
    )


def test_read_missing_partition_returns_none(tmp_path: Path) -> None:
    assert storage.read_parquet(tmp_path / "nope.parquet") is None


def test_round_trip_creates_parent_directories(tmp_path: Path) -> None:
    path = storage.partition_path(tmp_path / "raw" / "binance", "BTCUSDT")

    storage.write_parquet(_frame(["2025-01-01T00:00Z"], [1.0]), path)

    loaded = storage.read_parquet(path)
    assert loaded is not None
    assert len(loaded) == 1


def test_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT.parquet"

    storage.write_parquet(_frame(["2025-01-01T00:00Z"], [1.0]), path)

    assert [item.name for item in tmp_path.iterdir()] == ["BTCUSDT.parquet"]


def test_upsert_deduplicates_and_keeps_the_newest_row(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT.parquet"
    storage.write_parquet(_frame(["2025-01-01T00:00Z", "2025-01-01T01:00Z"], [1.0, 2.0]), path)

    added = storage.upsert(
        _frame(["2025-01-01T01:00Z", "2025-01-01T02:00Z"], [20.0, 3.0]), path
    )

    loaded = storage.read_parquet(path)
    assert loaded is not None
    assert added == 1
    assert len(loaded) == 3
    assert loaded.loc[loaded["ts"] == pd.Timestamp("2025-01-01T01:00Z"), "value"].item() == 20.0


def test_upsert_is_sorted_by_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT.parquet"

    storage.upsert(_frame(["2025-01-01T02:00Z", "2025-01-01T00:00Z"], [3.0, 1.0]), path)

    loaded = storage.read_parquet(path)
    assert loaded is not None
    assert loaded["ts"].is_monotonic_increasing


def test_upsert_of_an_empty_frame_is_a_noop(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT.parquet"
    storage.write_parquet(_frame(["2025-01-01T00:00Z"], [1.0]), path)

    assert storage.upsert(pd.DataFrame(columns=["ts", "value"]), path) == 0


def test_max_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT.parquet"
    storage.write_parquet(
        _frame(["2025-01-01T00:00Z", "2025-01-01T05:00Z"], [1.0, 2.0]), path
    )

    assert storage.max_timestamp(path) == pd.Timestamp("2025-01-01T05:00Z").to_pydatetime()
    assert storage.max_timestamp(tmp_path / "missing.parquet") is None
