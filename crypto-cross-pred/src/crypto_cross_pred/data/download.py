"""Raw data acquisition from Binance.

Two sources, one output layout:

- **Bulk archive** (``data.binance.vision``) for history: monthly klines and funding
  zips, daily metrics zips. One HTTP request per file, no API weight.
- **REST** (``fapi.binance.com``) for gaps and the most recent bars, paginated.

Layout: ``data/raw/binance/{dataset}/{symbol}.parquet``. Each dataset keeps its native
cadence; the transform stage aligns them onto the hourly grid.
"""

from __future__ import annotations

import io
import logging
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from crypto_cross_pred.io import binance, storage

logger = logging.getLogger(__name__)

DATASETS: tuple[str, ...] = ("klines", "funding", "metrics")

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]

METRICS_COLUMNS = [
    "create_time",
    "symbol",
    "open_interest",
    "open_interest_value",
    "toptrader_account_ratio",
    "toptrader_position_ratio",
    "global_account_ratio",
    "taker_volume_ratio",
]

#: The archive publishes metrics every 5 minutes; we store them hourly (D-38).
METRICS_RESAMPLE_RULE = "1h"

_thread_local = threading.local()


def _session() -> requests.Session:
    """One session per worker thread."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = binance.make_session()
        _thread_local.session = session
    return session


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of backfilling one symbol for one dataset."""

    symbol: str
    dataset: str
    files: int
    rows: int
    added: int


def month_range(start: date, end: date) -> list[str]:
    """Inclusive list of ``YYYY-MM`` strings covering ``start``…``end``."""
    months: list[str] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append(f"{cursor:%Y-%m}")
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return months


def day_range(start: date, end: date) -> list[str]:
    """Inclusive list of ``YYYY-MM-DD`` strings."""
    days: list[str] = []
    cursor = start
    while cursor <= end:
        days.append(f"{cursor:%Y-%m-%d}")
        cursor += timedelta(days=1)
    return days


def archive_url(dataset: str, symbol: str, period: str) -> str:
    """URL of one archive zip."""
    if dataset == "klines":
        return (
            f"{binance.VISION_URL}/data/futures/um/monthly/klines/"
            f"{symbol}/1h/{symbol}-1h-{period}.zip"
        )
    if dataset == "funding":
        return (
            f"{binance.VISION_URL}/data/futures/um/monthly/fundingRate/"
            f"{symbol}/{symbol}-fundingRate-{period}.zip"
        )
    if dataset == "metrics":
        return (
            f"{binance.VISION_URL}/data/futures/um/daily/metrics/"
            f"{symbol}/{symbol}-metrics-{period}.zip"
        )
    raise ValueError(f"unknown dataset: {dataset}")


def fetch_zip(url: str, *, attempts: int = 3) -> bytes | None:
    """Download a zip, returning ``None`` on 404 (period not published)."""
    for attempt in range(attempts):
        try:
            response = _session().get(url, timeout=60)
        except requests.RequestException as error:
            logger.warning("download failed (%s), attempt %d: %s", error, attempt + 1, url)
            continue
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.warning("status %s, attempt %d: %s", response.status_code, attempt + 1, url)
            continue
        return response.content
    return None


