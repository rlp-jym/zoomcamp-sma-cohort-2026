"""Universe selection: history filter, volume ranking, anchor, and cap."""

from datetime import UTC, datetime

from crypto_cross_pred.data import universe
from crypto_cross_pred.io.binance import SymbolInfo

AS_OF = datetime(2025, 10, 31, tzinfo=UTC)


def _symbol(symbol: str, onboard: datetime) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        base_asset=symbol.removesuffix("USDT"),
        quote_asset="USDT",
        contract_type="PERPETUAL",
        status="TRADING",
        onboard_date=onboard,
    )


def _universe(volumes: dict[str, float], onboard: dict[str, datetime], max_symbols: int = 250):
    symbols = [_symbol(name, onboard[name]) for name in volumes]
    return universe.select_universe(
        symbols,
        volumes,
        as_of=AS_OF,
        min_history_months=18,
        max_symbols=max_symbols,
        anchor="BTCUSDT",
    )


def test_short_history_is_excluded() -> None:
    onboard = {
        "OLDUSDT": datetime(2021, 1, 1, tzinfo=UTC),
        "NEWUSDT": datetime(2025, 6, 1, tzinfo=UTC),
    }
    volumes = {"OLDUSDT": 1.0, "NEWUSDT": 100.0}

    selected = _universe(volumes, onboard)

    assert [entry.symbol for entry in selected] == ["OLDUSDT"]


def test_ranking_is_by_volume_descending() -> None:
    onboard = {name: datetime(2021, 1, 1, tzinfo=UTC) for name in ("AUSDT", "BUSDT", "CUSDT")}
    volumes = {"AUSDT": 5.0, "BUSDT": 50.0, "CUSDT": 500.0}

    selected = _universe(volumes, onboard)

    assert [entry.symbol for entry in selected] == ["CUSDT", "BUSDT", "AUSDT"]


def test_max_symbols_caps_the_list() -> None:
    onboard = {f"S{i}USDT": datetime(2021, 1, 1, tzinfo=UTC) for i in range(10)}
    volumes = {name: float(i) for i, name in enumerate(onboard)}

    assert len(_universe(volumes, onboard, max_symbols=3)) == 3


def test_anchor_is_forced_in_when_it_falls_outside_the_cap() -> None:
    onboard = {f"S{i}USDT": datetime(2021, 1, 1, tzinfo=UTC) for i in range(5)}
    onboard["BTCUSDT"] = datetime(2019, 9, 8, tzinfo=UTC)
    volumes = {**{f"S{i}USDT": 100.0 + i for i in range(5)}, "BTCUSDT": 1.0}

    selected = _universe(volumes, onboard, max_symbols=3)

    assert len(selected) == 3
    assert "BTCUSDT" in {entry.symbol for entry in selected}


def test_universe_round_trips_through_json(tmp_path) -> None:
    onboard = {"BTCUSDT": datetime(2019, 9, 8, tzinfo=UTC)}
    entries = _universe({"BTCUSDT": 12.5}, onboard)
    path = tmp_path / "universe.json"

    universe.write_universe(
        path,
        entries,
        as_of=AS_OF,
        min_history_months=18,
        lookback_days=30,
    )
    loaded = universe.load_universe(path)

    assert loaded == entries
