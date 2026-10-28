"""Artifact readers must be honest about missing files and pick the latest one."""

import time
from pathlib import Path

import pandas as pd
import pytest

from crypto_cross_pred import config
from crypto_cross_pred.io import artifacts


def _settings(tmp_path: Path) -> config.Settings:
    return config.Settings(
        paths=config.PathsConfig(
            data_dir=tmp_path,
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            predictions_dir=tmp_path / "predictions",
            sim_dir=tmp_path / "sim",
            artifacts_dir=tmp_path / "artifacts",
        )
    )


def _write_dataset(directory: Path, name: str = "dataset_2025-01-01.parquet") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "BTCUSDT", "ETHUSDT"],
            "ts": pd.to_datetime(["2025-01-01T00:00Z", "2025-01-01T01:00Z", "2025-01-01T00:00Z"]),
        }
    )
    path = directory / name
    frame.to_parquet(path, index=False)
    return path


def test_status_is_empty_when_nothing_was_written(tmp_path: Path) -> None:
    status = artifacts.artifact_status(_settings(tmp_path))
    assert [entry.name for entry in status] == ["raw", "processed", "predictions", "sim"]
    assert all(entry.files == 0 and entry.rows == 0 for entry in status)
    assert artifacts.newest_artifact_mtime(_settings(tmp_path)) is None


def test_dataset_summary_counts_rows_and_symbols(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_dataset(settings.paths.resolve().processed_dir)

    summary = artifacts.summarize_dataset(settings)

    assert summary is not None
    assert summary.rows == 3
    assert summary.symbols == 2
    assert summary.rows_per_symbol.loc["BTCUSDT"] == 2
    assert summary.start == pd.Timestamp("2025-01-01T00:00Z")


def test_summary_is_none_without_a_dataset(tmp_path: Path) -> None:
    assert artifacts.summarize_dataset(_settings(tmp_path)) is None


def test_predictions_loader_returns_none_then_frame(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert artifacts.load_predictions(settings) is None

    directory = settings.paths.resolve().predictions_dir
    directory.mkdir(parents=True)
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "ts": pd.to_datetime(["2025-01-01T00:00Z"]),
            "pred_reg": [0.01],
            "p_top": [0.3],
        }
    ).to_parquet(directory / "2025-01-01.parquet", index=False)

    loaded = artifacts.load_predictions(settings)
    assert loaded is not None
    assert loaded["pred_reg"].iloc[0] == pytest.approx(0.01)


def test_sim_curves_keep_the_latest_file_per_strategy(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = settings.paths.resolve().sim_dir
    directory.mkdir(parents=True)

    older = directory / "sim0_2025-01-01.parquet"
    newer = directory / "sim0_2025-01-02.parquet"
    benchmark = directory / "btc_hodl_2025-01-01.parquet"

    for path, equity in ((older, 1.0), (benchmark, 2.0)):
        pd.DataFrame({"ts": pd.to_datetime(["2025-01-01T00:00Z"]), "equity": [equity]}).to_parquet(
            path, index=False
        )
        time.sleep(0.01)
    pd.DataFrame({"ts": pd.to_datetime(["2025-01-02T00:00Z"]), "equity": [1.5]}).to_parquet(
        newer, index=False
    )

    curves = artifacts.load_sim_curves(settings)

    assert set(curves) == {"sim0", "btc_hodl"}
    assert curves["sim0"]["equity"].iloc[0] == pytest.approx(1.5)
    assert curves["btc_hodl"]["equity"].iloc[0] == pytest.approx(2.0)
