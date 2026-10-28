"""Read-only access to pipeline artifacts.

The app and ``cli status`` display what the pipeline wrote; nothing here computes
a signal. Every loader returns ``None`` (or an empty collection) when the artifact
does not exist yet, so callers never have to guess whether a phase has run.

Contracts: docs/SPEC.md section 8.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from crypto_cross_pred.config import Settings, get_settings

PREDICTION_GLOB = "*.parquet"
SIM_GLOB = "*.parquet"
DATASET_GLOB = "dataset_*.parquet"


@dataclass(frozen=True)
class ArtifactInfo:
    """What one artifact family currently holds on disk."""

    name: str
    files: int
    rows: int
    latest: Path | None

    @property
    def exists(self) -> bool:
        """True when at least one file is present."""
        return self.files > 0

    @property
    def latest_name(self) -> str:
        """File name of the most recent artifact, or a dash when empty."""
        return self.latest.name if self.latest else "-"


@dataclass(frozen=True)
class DatasetSummary:
    """Shape and coverage of the processed dataset."""

    rows: int
    symbols: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    rows_per_symbol: pd.Series


def _parquet_rows(path: Path) -> int:
    """Row count from parquet metadata, without reading the data."""
    try:
        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:  # noqa: BLE001 - a corrupt artifact must not crash the app
        return 0


def _latest(paths: list[Path]) -> Path | None:
    """Newest path by modification time."""
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _describe(name: str, paths: list[Path]) -> ArtifactInfo:
    return ArtifactInfo(
        name=name,
        files=len(paths),
        rows=sum(_parquet_rows(path) for path in paths),
        latest=_latest(paths),
    )


def artifact_status(settings: Settings | None = None) -> list[ArtifactInfo]:
    """Summarise every artifact family. Missing directories yield empty entries."""
    settings = settings or get_settings()
    paths = settings.paths.resolve()

    raw_files = sorted(paths.raw_dir.rglob("*.parquet")) if paths.raw_dir.exists() else []
    processed = sorted(paths.processed_dir.glob(DATASET_GLOB))
    predictions = sorted(paths.predictions_dir.glob(PREDICTION_GLOB))
    sim = sorted(paths.sim_dir.glob(SIM_GLOB))

    return [
        _describe("raw", raw_files),
        _describe("processed", processed),
        _describe("predictions", predictions),
        _describe("sim", sim),
    ]


def latest_dataset_path(settings: Settings | None = None) -> Path | None:
    """Newest processed dataset file, if any."""
    settings = settings or get_settings()
    directory = settings.paths.resolve().processed_dir
    if not directory.exists():
        return None
    return _latest(sorted(directory.glob(DATASET_GLOB)))


def latest_predictions_path(settings: Settings | None = None) -> Path | None:
    """Newest predictions file, if any."""
    settings = settings or get_settings()
    directory = settings.paths.resolve().predictions_dir
    if not directory.exists():
        return None
    return _latest(sorted(directory.glob(PREDICTION_GLOB)))


def summarize_dataset(settings: Settings | None = None) -> DatasetSummary | None:
    """Row count, symbol count, date range and per-symbol coverage."""
    path = latest_dataset_path(settings)
    if path is None:
        return None

    frame = pd.read_parquet(path, columns=["symbol", "ts"])
    if frame.empty:
        return None

    timestamps = pd.to_datetime(frame["ts"], utc=True)
    return DatasetSummary(
        rows=len(frame),
        symbols=int(frame["symbol"].nunique()),
        start=timestamps.min(),
        end=timestamps.max(),
        rows_per_symbol=frame["symbol"].value_counts().sort_values(ascending=False),
    )


def load_predictions(settings: Settings | None = None) -> pd.DataFrame | None:
    """Latest predictions, one row per (ts, symbol)."""
    path = latest_predictions_path(settings)
    if path is None:
        return None
    return pd.read_parquet(path)


def load_sim_curves(settings: Settings | None = None) -> dict[str, pd.DataFrame]:
    """Every equity curve, keyed by ``sim0``…``sim3`` or benchmark name.

    Files are named ``{strategy}_{YYYY-MM-DD}.parquet``; the latest file per
    strategy wins.
    """
    settings = settings or get_settings()
    directory = settings.paths.resolve().sim_dir
    if not directory.exists():
        return {}

    latest: dict[str, Path] = {}
    for path in sorted(directory.glob(SIM_GLOB)):
        strategy = path.name.rsplit("_", 1)[0]
        current = latest.get(strategy)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            latest[strategy] = path

    return {strategy: pd.read_parquet(path) for strategy, path in sorted(latest.items())}


def newest_artifact_mtime(settings: Settings | None = None) -> datetime | None:
    """UTC timestamp of the most recently written artifact, or ``None``."""
    settings = settings or get_settings()
    paths = settings.paths.resolve()
    stamps: list[float] = []
    for directory in (
        paths.raw_dir,
        paths.processed_dir,
        paths.predictions_dir,
        paths.sim_dir,
    ):
        if directory.exists():
            stamps.extend(path.stat().st_mtime for path in directory.rglob("*.parquet"))
    if not stamps:
        return None
    return datetime.fromtimestamp(max(stamps), tz=UTC)
