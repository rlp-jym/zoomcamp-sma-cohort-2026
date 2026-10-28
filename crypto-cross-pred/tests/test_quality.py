"""The quality report must find gaps, missing funding and missing metrics."""

from pathlib import Path

import pandas as pd

from crypto_cross_pred.io import storage
from crypto_cross_pred.report import quality


def _write_klines(raw_dir: Path, symbol: str, timestamps: list[str]) -> None:
    frame = pd.DataFrame({"ts": pd.to_datetime(timestamps, utc=True), "close": 1.0})
    storage.write_parquet(frame, storage.partition_path(raw_dir / "binance" / "klines", symbol))


def test_full_coverage_symbol(tmp_path: Path) -> None:
    hours = [f"2025-01-01T{hour:02d}:00Z" for hour in range(24)]
    _write_klines(tmp_path, "AAAUSDT", hours)

    frame = quality.build(tmp_path, ["AAAUSDT"])
    summary = quality.summarize(frame)

    assert frame.loc[0, "klines"] == 24
    assert frame.loc[0, "coverage"] == 1.0
    assert frame.loc[0, "gaps"] == 0
    assert summary.missing_funding == ("AAAUSDT",)
    assert summary.missing_metrics == ("AAAUSDT",)


def test_gaps_lower_coverage(tmp_path: Path) -> None:
    hours = [f"2025-01-01T{hour:02d}:00Z" for hour in range(24) if hour not in (5, 6)]
    _write_klines(tmp_path, "BBBUSDT", hours)

    frame = quality.build(tmp_path, ["BBBUSDT"])

    assert frame.loc[0, "klines"] == 22
    assert frame.loc[0, "gaps"] == 1  # one jump of 2 hours
    assert frame.loc[0, "coverage"] < 1.0


def test_missing_symbol_is_zeroed(tmp_path: Path) -> None:
    frame = quality.build(tmp_path, ["CCCUSDT"])
    summary = quality.summarize(frame)

    assert frame.loc[0, "klines"] == 0
    assert summary.under_covered == ("CCCUSDT",)


def test_funding_and_metrics_counts(tmp_path: Path) -> None:
    _write_klines(tmp_path, "AAAUSDT", ["2025-01-01T00:00Z", "2025-01-01T01:00Z"])
    storage.write_parquet(
        pd.DataFrame({"ts": pd.to_datetime(["2025-01-01T00:00Z"], utc=True), "funding_rate": 0.1}),
        storage.partition_path(tmp_path / "binance" / "funding", "AAAUSDT"),
    )
    storage.write_parquet(
        pd.DataFrame(
            {
                "ts": pd.to_datetime(["2025-01-01T00:00Z", "2025-01-01T01:00Z"], utc=True),
                "open_interest": [1.0, None],
            }
        ),
        storage.partition_path(tmp_path / "binance" / "metrics", "AAAUSDT"),
    )

    frame = quality.build(tmp_path, ["AAAUSDT"])
    summary = quality.summarize(frame)

    assert frame.loc[0, "funding"] == 1
    assert frame.loc[0, "metrics"] == 2
    assert frame.loc[0, "metrics_null_pct"] == 0.5
    assert summary.missing_funding == ()


def test_report_is_saved_as_parquet_and_json(tmp_path: Path) -> None:
    _write_klines(tmp_path, "AAAUSDT", ["2025-01-01T00:00Z"])
    frame = quality.build(tmp_path, ["AAAUSDT"])
    summary = quality.summarize(frame)

    parquet_path, json_path = quality.save(frame, summary, tmp_path / "artifacts")

    assert parquet_path.exists()
    assert json_path.exists()
    assert '"symbols": 1' in json_path.read_text(encoding="utf-8")


def test_render_handles_empty_input() -> None:
    empty = pd.DataFrame()
    assert quality.render(empty, quality.summarize(empty)) == "no data to report"
