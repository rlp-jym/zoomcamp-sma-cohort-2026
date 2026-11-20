"""Feature engineering: per-issuer indicators, breadth aggregates, 5-day target.

This mirrors the notebook exactly. Keeping one implementation matters: the cron
and the research study must score the same row with the same numbers.
"""

import numpy as np
import pandas as pd
import talib

from . import config

PERIODS = config.PERIODS
FEATURES = config.FEATURES
TARGET = config.TARGET


def spy_frame(spy: pd.DataFrame) -> pd.DataFrame:
    """SPY indicators: SMA, RSI, ATR, forward returns, ATR-normalised target."""
    spy = spy.copy()
    spy["turnover_value"] = (spy["close"] * spy["volume"]).astype("int64")

    for n, tf in PERIODS:
        spy[f"chg_{tf}"] = ((spy["close"].shift(-n) / spy["close"]) - 1) * 100
        spy[f"atr_{tf}"] = talib.ATR(spy["high"].values, spy["low"].values,
                                     spy["close"].values, timeperiod=n)
        spy[f"sma_{tf}"] = talib.SMA(spy["close"].values, timeperiod=n)
        spy[f"atr_{tf}_pct"] = spy[f"atr_{tf}"] / spy["close"] * 100
        if n > 1:
            spy[f"rsi_{tf}"] = talib.RSI(spy["close"].values, timeperiod=n)
            spy[f"rel_sma_{tf}"] = ((spy["close"] / spy[f"sma_{tf}"]) - 1) * 100

    for n, tf in PERIODS:
        if n == 1:
            continue
        spy[f"rel_sma_{tf}_atr"] = spy[f"rel_sma_{tf}"] / spy["atr_20d_pct"]

    for n, tf in PERIODS:
        spy[f"rr_{tf}"] = spy[f"chg_{tf}"] / spy["atr_20d_pct"]

    return spy


def enrich(base: pd.DataFrame, start: str = "2014-01-01") -> pd.DataFrame:
    """Per-issuer SMA/RSI/ATR, returns and 52-week extremes on the long table."""
    c = base[base["date"] >= start].copy()
    c["date"] = pd.to_datetime(c["date"])

    close_wide = c.pivot(index="date", columns="issuer_id", values="close")
    high_wide = c.pivot(index="date", columns="issuer_id", values="high")
    low_wide = c.pivot(index="date", columns="issuer_id", values="low")

    wide = {}
    for n, tf in PERIODS:
        sma, rsi, atr = {}, {}, {}
        for col in close_wide.columns:
            s = close_wide[col].dropna()
            idx = s.index
            sma[col] = pd.Series(talib.SMA(s.values, n), index=idx)
            if n > 1:
                rsi[col] = pd.Series(talib.RSI(s.values, n), index=idx)
            atr[col] = pd.Series(
                talib.ATR(high_wide[col].reindex(idx).values,
                          low_wide[col].reindex(idx).values, s.values, n),
                index=idx,
            )

        sma_df = pd.DataFrame(sma).reindex(index=close_wide.index, columns=close_wide.columns)
        atr_df = pd.DataFrame(atr).reindex(index=close_wide.index, columns=close_wide.columns)

        wide[f"sma_{tf}"] = sma_df
        wide[f"rel_sma_{tf}"] = (close_wide / sma_df - 1) * 100
        wide[f"atr_{tf}"] = atr_df
        wide[f"atr_{tf}_pct"] = atr_df / close_wide * 100
        wide[f"ret_{tf}"] = close_wide.pct_change(n) * 100
        if rsi:
            wide[f"rsi_{tf}"] = pd.DataFrame(rsi).reindex(index=close_wide.index,
                                                          columns=close_wide.columns)

    for n, tf in PERIODS:
        if n == 1:
            continue
        wide[f"rel_sma_{tf}_atr"] = wide[f"rel_sma_{tf}"] / wide["atr_20d_pct"]

    for label, window in {"13w": 65, "26w": 130, "52w": 252}.items():
        hi = close_wide.rolling(window, min_periods=window).max()
        lo = close_wide.rolling(window, min_periods=window).min()
        wide[f"high_{label}"] = (close_wide >= hi).astype(float).where(hi.notna())
        wide[f"low_{label}"] = (close_wide <= lo).astype(float).where(lo.notna())

    flat = pd.MultiIndex.from_product([close_wide.index, close_wide.columns],
                                      names=["date", "issuer_id"])
    long = pd.DataFrame({k: v.to_numpy().ravel() for k, v in wide.items()}, index=flat)

    c = c.drop(columns=[col for col in wide if col in c.columns], errors="ignore")
    c = c.set_index(["date", "issuer_id"]).join(long).reset_index()
    c["turnover_value"] = c["volume"] * c["close"]
    return c


