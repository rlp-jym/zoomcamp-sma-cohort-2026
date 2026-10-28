"""exchangeInfo parsing must keep only tradable USDT perpetuals."""

from datetime import UTC, datetime

from crypto_cross_pred.io import binance

ONBOARD_MS = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1000)


def _entry(symbol: str, **overrides) -> dict:
    entry = {
        "symbol": symbol,
        "baseAsset": symbol.removesuffix("USDT"),
        "quoteAsset": "USDT",
        "contractType": "PERPETUAL",
        "status": "TRADING",
        "onboardDate": ONBOARD_MS,
    }
    entry.update(overrides)
    return entry


def test_keeps_only_perpetual_usdt_trading() -> None:
    payload = {
        "symbols": [
            _entry("BTCUSDT"),
            _entry("ETHUSDT"),
            _entry("BTCUSDC", quoteAsset="USDC"),
            _entry("BTCUSDT_250627", contractType="CURRENT_QUARTER"),
            _entry("OLDUSDT", status="SETTLING"),
        ]
    }

    symbols = binance.parse_symbols(payload)

    assert [item.symbol for item in symbols] == ["BTCUSDT", "ETHUSDT"]
    assert all(item.quote_asset == "USDT" for item in symbols)


def test_onboard_date_is_utc() -> None:
    symbols = binance.parse_symbols({"symbols": [_entry("BTCUSDT")]})

    onboard = symbols[0].onboard_date
    assert onboard.tzinfo is not None
    assert onboard == datetime(2020, 1, 1, tzinfo=UTC)


def test_symbols_are_sorted() -> None:
    payload = {"symbols": [_entry("SOLUSDT"), _entry("BTCUSDT"), _entry("ETHUSDT")]}

    assert [item.symbol for item in binance.parse_symbols(payload)] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    ]
