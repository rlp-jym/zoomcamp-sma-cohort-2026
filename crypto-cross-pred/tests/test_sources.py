"""Fear & Greed and FRED parsing, without touching the network."""

from datetime import date

import pandas as pd
import pytest

from crypto_cross_pred.io import fear_greed, fred


def test_fear_greed_parses_and_deduplicates() -> None:
    payload = {
        "data": [
            {"value": "72", "timestamp": "1704153600", "value_classification": "Greed"},
            {"value": "30", "timestamp": "1704067200", "value_classification": "Fear"},
            {"value": "99", "timestamp": "1704067200", "value_classification": "Greed"},
        ]
    }

    frame = fear_greed.parse_payload(payload)

    assert list(frame.columns) == ["ts", "fng"]
    assert frame["ts"].is_monotonic_increasing
    assert len(frame) == 2
    # the later duplicate wins
    assert frame.loc[frame["ts"] == pd.Timestamp("2024-01-01T00:00Z"), "fng"].item() == 99.0


def test_fear_greed_empty_payload() -> None:
    assert fear_greed.parse_payload({"data": []}).empty


def test_fred_series_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = pd.DataFrame(
        {"VIXCLS": [18.2, None, 19.4]},
        index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-04"]),
    )
    monkeypatch.setattr(fred.web, "DataReader", lambda *args, **kwargs: raw)

    series = fred.fetch_series("VIXCLS", date(2025, 1, 1), date(2025, 1, 5))

    assert series.name == "VIXCLS"
    assert len(series) == 2  # the NaN row is dropped
    assert series.index.tz is not None


def test_fred_join_keeps_dates_and_names(monkeypatch: pytest.MonkeyPatch) -> None:
    index = pd.to_datetime(["2025-01-02", "2025-01-03"], utc=True)

    def fake(series_id: str, start: date, end: date) -> pd.Series:
        return pd.Series([1.0, 2.0], index=index, name=series_id)

    monkeypatch.setattr(fred, "fetch_series", fake)

    frame = fred.fetch_all(date(2025, 1, 1), date(2025, 1, 5))

    assert list(frame.columns) == ["ts", *fred.SERIES]
    assert len(frame) == 2
    assert frame["credit_spread"].notna().all()


def test_series_mapping_matches_the_schema() -> None:
    from crypto_cross_pred import contracts

    for name in fred.SERIES:
        assert name in contracts.SCHEMA
