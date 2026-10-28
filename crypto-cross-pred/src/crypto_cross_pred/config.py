"""Typed configuration, loaded from ``config/config.yaml`` and the environment.

Structural settings (universe, dates, costs, paths) come from YAML. Secrets and
machine-specific values (``HF_TOKEN``, ``HF_DATASET_REPO``) come from the
environment and always win over YAML (AGENTS.md section 7).

Override the config file with ``CRYPTO_CONFIG_FILE=/path/to/config.yaml``.
"""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE: Path = PROJECT_ROOT / "config" / "config.yaml"


def config_file() -> Path:
    """Return the active config file path."""
    return Path(os.environ.get("CRYPTO_CONFIG_FILE", DEFAULT_CONFIG_FILE))


class UniverseConfig(BaseModel):
    quote_asset: str = "USDT"
    contract_type: str = "PERPETUAL"
    anchor_symbol: str = "BTCUSDT"
    min_history_months: int = Field(default=18, ge=0)
    min_symbols: int = Field(default=150, ge=10)
    max_symbols: int = Field(default=250, ge=10)

    @model_validator(mode="after")
    def _check_bounds(self) -> UniverseConfig:
        if self.min_symbols > self.max_symbols:
            raise ValueError("min_symbols must not exceed max_symbols")
        return self


class DatesConfig(BaseModel):
    dev_start: date = date(2021, 1, 1)
    dev_end: date = date(2025, 10, 31)
    holdout_start: date = date(2025, 11, 1)
    holdout_end: date = date(2026, 10, 31)

    @model_validator(mode="after")
    def _check_order(self) -> DatesConfig:
        if not self.dev_start < self.dev_end:
            raise ValueError("dev_start must be before dev_end")
        if self.dev_end >= self.holdout_start:
            raise ValueError("the dev period must end before the holdout starts")
        if not self.holdout_start < self.holdout_end:
            raise ValueError("holdout_start must be before holdout_end")
        return self


class LabelConfig(BaseModel):
    horizon_hours: int = Field(default=24, ge=1)
    clf_quantile: float = Field(default=0.80, gt=0.0, lt=1.0)


class ValidationConfig(BaseModel):
    retrain_frequency: str = "MS"
    embargo_hours: int = Field(default=24, ge=0)


class CostConfig(BaseModel):
    taker_bps: float = Field(default=4.0, ge=0.0)
    slippage_bps: float = Field(default=2.0, ge=0.0)
    funding_interval_hours: int = Field(default=8, ge=1)

    @property
    def round_trip_bps(self) -> float:
        """Cost of opening and closing one position, in basis points."""
        return 2.0 * (self.taker_bps + self.slippage_bps)


class SimulationConfig(BaseModel):
    rebalance_hour_utc: int = Field(default=0, ge=0, le=23)
    top_fraction: float = Field(default=0.10, gt=0.0, lt=1.0)
    vol_target_annual: float = Field(default=0.15, gt=0.0)
    stop_loss_pct: float = Field(default=0.10, gt=0.0, lt=1.0)
    max_positions: int = Field(default=20, ge=1)


class PathsConfig(BaseModel):
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    predictions_dir: Path = Path("data/predictions")
    sim_dir: Path = Path("data/sim")
    artifacts_dir: Path = Path("data/artifacts")

    def resolve(self) -> PathsConfig:
        """Return a copy with every path anchored at the project root."""
        return PathsConfig(
            **{
                name: PROJECT_ROOT / value
                for name, value in self.model_dump().items()
            }
        )


class Settings(BaseSettings):
    """Resolved settings: YAML first, environment overrides."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    universe: UniverseConfig = UniverseConfig()
    dates: DatesConfig = DatesConfig()
    labels: LabelConfig = LabelConfig()
    validation: ValidationConfig = ValidationConfig()
    costs: CostConfig = CostConfig()
    simulation: SimulationConfig = SimulationConfig()
    paths: PathsConfig = PathsConfig()

    # Environment-only: never stored in YAML.
    hf_token: SecretStr = SecretStr("")
    hf_dataset_repo: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=config_file()),
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()
