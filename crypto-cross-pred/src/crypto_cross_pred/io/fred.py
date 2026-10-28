"""FRED macro series. Free, no key, daily; the 1-day lag is applied in transform.

Only the five series the feature set needs. Values are stored raw — no lag, no
forward-fill — so the transform stage owns the alignment rule (SPEC §4.2).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd
from pandas_datareader import data as web

from crypto_cross_pred.io import storage

logger = logging.getLogger(__name__)

#: Feature column -> FRED series id.
#:
#: ``BAMLH0A0HYM2`` (ICE BofA HY OAS) would be the textbook choice, but FRED's public
#: CSV endpoint serves the ICE series only from 2023-10 onwards. ``BAA10Y`` (Moody's
#: Baa yield minus the 10Y Treasury) is the same risk-off signal with history from 1986.
SERIES: dict[str, str] = {
    "vix": "VIXCLS",
    "dgs10": "DGS10",
    "dff": "DFF",
    "dxy": "DTWEXBGS",
    "credit_spread": "BAA10Y",
}

FRED_PATH = Path("fred") / "macro.parquet"


def fetch_series(series_id: str, start: date, end: date) -> pd.Series:
    """One FRED series, indexed by UTC-normalised date."""
    frame = web.DataReader(series_id, "fred", start, end)
    series = frame[series_id].astype(float)
    series.index = pd.to_datetime(series.index, utc=True).normalize()
    return series.dropna().rename(series_id)


def fetch_all(start: date, end: date) -> pd.DataFrame:
    """Every series, joined on date. Missing days stay missing."""
    columns = []
    for name, series_id in SERIES.items():
        series = fetch_series(series_id, start, end)
        logger.info("%s: %d observations", series_id, len(series))
        columns.append(series.rename(name))

    frame = pd.concat(columns, axis=1).sort_index()
    frame.index.name = "ts"
    return frame.reset_index()


def update(raw_dir: Path, *, start: date, end: date) -> int:
    """Fetch and upsert into ``data/raw/fred/macro.parquet``. Returns rows added."""
    frame = fetch_all(start, end)
    if frame.empty:
        logger.warning("fred returned no rows")
        return 0

    path = raw_dir / FRED_PATH
    added = storage.upsert(frame, path, keys=("ts",))
    logger.info("fred: %d rows (%d new)", len(frame), added)
    return added


def load(raw_dir: Path) -> pd.DataFrame | None:
    """Read the cached macro frame, or ``None`` when it has not been fetched."""
    return storage.read_parquet(raw_dir / FRED_PATH)
