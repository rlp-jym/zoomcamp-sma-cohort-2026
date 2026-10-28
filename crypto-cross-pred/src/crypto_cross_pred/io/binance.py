"""Binance USD-M futures REST client.

Only the endpoints this project needs, with one retry policy shared by all of them.
Rate limits: 429 (rate limit) and 418 (IP ban) back off for ``Retry-After`` seconds;
5xx and connection errors retry with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com"
VISION_URL = "https://data.binance.vision"

KLINES_PATH = "/fapi/v1/klines"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
FUNDING_PATH = "/fapi/v1/fundingRate"
OPEN_INTEREST_PATH = "/futures/data/openInterestHist"
LONG_SHORT_PATH = "/futures/data/globalLongShortAccountRatio"
TAKER_PATH = "/futures/data/takerlongshortRatio"
LIQUIDATIONS_PATH = "/fapi/v1/allForceOrders"

MAX_KLINES_PER_REQUEST = 1500
MAX_FUNDING_PER_REQUEST = 1000


class BinanceError(RuntimeError):
    """Raised when the API keeps failing after the retry budget."""


@dataclass(frozen=True)
class SymbolInfo:
    """One perpetual contract, as reported by ``exchangeInfo``."""

    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str
    status: str
    onboard_date: datetime


def make_session() -> requests.Session:
    """A session with a browser-like user agent, so the CDN does not throttle us."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "crypto-cross-pred/0.1 (research; https://github.com/rlp-jym)",
            "Accept": "application/json",
        }
    )
    return session


def _sleep_for(response: requests.Response, attempt: int) -> float:
    """Seconds to wait before retrying, honouring Retry-After when present."""
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(2.0**attempt, 30.0)


def request_json(
    session: requests.Session,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    base_url: str = BASE_URL,
    max_attempts: int = 4,
    timeout: float = 30.0,
) -> Any:
    """GET ``path`` and return parsed JSON, retrying transient failures."""
    url = f"{base_url}{path}"
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as error:
            last_error = error
            wait = min(2.0**attempt, 30.0)
            logger.warning("request failed (%s), retrying in %.0fs: %s", error, wait, url)
            time.sleep(wait)
            continue

        if response.status_code in {429, 418}:
            wait = _sleep_for(response, attempt)
            logger.warning("rate limited (%s), sleeping %.0fs", response.status_code, wait)
            time.sleep(wait)
            last_error = BinanceError(f"rate limited: {response.status_code}")
            continue

        if 500 <= response.status_code < 600:
            wait = _sleep_for(response, attempt)
            logger.warning("server error %s, retrying in %.0fs", response.status_code, wait)
            time.sleep(wait)
            last_error = BinanceError(f"server error: {response.status_code}")
            continue

        if response.status_code != 200:
            raise BinanceError(f"{url} returned {response.status_code}: {response.text[:200]}")

        return response.json()

    raise BinanceError(f"{url} failed after {max_attempts} attempts: {last_error}")


def parse_symbols(payload: dict[str, Any]) -> list[SymbolInfo]:
    """Filter ``exchangeInfo`` to tradable USDT perpetual contracts."""
    symbols: list[SymbolInfo] = []
    for entry in payload.get("symbols", []):
        if entry.get("contractType") != "PERPETUAL":
            continue
        if entry.get("quoteAsset") != "USDT":
            continue
        if entry.get("status") != "TRADING":
            continue
        symbols.append(
            SymbolInfo(
                symbol=entry["symbol"],
                base_asset=entry.get("baseAsset", ""),
                quote_asset=entry["quoteAsset"],
                contract_type=entry["contractType"],
                status=entry["status"],
                onboard_date=datetime.fromtimestamp(entry["onboardDate"] / 1000, tz=UTC),
            )
        )
    return sorted(symbols, key=lambda item: item.symbol)


def load_symbols(session: requests.Session | None = None) -> list[SymbolInfo]:
    """Fetch and filter the tradable perpetual universe."""
    session = session or make_session()
    payload = request_json(session, EXCHANGE_INFO_PATH)
    return parse_symbols(payload)


def klines(
    session: requests.Session,
    symbol: str,
    *,
    interval: str = "1h",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = MAX_KLINES_PER_REQUEST,
) -> list[list[Any]]:
    """Raw kline rows for one symbol. One request: callers paginate."""
    params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = int(start_time.timestamp() * 1000)
    if end_time is not None:
        params["endTime"] = int(end_time.timestamp() * 1000)
    return request_json(session, KLINES_PATH, params)


def funding_history(
    session: requests.Session,
    symbol: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = MAX_FUNDING_PER_REQUEST,
) -> list[dict[str, Any]]:
    """Funding-rate records for one symbol, oldest first."""
    params: dict[str, Any] = {"symbol": symbol, "limit": limit}
    if start_time is not None:
        params["startTime"] = int(start_time.timestamp() * 1000)
    if end_time is not None:
        params["endTime"] = int(end_time.timestamp() * 1000)
    return request_json(session, FUNDING_PATH, params)