def breadth(c: pd.DataFrame) -> pd.DataFrame:
    """Weighted share of the index in each state, plus breadth momentum and turnover."""
    out = pd.DataFrame(index=sorted(c["date"].unique()))
    out.index.name = "date"

    for n, tf in PERIODS:
        if n == 1:
            continue
        above = (c["close"] > c[f"sma_{tf}"]).astype(float)
        above = above.where(c[f"sma_{tf}"].notna() & c["close"].notna())
        tmp = pd.DataFrame({"x": above * c["index_weight"],
                            "w": c["index_weight"].where(above.notna())})
        agg = tmp.groupby(c["date"]).sum()
        out[f"breadth_sma_{tf}"] = agg["x"] / agg["w"] * 100

        up = (c[f"ret_{tf}"] > 0).astype(float).where(c[f"ret_{tf}"].notna())
        tmp = pd.DataFrame({"x": up * c["index_weight"],
                            "w": c["index_weight"].where(up.notna())})
        agg = tmp.groupby(c["date"]).sum()
        out[f"breadth_adv_dec_{tf}"] = agg["x"] / agg["w"] * 100

        for label, flag in (("rsi70", c[f"rsi_{tf}"] > 70), ("rsi30", c[f"rsi_{tf}"] < 30)):
            hit = flag.astype(float).where(c[f"rsi_{tf}"].notna())
            tmp = pd.DataFrame({"x": hit * c["index_weight"],
                                "w": c["index_weight"].where(hit.notna())})
            agg = tmp.groupby(c["date"]).sum()
            out[f"breadth_{label}_{tf}"] = agg["x"] / agg["w"] * 100

    for name in ("high_13w", "low_13w", "high_26w", "low_26w", "high_52w", "low_52w"):
        hit = c[name].where(c[name].notna())
        tmp = pd.DataFrame({"x": hit.fillna(0) * c["index_weight"],
                            "w": c["index_weight"].where(hit.notna())})
        agg = tmp.groupby(c["date"]).sum()
        out[f"breadth_{name}"] = agg["x"] / agg["w"] * 100

    for tf in ("5d", "20d", "60d"):
        out[f"breadth_sma_{tf}_chg_5d"] = out[f"breadth_sma_{tf}"].diff(5)

    turnover = c.groupby("date")["turnover_value"].sum()
    out["breadth_turnover_rel_60d"] = turnover / turnover.rolling(60).mean()
    return out


def medians(c: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional medians and dispersion for distance, RSI and ATR%."""
    out = pd.DataFrame(index=sorted(c["date"].unique()))
    out.index.name = "date"

    for n, tf in PERIODS:
        if n == 1:
            continue
        rel = c.pivot(index="date", columns="issuer_id", values=f"rel_sma_{tf}")
        rsi = c.pivot(index="date", columns="issuer_id", values=f"rsi_{tf}")
        atr = c.pivot(index="date", columns="issuer_id", values=f"atr_{tf}_pct")
        rel_atr = c.pivot(index="date", columns="issuer_id", values=f"rel_sma_{tf}_atr")

        out[f"med_rel_sma_{tf}"] = rel.median(axis=1)
        out[f"iqr_rel_sma_{tf}"] = rel.quantile(0.75, axis=1) - rel.quantile(0.25, axis=1)
        out[f"med_rel_sma_{tf}_atr"] = rel_atr.median(axis=1)
        out[f"med_rsi_{tf}"] = rsi.median(axis=1)
        out[f"med_atr_pct_{tf}"] = atr.median(axis=1)
    return out


def build_frame(base: pd.DataFrame, spy: pd.DataFrame) -> pd.DataFrame:
    """Modelling frame: SPY row + breadth + medians, target rr_5d, all features present."""
    c = enrich(base)
    b = breadth(c)
    m = medians(c)

    spy = spy_frame(spy)
    df = spy.merge(b, left_on="date", right_index=True, how="inner")
    df = df.sort_values("date").reset_index(drop=True)
    df = df.merge(m, left_on="date", right_index=True, how="left")

    df = df.set_index("date")
    # keep the last sessions even though rr_5d is still unknown: they are what we score
    return df.dropna(subset=FEATURES).copy()


def latest_row(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[-1]


def format_feature(name: str, value: float) -> str:
    """Human units for the alert: breadth is a percent, distance is ATR, RSI is a level."""
    if name == "breadth_turnover_rel_60d":
        return f"{value:.2f}x"
    if name.endswith("_chg_5d"):
        return f"{value:+.1f}pp"
    if name.startswith("med_rel_sma") and name.endswith("_atr"):
        return f"{value:+.2f} ATR"
    if name.startswith("med_rsi"):
        return f"{value:.0f}"
    if name.startswith("med_atr_pct"):
        return f"{value:.2f}%"
    if name.startswith(("breadth_", "iqr_rel_sma", "med_rel_sma")):
        return f"{value:.0f}%"
    return f"{value:.2f}"