def _read_zip_csv(payload: bytes) -> list[str]:
    """Return the CSV lines inside a one-file zip."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = archive.namelist()[0]
        return archive.read(name).decode("utf-8", "replace").splitlines()


def parse_klines_csv(lines: list[str]) -> pd.DataFrame:
    """Parse hourly klines. Archive files have no header; daily files sometimes do."""
    if lines and lines[0].startswith("open_time"):
        lines = lines[1:]
    if not lines:
        return pd.DataFrame()

    frame = pd.read_csv(io.StringIO("\n".join(lines)), header=None, names=KLINE_COLUMNS)
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    frame[numeric] = frame[numeric].astype(float)
    frame["trades"] = frame["trades"].astype("int64")
    return frame[["ts", *numeric, "trades"]]


def parse_funding_csv(lines: list[str]) -> pd.DataFrame:
    """Parse the 8h funding-rate history."""
    if not lines:
        return pd.DataFrame()
    frame = pd.read_csv(io.StringIO("\n".join(lines)))
    if "calc_time" not in frame:
        return pd.DataFrame()
    frame["ts"] = pd.to_datetime(frame["calc_time"], unit="ms", utc=True)
    frame["funding_rate"] = frame["last_funding_rate"].astype(float)
    return frame[["ts", "funding_rate"]]


def parse_metrics_csv(lines: list[str]) -> pd.DataFrame:
    """Parse daily metrics and aggregate the 5-minute snapshots to hourly.

    The archive only publishes 5-minute files, but hourly is the project's minimum
    resolution (D-38). For each hour we keep the **last** snapshot inside it (``:55``),
    which is the value closest to that hourly bar's close.
    """
    if not lines:
        return pd.DataFrame()
    frame = pd.read_csv(io.StringIO("\n".join(lines)))
    if "create_time" not in frame:
        return pd.DataFrame()

    frame["ts"] = pd.to_datetime(frame["create_time"], utc=True)
    frame = frame.drop(columns=["symbol", "create_time"], errors="ignore")
    frame = frame.rename(
        columns={
            "sum_open_interest": "open_interest",
            "sum_open_interest_value": "open_interest_value",
            "count_toptrader_long_short_ratio": "toptrader_account_ratio",
            "sum_toptrader_long_short_ratio": "toptrader_position_ratio",
            "count_long_short_ratio": "global_account_ratio",
            "sum_taker_long_short_vol_ratio": "taker_volume_ratio",
        }
    )
    frame = frame.drop_duplicates(subset=["ts"], keep="last").sort_values("ts", kind="stable")
    frame["ts"] = frame["ts"].dt.floor(METRICS_RESAMPLE_RULE)
    frame = frame.drop_duplicates(subset=["ts"], keep="last")
    return frame.reset_index(drop=True)


PARSERS = {
    "klines": parse_klines_csv,
    "funding": parse_funding_csv,
    "metrics": parse_metrics_csv,
}


def backfill_symbol(
    symbol: str,
    dataset: str,
    *,
    start: date,
    end: date,
    raw_dir: Path,
) -> DownloadResult:
    """Download every archive file for one symbol/dataset and upsert into parquet."""
    periods = month_range(start, end) if dataset != "metrics" else day_range(start, end)
    parser = PARSERS[dataset]

    frames: list[pd.DataFrame] = []
    files = 0
    for period in periods:
        payload = fetch_zip(archive_url(dataset, symbol, period))
        if payload is None:
            continue
        files += 1
        frame = parser(_read_zip_csv(payload))
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return DownloadResult(symbol=symbol, dataset=dataset, files=files, rows=0, added=0)

    combined = pd.concat(frames, ignore_index=True)
    path = storage.partition_path(raw_dir / "binance" / dataset, symbol)
    added = storage.upsert(combined, path, keys=("ts",))
    return DownloadResult(
        symbol=symbol,
        dataset=dataset,
        files=files,
        rows=len(combined),
        added=added,
    )


def backfill(
    symbols: list[str],
    *,
    start: date,
    end: date,
    raw_dir: Path,
    datasets: tuple[str, ...] = DATASETS,
    workers: int = 4,
) -> list[DownloadResult]:
    """Backfill many symbols, a few in parallel."""
    tasks = [(symbol, dataset) for symbol in symbols for dataset in datasets]

    def run(task: tuple[str, str]) -> DownloadResult:
        symbol, dataset = task
        try:
            result = backfill_symbol(symbol, dataset, start=start, end=end, raw_dir=raw_dir)
            logger.info(
                "%s %s: %d files, %d rows (%d new)",
                symbol,
                dataset,
                result.files,
                result.rows,
                result.added,
            )
            return result
        except Exception as error:  # noqa: BLE001 - one symbol must not stop the batch
            logger.error("%s %s failed: %s", symbol, dataset, error)
            return DownloadResult(symbol=symbol, dataset=dataset, files=0, rows=0, added=0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, tasks))


def fetch_klines_rest(
    symbol: str,
    *,
    start: datetime,
    end: datetime,
    interval: str = "1h",
    limit: int = binance.MAX_KLINES_PER_REQUEST,
) -> pd.DataFrame:
    """Page through the REST klines endpoint for a time range."""
    session = _session()
    rows: list[list[Any]] = []
    cursor = start

    while cursor < end:
        batch = binance.klines(
            session,
            symbol,
            interval=interval,
            start_time=cursor,
            end_time=end,
            limit=limit,
        )
        if not batch:
            break
        rows.extend(batch)
        last_open = datetime.fromtimestamp(batch[-1][0] / 1000, tz=UTC)
        if last_open <= cursor:
            break
        cursor = last_open + timedelta(hours=1)

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame.columns = KLINE_COLUMNS
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    frame[numeric] = frame[numeric].astype(float)
    frame["trades"] = frame["trades"].astype("int64")
    return frame[["ts", *numeric, "trades"]].drop_duplicates(subset=["ts"]).sort_values("ts")


def _drop_incomplete_bars(frame: pd.DataFrame, *, now: datetime) -> pd.DataFrame:
    """Drop the current, still-open hourly bar."""
    if frame.empty:
        return frame
    complete = frame["ts"] + pd.Timedelta(hours=1) <= now
    return frame.loc[complete].reset_index(drop=True)


def incremental_symbol(
    symbol: str,
    *,
    raw_dir: Path,
    now: datetime | None = None,
) -> dict[str, int]:
    """Top up klines and funding from REST, starting after the last stored bar."""
    now = now or datetime.now(UTC)
    added: dict[str, int] = {}

    kline_path = storage.partition_path(raw_dir / "binance" / "klines", symbol)
    last_kline = storage.max_timestamp(kline_path)
    if last_kline is None:
        added["klines"] = 0
    else:
        start = last_kline + timedelta(hours=1)
        if start < now:
            frame = fetch_klines_rest(symbol, start=start, end=now)
            frame = _drop_incomplete_bars(frame, now=now)
            added["klines"] = storage.upsert(frame, kline_path, keys=("ts",))
        else:
            added["klines"] = 0

    funding_path = storage.partition_path(raw_dir / "binance" / "funding", symbol)
    last_funding = storage.max_timestamp(funding_path)
    if last_funding is None:
        added["funding"] = 0
    else:
        records = binance.funding_history(_session(), symbol, start_time=last_funding, end_time=now)
        if records:
            frame = pd.DataFrame(records)
            frame["ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
            frame["funding_rate"] = frame["fundingRate"].astype(float)
            added["funding"] = storage.upsert(
                frame[["ts", "funding_rate"]], funding_path, keys=("ts",)
            )
        else:
            added["funding"] = 0

    return added


def incremental(
    symbols: list[str],
    *,
    raw_dir: Path,
    workers: int = 4,
) -> list[tuple[str, dict[str, int]]]:
    """Top up every symbol from REST. A second run should add almost nothing."""

    def run(symbol: str) -> tuple[str, dict[str, int]]:
        try:
            added = incremental_symbol(symbol, raw_dir=raw_dir)
            logger.info("%s incremental: %s", symbol, added)
            return symbol, added
        except Exception as error:  # noqa: BLE001 - one symbol must not stop the batch
            logger.error("%s incremental failed: %s", symbol, error)
            return symbol, {"klines": 0, "funding": 0}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, symbols))
