"""Fit, persist and load the random forest, plus the KPI stats the alert quotes."""

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from . import config

MODEL_FILE = config.LOCAL / "model.joblib"
RANDOM_STATE = 9
DEV_SHARE = 0.8  # train + validation, matching the notebook's final refit


def labelled(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows with a realised forward return; the newest sessions have no label yet."""
    return frame.dropna(subset=[config.TARGET])


def dev_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = labelled(frame)
    cut = int(len(frame) * DEV_SHARE)
    return frame.iloc[:cut], frame.iloc[cut:]


def fit(frame: pd.DataFrame) -> tuple[RandomForestRegressor, dict]:
    dev, _test = dev_split(frame)
    model = RandomForestRegressor(
        n_estimators=300, max_depth=8, min_samples_leaf=10,
        max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
    )
    model.fit(dev[config.FEATURES], dev[config.TARGET])
    joblib.dump(model, MODEL_FILE)
    return model, segment_stats(model, frame)


def load() -> RandomForestRegressor:
    return joblib.load(MODEL_FILE)


def segment_stats(model: RandomForestRegressor, frame: pd.DataFrame) -> dict:
    """Validation-slice stats for days the model scores above the threshold."""
    _train, valid = dev_split(frame)
    preds = model.predict(valid[config.FEATURES])
    taken = preds > config.THRESHOLD
    realised = valid.loc[taken, config.TARGET]

    if len(realised) == 0:
        return {"days": 0, "expectancy": float("nan"), "hit_rate": float("nan")}

    return {
        "days": int(taken.sum()),
        "expectancy": float(realised.mean()),
        "hit_rate": float((realised > 0).mean()),
    }


def vote_share(model: RandomForestRegressor, row: pd.DataFrame) -> float:
    """Share of trees predicting a positive 5-day return for this row."""
    votes = [tree.predict(row[config.FEATURES].to_numpy())[0] > 0
             for tree in model.estimators_]
    return float(np.mean(votes))
