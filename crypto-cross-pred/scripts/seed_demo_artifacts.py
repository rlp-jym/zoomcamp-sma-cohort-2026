"""Write synthetic predictions and equity curves so the dashboard can be inspected.

The values are **fake**. Nothing here is a result. Files land in the configured data
directories (gitignored) and are overwritten by the first real pipeline run.

Usage::

    uv run python scripts/seed_demo_artifacts.py
    uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_cross_pred import contracts
from crypto_cross_pred.config import get_settings

DAYS = 30
SYMBOLS = 20
SEED = 7


def _symbols() -> list[str]:
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    extra = [f"DEMO{i:02d}USDT" for i in range(SYMBOLS - len(majors))]
    return majors + extra


def _predictions(rng: np.random.Generator, last_day: pd.Timestamp) -> pd.DataFrame:
    timestamps = pd.date_range(end=last_day, periods=DAYS, freq="D", tz="UTC")
    symbols = _symbols()

    rows = []
    for ts in timestamps:
        pred_reg = rng.normal(0.0, 0.02, len(symbols))
        p_top = rng.uniform(0.0, 1.0, len(symbols))
        order = np.argsort(-pred_reg)
        rank = np.empty(len(symbols), dtype=int)
        rank[order] = np.arange(1, len(symbols) + 1)
        decile = np.clip(10 - (rank - 1) * 10 // len(symbols), 1, 10)

        for i, symbol in enumerate(symbols):
            rows.append(
                {
                    "symbol": symbol,
                    "ts": ts,
                    "pred_reg": float(pred_reg[i]),
                    "p_top": float(p_top[i]),
                    "rank_reg": int(rank[i]),
                    "decile": int(decile[i]),
                    **{f"w_{name}": float(rng.normal(0.0, 0.05)) for name in contracts.STRATEGIES},
                }
            )

    return pd.DataFrame(rows)[list(contracts.PREDICTION_COLUMNS)]


def _equity_curve(
    rng: np.random.Generator, last_day: pd.Timestamp, drift: float, vol: float
) -> pd.DataFrame:
    timestamps = pd.date_range(end=last_day, periods=DAYS * 6, freq="4h", tz="UTC")
    net_ret = rng.normal(drift, vol, len(timestamps))
    equity = np.cumprod(1.0 + net_ret)

    return pd.DataFrame(
        {
            "ts": timestamps,
            "equity": equity,
            "gross_ret": net_ret + 0.0001,
            "net_ret": net_ret,
            "turnover": np.abs(rng.normal(0.2, 0.05, len(timestamps))),
            "n_positions": rng.integers(4, SYMBOLS, len(timestamps)),
            "net_exposure": rng.normal(0.0, 0.02, len(timestamps)),
        }
    )[list(contracts.SIM_EQUITY_COLUMNS)]


def main() -> int:
    """Write the demo artifacts and report where they went."""
    rng = np.random.default_rng(SEED)
    paths = get_settings().paths.resolve()
    last_day = pd.Timestamp.now(tz="UTC").normalize()

    paths.predictions_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = paths.predictions_dir / f"{last_day:%Y-%m-%d}.parquet"
    predictions = _predictions(rng, last_day)
    predictions.to_parquet(predictions_path, index=False)

    paths.sim_dir.mkdir(parents=True, exist_ok=True)
    curves = {
        "sim0": (0.0004, 0.010),
        "sim1": (0.0006, 0.012),
        "sim2": (0.0009, 0.011),
        "sim3": (0.0012, 0.008),
        "btc_hodl": (0.0010, 0.020),
        "ew_basket": (0.0007, 0.016),
        "cash": (0.0, 0.0),
    }
    for name, (drift, vol) in curves.items():
        curve = _equity_curve(rng, last_day, drift, vol)
        curve.to_parquet(paths.sim_dir / f"{name}_{last_day:%Y-%m-%d}.parquet", index=False)

    print(f"wrote {len(predictions):,} prediction rows -> {predictions_path}")
    print(f"wrote {len(curves)} equity curves -> {paths.sim_dir}")
    print("these values are synthetic; the first real run overwrites them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
