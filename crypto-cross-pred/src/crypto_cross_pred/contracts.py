"""Single source of truth for the dataset schema and the model feature sets.

Everything that reads or writes the unified dataset imports from here. Never
redefine these lists in a notebook or another module (AGENTS.md section 4).

- Schema: docs/SPEC.md section 4.2
- Feature families: docs/SPEC.md section 4.3
- Labels: docs/SPEC.md section 4.4
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

PRIMARY_KEY: tuple[str, str] = ("symbol", "ts")

#: Column name -> description. Insertion order is the canonical column order.
SCHEMA: dict[str, str] = {
    "symbol": "contract symbol, e.g. BTCUSDT",
    "ts": "UTC bar open time, hourly",
    "open": "open price from klines",
    "high": "high price from klines",
    "low": "low price from klines",
    "close": "close price from klines",
    "volume": "base-asset volume from klines",
    "quote_volume": "quote-asset volume from klines",
    "trades": "number of trades in the bar",
    "taker_buy_volume": "taker buy base volume",
    "taker_buy_quote_volume": "taker buy quote volume",
    "funding_rate": "current funding rate (8h cadence, forward-filled)",
    "open_interest": "open interest",
    "ls_ratio_account": "long/short account ratio",
    "ls_ratio_position": "long/short position ratio",
    "fng": "Fear & Greed index, 0-100",
    "vix": "CBOE VIX close (lagged 1 day)",
    "dgs10": "10Y Treasury yield, percent (lagged 1 day)",
    "dff": "effective fed funds rate, percent (lagged 1 day)",
    "dxy": "broad dollar index (lagged 1 day)",
    "credit_spread": "Moody's Baa yield minus 10Y Treasury, percent (lagged 1 day)",
}

SCHEMA_COLUMNS: tuple[str, ...] = tuple(SCHEMA)

# --- Feature families (docs/SPEC.md section 4.3) ---------------------------------

PRICE_VOLUME_FEATURES: tuple[str, ...] = (
    "ret_1h",
    "ret_4h",
    "ret_24h",
    "ret_7d",
    "log_volume",
    "volume_z_24h",
    "volume_ratio_24h_7d",
    "taker_buy_ratio",
    "taker_buy_ratio_ma_24h",
    "trades_z_24h",
    "avg_trade_size",
    "hl_range",
    "parkinson_vol_24h",
    "realized_vol_24h",
    "vol_ratio_24h_7d",
    "close_to_high_24h",
    "close_to_low_24h",
    "dist_high_30d",
    "dist_low_30d",
    "rsi_14",
    "macd_hist",
    "ma_ratio_24h",
    "ma_ratio_7d",
    "skew_24h",
    "kurt_24h",
    "autocorr_1h_24h",
)

DERIVATIVES_FEATURES: tuple[str, ...] = (
    "funding_rate",
    "funding_ma_8",
    "funding_z_7d",
    "funding_cum_24h",
    "oi_change_1h",
    "oi_change_24h",
    "oi_z_7d",
    "oi_to_volume",
    "ls_ratio_account",
    "ls_ratio_position",
    "ls_ratio_z_7d",
)

CROSS_SECTIONAL_FEATURES: tuple[str, ...] = (
    "cs_rank_ret_24h",
    "cs_rank_vol_24h",
    "cs_rank_funding",
    "cs_rank_oi_change",
    "cs_z_ret_24h",
    "cs_demeaned_ret_24h",
    "beta_to_btc_7d",
    "corr_to_btc_7d",
    "resid_mom_24h",
)

MARKET_WIDE_FEATURES: tuple[str, ...] = (
    "btc_ret_1h",
    "btc_ret_24h",
    "btc_realized_vol_24h",
    "market_breadth",
    "market_dispersion",
    "avg_funding_all",
    "fng",
    "fng_change_7d",
    "fng_z_30d",
)

# `macro_risk_off` lives in DUMMIES, not here, because it is a 0/1 flag.
MACRO_FEATURES: tuple[str, ...] = (
    "vix_level",
    "vix_z_30d",
    "vix_change_1d",
    "yield_10y",
    "yield_change_5d",
    "term_spread",
    "dxy_ret_5d",
    "credit_spread_level",
    "credit_spread_z_30d",
    "credit_spread_change_5d",
)

DUMMIES: tuple[str, ...] = (
    "is_weekend",
    "macro_risk_off",
)

CATEGORICAL: tuple[str, ...] = (
    "symbol",
    "hour_of_day",
    "day_of_week",
    "vol_regime",
    "funding_regime",
)


def _dedupe(*groups: Iterable[str]) -> tuple[str, ...]:
    """Concatenate feature groups, keeping first occurrence order."""
    return tuple(dict.fromkeys(name for group in groups for name in group))


NUMERIC: tuple[str, ...] = _dedupe(
    PRICE_VOLUME_FEATURES,
    DERIVATIVES_FEATURES,
    CROSS_SECTIONAL_FEATURES,
    MARKET_WIDE_FEATURES,
    MACRO_FEATURES,
)

#: Everything a model may read. Labels are never part of this tuple.
MODEL_INPUTS: tuple[str, ...] = NUMERIC + DUMMIES + CATEGORICAL

# --- Labels (docs/SPEC.md section 4.4) -------------------------------------------

TO_PREDICT_REG: tuple[str, ...] = ("cs_excess_ret_24h",)
TO_PREDICT_CLF: tuple[str, ...] = ("is_top_quintile",)
LABELS: tuple[str, ...] = ("fwd_ret_24h",) + TO_PREDICT_REG + TO_PREDICT_CLF

# --- Artifacts (docs/SPEC.md section 8.1) ----------------------------------------

STRATEGIES: tuple[str, ...] = ("sim0", "sim1", "sim2", "sim3")
BENCHMARKS: tuple[str, ...] = ("btc_hodl", "ew_basket", "cash")

WEIGHT_COLUMNS: tuple[str, ...] = tuple(f"w_{name}" for name in STRATEGIES)

PREDICTION_COLUMNS: tuple[str, ...] = (
    "symbol",
    "ts",
    "pred_reg",
    "p_top",
    "rank_reg",
    "decile",
) + WEIGHT_COLUMNS

SIM_EQUITY_COLUMNS: tuple[str, ...] = (
    "ts",
    "equity",
    "gross_ret",
    "net_ret",
    "turnover",
    "n_positions",
    "net_exposure",
)


def missing_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return the schema columns absent from ``df``, in canonical order."""
    return tuple(column for column in SCHEMA_COLUMNS if column not in df.columns)


def unexpected_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return columns of ``df`` that are not part of the unified schema."""
    return tuple(column for column in df.columns if column not in SCHEMA)


def validate_schema(df: pd.DataFrame) -> None:
    """Raise ``ValueError`` if ``df`` does not match the unified schema exactly."""
    missing = missing_columns(df)
    if missing:
        raise ValueError(f"missing schema columns: {list(missing)}")
    unexpected = unexpected_columns(df)
    if unexpected:
        raise ValueError(f"unexpected columns: {list(unexpected)}")
    duplicates = df.duplicated(subset=list(PRIMARY_KEY))
    if duplicates.any():
        raise ValueError(f"duplicate primary keys: {int(duplicates.sum())} rows")
