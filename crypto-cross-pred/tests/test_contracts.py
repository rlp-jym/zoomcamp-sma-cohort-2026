"""The contracts module is the single source of truth: guard it."""

import pandas as pd
import pytest

from crypto_cross_pred import contracts


def _valid_frame() -> pd.DataFrame:
    """One row per (symbol, ts), every schema column present."""
    rows = [
        {"symbol": "BTCUSDT", "ts": pd.Timestamp("2025-01-01T00:00Z")},
        {"symbol": "BTCUSDT", "ts": pd.Timestamp("2025-01-01T01:00Z")},
        {"symbol": "ETHUSDT", "ts": pd.Timestamp("2025-01-01T00:00Z")},
    ]
    frame = pd.DataFrame(rows)
    for column in contracts.SCHEMA_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0.0
    return frame[list(contracts.SCHEMA_COLUMNS)]


def test_schema_columns_are_unique() -> None:
    assert len(contracts.SCHEMA_COLUMNS) == len(set(contracts.SCHEMA_COLUMNS))


def test_primary_key_is_in_schema() -> None:
    for column in contracts.PRIMARY_KEY:
        assert column in contracts.SCHEMA


def test_model_inputs_are_unique() -> None:
    assert len(contracts.MODEL_INPUTS) == len(set(contracts.MODEL_INPUTS))


def test_labels_are_not_model_inputs() -> None:
    assert not set(contracts.LABELS) & set(contracts.MODEL_INPUTS)


def test_feature_groups_do_not_overlap() -> None:
    groups = [
        contracts.PRICE_VOLUME_FEATURES,
        contracts.DERIVATIVES_FEATURES,
        contracts.CROSS_SECTIONAL_FEATURES,
        contracts.MARKET_WIDE_FEATURES,
        contracts.MACRO_FEATURES,
    ]
    seen: set[str] = set()
    for group in groups:
        assert not seen & set(group), "a feature appears in two families"
        seen |= set(group)


def test_enough_numeric_features_for_the_rubric() -> None:
    assert len(contracts.NUMERIC) >= 60


def test_validate_schema_accepts_a_valid_frame() -> None:
    contracts.validate_schema(_valid_frame())


def test_validate_schema_rejects_a_missing_column() -> None:
    frame = _valid_frame().drop(columns=["funding_rate"])
    with pytest.raises(ValueError, match="missing schema columns"):
        contracts.validate_schema(frame)


def test_validate_schema_rejects_an_unexpected_column() -> None:
    frame = _valid_frame().assign(surprise=1.0)
    with pytest.raises(ValueError, match="unexpected columns"):
        contracts.validate_schema(frame)


def test_validate_schema_rejects_duplicate_keys() -> None:
    frame = _valid_frame()
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate primary keys"):
        contracts.validate_schema(duplicated)
