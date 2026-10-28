"""Config loads from YAML, validates itself, and lets the environment win."""

from datetime import date

import pytest
from pydantic import ValidationError

from crypto_cross_pred import config


def test_yaml_values_are_loaded() -> None:
    settings = config.get_settings()
    assert settings.dates.dev_start == date(2021, 1, 1)
    assert settings.labels.horizon_hours == 24
    assert settings.costs.taker_bps == 4.0


def test_round_trip_cost_is_two_sides() -> None:
    costs = config.CostConfig(taker_bps=4.0, slippage_bps=2.0)
    assert costs.round_trip_bps == 12.0


def test_paths_resolve_against_the_project_root() -> None:
    resolved = config.get_settings().paths.resolve()
    assert resolved.raw_dir == config.PROJECT_ROOT / "data" / "raw"
    assert resolved.predictions_dir.is_absolute()


def test_dev_period_must_end_before_the_holdout() -> None:
    with pytest.raises(ValidationError, match="must end before the holdout"):
        config.DatesConfig(
            dev_start=date(2021, 1, 1),
            dev_end=date(2025, 12, 1),
            holdout_start=date(2025, 11, 1),
            holdout_end=date(2026, 10, 31),
        )


def test_universe_bounds_are_checked() -> None:
    with pytest.raises(ValidationError, match="min_symbols"):
        config.UniverseConfig(min_symbols=300, max_symbols=200)


def test_clf_quantile_must_be_a_probability() -> None:
    with pytest.raises(ValidationError):
        config.LabelConfig(clf_quantile=1.5)


def test_environment_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_DATASET_REPO", "someone/crypto-cross-pred")
    monkeypatch.setenv("UNIVERSE__MAX_SYMBOLS", "180")
    settings = config.Settings()
    assert settings.hf_dataset_repo == "someone/crypto-cross-pred"
    assert settings.universe.max_symbols == 180


def test_config_file_can_be_overridden(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    custom = tmp_path / "custom.yaml"
    monkeypatch.setenv("CRYPTO_CONFIG_FILE", str(custom))
    assert config.config_file() == custom


def test_data_end_matches_the_holdout_end() -> None:
    settings = config.get_settings()
    assert settings.data_end == settings.dates.holdout_end
