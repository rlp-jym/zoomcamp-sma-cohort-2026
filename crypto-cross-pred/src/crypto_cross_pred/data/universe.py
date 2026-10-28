"""Universe selection: liquid USDT perpetuals with enough history.

The universe is chosen **as of a fixed date** (``as_of``, default: the end of the dev
period) using trailing quote volume measured up to that date. Ranking on today's volume
would leak holdout-period information into which symbols the study covers.

Output: ``config/universe.json`` — small, committed, and the input to every later stage.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from crypto_cross_pred.io import binance

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_WORKERS = 6


@dataclass(frozen=True)
class UniverseEntry:
    """One selected symbol."""

    symbol: str
    base_asset: str
    onboard_date: datetime
    quote_volume_30d: float


def _months_between(start: datetime, end: datetime) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _quote_volume(
    session: requests.Session, symbol: str, end_time: datetime, lookback_days: int
) -> float:
    """Sum of quote volume over the trailing window, using daily klines."""
    try:
        rows = binance.klines(
            session,
            symbol,
            interval="1d",
            start_time=end_time - timedelta(days=lookback_days),
            end_time=end_time,
            limit=lookback_days + 5,
        )
    except binance.BinanceError as error:
        logger.warning("skipping %s: %s", symbol, error)
        return 0.0
    return float(sum(float(row[7]) for row in rows))


def trailing_quote_volume(
    symbols: list[binance.SymbolInfo],
    *,
    as_of: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, float]:
    """Trailing quote volume per symbol, fetched concurrently."""
    session = binance.make_session()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        volumes = pool.map(
            lambda item: (item.symbol, _quote_volume(session, item.symbol, as_of, lookback_days)),
            symbols,
        )
        return dict(volumes)


def select_universe(
    symbols: list[binance.SymbolInfo],
    volumes: dict[str, float],
    *,
    as_of: datetime,
    min_history_months: int,
    max_symbols: int,
    anchor: str,
) -> list[UniverseEntry]:
    """Filter by history, rank by trailing volume, keep the top ``max_symbols``."""
    eligible = [
        item for item in symbols if _months_between(item.onboard_date, as_of) >= min_history_months
    ]
    logger.info(
        "%d symbols have >= %d months of history at %s",
        len(eligible),
        min_history_months,
        as_of.date(),
    )

    ranked = sorted(eligible, key=lambda item: volumes.get(item.symbol, 0.0), reverse=True)
    selected = ranked[:max_symbols]

    by_symbol = {item.symbol: item for item in eligible}
    if anchor in by_symbol and anchor not in {item.symbol for item in selected}:
        logger.warning("%s missing from the top %d; forcing it in", anchor, max_symbols)
        selected = selected[:-1] + [by_symbol[anchor]]

    return [
        UniverseEntry(
            symbol=item.symbol,
            base_asset=item.base_asset,
            onboard_date=item.onboard_date,
            quote_volume_30d=volumes.get(item.symbol, 0.0),
        )
        for item in selected
    ]


def write_universe(
    path: Path,
    entries: list[UniverseEntry],
    *,
    as_of: datetime,
    min_history_months: int,
    lookback_days: int,
    source: str = "binance",
) -> None:
    """Persist the universe as JSON, with the parameters that produced it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "source": source,
        "min_history_months": min_history_months,
        "lookback_days": lookback_days,
        "symbol_count": len(entries),
        "symbols": [
            {
                "symbol": entry.symbol,
                "base_asset": entry.base_asset,
                "onboard_date": entry.onboard_date.isoformat(),
                "quote_volume_30d": round(entry.quote_volume_30d, 2),
            }
            for entry in entries
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_universe(path: Path) -> list[UniverseEntry]:
    """Read a universe file written by :func:`write_universe`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        UniverseEntry(
            symbol=item["symbol"],
            base_asset=item["base_asset"],
            onboard_date=datetime.fromisoformat(item["onboard_date"]),
            quote_volume_30d=float(item["quote_volume_30d"]),
        )
        for item in payload["symbols"]
    ]


def entry_to_dict(entry: UniverseEntry) -> dict[str, Any]:
    """Convenience for logging and tests."""
    return asdict(entry)
