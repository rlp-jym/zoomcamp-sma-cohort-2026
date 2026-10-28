"""Crypto Fear & Greed index from alternative.me. Free, no key, daily.

The API returns the full history when ``limit=0``. Values are 0-100 integers; the
classification label is dropped because the model gets the number.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from crypto_cross_pred.io import storage

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/"
FNG_PATH = Path("alternative") / "fng.parquet"


def parse_payload(payload: dict) -> pd.DataFrame:
    """Convert the API payload into ``ts`` (daily, UTC) and ``fng`` columns."""
    rows = payload.get("data", [])
    if not rows:
        return pd.DataFrame(columns=["ts", "fng"])

    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(
        frame["timestamp"].astype("int64"), unit="s", utc=True
    ).dt.normalize()
    frame["fng"] = frame["value"].astype(float)
    return (
        frame[["ts", "fng"]]
        .drop_duplicates(subset=["ts"], keep="last")
        .sort_values("ts")
        .reset_index(drop=True)
    )


def fetch(session: requests.Session | None = None, *, limit: int = 0) -> pd.DataFrame:
    """Download the index history. ``limit=0`` means everything available."""
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", "crypto-cross-pred/0.1 (research)")
    response = session.get(FNG_URL, params={"limit": limit, "format": "json"}, timeout=30)
    response.raise_for_status()
    return parse_payload(response.json())


def update(raw_dir: Path, session: requests.Session | None = None) -> int:
    """Fetch and upsert into ``data/raw/alternative/fng.parquet``. Returns rows added."""
    frame = fetch(session)
    if frame.empty:
        logger.warning("fear & greed returned no rows")
        return 0

    path = raw_dir / FNG_PATH
    added = storage.upsert(frame, path, keys=("ts",))
    logger.info(
        "fear & greed: %d rows (%d new), %s -> %s",
        len(frame),
        added,
        frame["ts"].min().date(),
        frame["ts"].max().date(),
    )
    return added


def load(raw_dir: Path) -> pd.DataFrame | None:
    """Read the cached index, or ``None`` when it has not been fetched."""
    return storage.read_parquet(raw_dir / FNG_PATH)


def latest_timestamp(raw_dir: Path) -> datetime | None:
    """Most recent cached day, used by the incremental loader."""
    path = raw_dir / FNG_PATH
    return storage.max_timestamp(path)


def today_utc() -> datetime:
    """Today at midnight UTC."""
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
