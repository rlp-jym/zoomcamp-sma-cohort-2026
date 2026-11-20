"""Paths, feature list and environment for the daily signal pipeline."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local_data"
DOCS = ROOT / "docs"
LOCAL.mkdir(exist_ok=True)

RELEASE = "https://github.com/rlp-jym/zoomcamp-sma-cohort-2026/releases/download/v0.1-data"
CONSTITUENTS_URL = f"{RELEASE}/sp500_constituents_daily.parquet"
SPY_URL = f"{RELEASE}/SPY.parquet"

PERIODS = [(1, "1d"), (5, "5d"), (20, "20d"), (60, "60d")]

FEATURES = [
    "breadth_sma_5d", "breadth_sma_20d", "breadth_sma_60d",
    "breadth_rsi70_5d", "breadth_rsi70_20d",
    "breadth_rsi30_5d", "breadth_rsi30_20d",
    "med_rel_sma_5d_atr", "med_rel_sma_20d_atr", "med_rel_sma_60d_atr",
    "med_rsi_5d", "med_rsi_20d", "med_rsi_60d",
    "med_atr_pct_5d", "med_atr_pct_20d", "med_atr_pct_60d",
    "breadth_adv_dec_5d", "breadth_adv_dec_20d", "breadth_adv_dec_60d",
    "breadth_high_13w", "breadth_low_13w",
    "breadth_high_26w", "breadth_low_26w",
    "breadth_high_52w", "breadth_low_52w",
    "breadth_sma_5d_chg_5d", "breadth_sma_20d_chg_5d", "breadth_sma_60d_chg_5d",
    "iqr_rel_sma_5d", "iqr_rel_sma_20d", "iqr_rel_sma_60d",
    "breadth_turnover_rel_60d",
]

TARGET = "rr_5d"

FEATURE_NOTES = {
    "breadth_sma_5d": "weighted share above their 5-day average",
    "breadth_sma_20d": "weighted share above their 20-day average",
    "breadth_sma_60d": "weighted share above their 60-day average",
    "breadth_rsi70_5d": "weighted share with RSI above 70",
    "breadth_rsi70_20d": "weighted share with RSI above 70, 20-day",
    "breadth_rsi30_5d": "weighted share with RSI below 30",
    "breadth_rsi30_20d": "weighted share with RSI below 30, 20-day",
    "med_rel_sma_5d_atr": "median distance from 5-day average, in ATR",
    "med_rel_sma_20d_atr": "median distance from 20-day average, in ATR",
    "med_rel_sma_60d_atr": "median distance from 60-day average, in ATR",
    "med_rsi_5d": "median constituent RSI, 5-day",
    "med_rsi_20d": "median constituent RSI, 20-day",
    "med_rsi_60d": "median constituent RSI, 60-day",
    "med_atr_pct_5d": "median 5-day ATR across constituents",
    "med_atr_pct_20d": "median 20-day ATR across constituents",
    "med_atr_pct_60d": "median 60-day ATR across constituents",
    "breadth_adv_dec_5d": "weighted share with a positive 5-day return",
    "breadth_adv_dec_20d": "weighted share with a positive 20-day return",
    "breadth_adv_dec_60d": "weighted share with a positive 60-day return",
    "breadth_high_13w": "weighted share at a 13-week high",
    "breadth_low_13w": "weighted share at a 13-week low",
    "breadth_high_26w": "weighted share at a 26-week high",
    "breadth_low_26w": "weighted share at a 26-week low",
    "breadth_high_52w": "weighted share at a 52-week high",
    "breadth_low_52w": "weighted share at a 52-week low",
    "breadth_sma_5d_chg_5d": "5-day change in 5-day breadth",
    "breadth_sma_20d_chg_5d": "5-day change in 20-day breadth",
    "breadth_sma_60d_chg_5d": "5-day change in 60-day breadth",
    "iqr_rel_sma_5d": "spread of distance from trend, 5-day",
    "iqr_rel_sma_20d": "spread of distance from trend, 20-day",
    "iqr_rel_sma_60d": "spread of distance from trend, 60-day",
    "breadth_turnover_rel_60d": "index turnover versus its 60-day norm",
}

RISK_LEVELS = (0.25, 0.50, 1.00)


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env without adding a dependency."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

THRESHOLD = float(os.environ.get("SIGNAL_THRESHOLD", "0.0"))
TIMEZONE = os.environ.get("SIGNAL_TIMEZONE", "America/New_York")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
