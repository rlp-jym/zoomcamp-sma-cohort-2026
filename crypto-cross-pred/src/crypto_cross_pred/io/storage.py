"""Local parquet cache: atomic writes, per-symbol partitions, max-timestamp lookups.

Every write goes to a temporary file and is moved into place, so a crash mid-write
cannot leave a half-written partition. Reads of a missing file return ``None``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def partition_path(root: Path, symbol: str) -> Path:
    """Path of one symbol's partition under ``root``."""
    return root / f"{symbol}.parquet"


def read_parquet(path: Path) -> pd.DataFrame | None:
    """Read a partition, or ``None`` when it does not exist."""
    if not path.exists():
        return None
    return pd.read_parquet(path)


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    """Write ``frame`` atomically, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, path)


def max_timestamp(path: Path, column: str = "ts") -> datetime | None:
    """Latest timestamp in a partition, or ``None`` when it is missing or empty."""
    frame = read_parquet(path)
    if frame is None or frame.empty or column not in frame:
        return None
    return pd.to_datetime(frame[column], utc=True).max().to_pydatetime()


def upsert(
    frame: pd.DataFrame,
    path: Path,
    *,
    keys: tuple[str, ...] = ("ts",),
    sort_by: str = "ts",
) -> int:
    """Merge ``frame`` into the partition, keeping the newest row per key.

    Returns the number of rows the partition grew by.
    """
    if frame.empty:
        return 0

    existing = read_parquet(path)
    if existing is not None and not existing.empty:
        before = len(existing)
        combined = pd.concat([existing, frame], ignore_index=True)
    else:
        before = 0
        combined = frame.copy()

    combined = (
        combined.drop_duplicates(subset=list(keys), keep="last")
        .sort_values(sort_by)
        .reset_index(drop=True)
    )
    write_parquet(combined, path)
    return len(combined) - before
