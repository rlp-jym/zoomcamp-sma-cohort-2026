"""Progress dashboard. Read-only: it renders artifacts, it never computes a signal.

Run with::

    uv run streamlit run app/streamlit_app.py

Every panel has an empty state, so the app is useful from day one and fills in as
the pipeline produces files (docs/SPEC.md section 8.1).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from crypto_cross_pred.config import get_settings
from crypto_cross_pred.io.artifacts import (
    artifact_status,
    load_predictions,
    load_sim_curves,
    newest_artifact_mtime,
    summarize_dataset,
)

NEXT_STEP: dict[str, str] = {
    "raw": "cli download --source binance",
    "processed": "cli transform",
    "predictions": "cli train, then cli predict",
    "sim": "cli simulate",
}


@st.cache_data(ttl=60)
def _status() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "artifact": info.name,
                "files": info.files,
                "rows": info.rows,
                "latest": info.latest_name,
            }
            for info in artifact_status()
        ]
    )


@st.cache_data(ttl=60)
def _dataset():
    return summarize_dataset()


@st.cache_data(ttl=60)
def _predictions() -> pd.DataFrame | None:
    return load_predictions()


@st.cache_data(ttl=60)
def _curves() -> dict[str, pd.DataFrame]:
    return load_sim_curves()


def _empty(message: str, command: str) -> None:
    """Show a placeholder; the caller returns so other tabs still render."""
    st.info(f"{message}\n\nRun `{command}`.")


def _render_status() -> None:
    status = _status()
    st.subheader("Artifacts on disk")
    st.dataframe(status, width="stretch", hide_index=True)

    written = newest_artifact_mtime()
    if written is None:
        st.warning("Nothing written yet. Start with the download stage.")
        return

    st.caption(f"Newest artifact: {written:%Y-%m-%d %H:%M:%S} UTC")

    missing = status.loc[status["files"] == 0, "artifact"].tolist()
    if missing:
        first = missing[0]
        st.info(f"Next up: `{NEXT_STEP[first]}` (produces `{first}`).")


def _render_dataset() -> None:
    summary = _dataset()
    if summary is None:
        _empty("No processed dataset yet.", NEXT_STEP["processed"])
        return

    left, middle, right = st.columns(3)
    left.metric("Rows", f"{summary.rows:,}")
    middle.metric("Symbols", f"{summary.symbols:,}")
    right.metric(
        "Coverage",
        f"{summary.start:%Y-%m-%d} → {summary.end:%Y-%m-%d}"
        if summary.start is not None and summary.end is not None
        else "-",
    )

    coverage = summary.rows_per_symbol.head(30).rename_axis("symbol").reset_index(name="rows")
    figure = px.bar(
        coverage,
        x="symbol",
        y="rows",
        title="Rows per symbol (top 30)",
    )
    st.plotly_chart(figure, width="stretch")


def _render_predictions() -> None:
    predictions = _predictions()
    if predictions is None or predictions.empty:
        _empty("No predictions yet.", NEXT_STEP["predictions"])
        return

    latest_ts = pd.to_datetime(predictions["ts"], utc=True).max()
    current = predictions.loc[pd.to_datetime(predictions["ts"], utc=True) == latest_ts]

    left, middle, right = st.columns(3)
    left.metric("Decision time", f"{latest_ts:%Y-%m-%d %H:%M} UTC")
    middle.metric("Symbols scored", f"{len(current):,}")
    right.metric("Mean p_top", f"{current['p_top'].mean():.3f}")

    columns = [column for column in ("symbol", "pred_reg", "p_top", "decile") if column in current]
    ordered = current.sort_values("pred_reg", ascending=False)

    top, bottom = st.columns(2)
    with top:
        st.caption("Highest predicted excess return")
        st.dataframe(ordered[columns].head(10), width="stretch", hide_index=True)
    with bottom:
        st.caption("Lowest predicted excess return")
        st.dataframe(ordered[columns].tail(10), width="stretch", hide_index=True)

    figure = px.histogram(current, x="p_top", nbins=40, title="p_top distribution")
    st.plotly_chart(figure, width="stretch")


def _render_simulation() -> None:
    curves = _curves()
    if not curves:
        _empty("No simulation output yet.", NEXT_STEP["sim"])
        return

    frames = []
    for name, frame in curves.items():
        if "ts" not in frame or "equity" not in frame:
            continue
        frames.append(frame.assign(strategy=name)[["ts", "equity", "strategy"]])

    if not frames:
        st.warning("Simulation files exist but none carry `ts` and `equity` (SPEC section 8.1).")
        return

    combined = pd.concat(frames, ignore_index=True)
    figure = px.line(
        combined,
        x="ts",
        y="equity",
        color="strategy",
        title="Equity curves",
    )
    st.plotly_chart(figure, width="stretch")

    table = (
        combined.groupby("strategy")["equity"]
        .agg(["last", "max", "min"])
        .rename(columns={"last": "final", "max": "peak", "min": "trough"})
    )
    st.dataframe(table, width="stretch")


def main() -> None:
    """Render the dashboard."""
    settings = get_settings()

    st.set_page_config(page_title="crypto-cross-pred", layout="wide")
    st.title("crypto-cross-pred")
    st.caption("Cross-sectional return prediction for Binance USD-M perpetual futures")

    with st.sidebar:
        st.subheader("Config")
        st.write(f"**Dev:** {settings.dates.dev_start} → {settings.dates.dev_end}")
        st.write(f"**Holdout:** {settings.dates.holdout_start} → {settings.dates.holdout_end}")
        st.write(
            f"**Universe:** {settings.universe.min_symbols}–{settings.universe.max_symbols} symbols"
        )
        st.write(f"**Round-trip cost:** {settings.costs.round_trip_bps:.0f} bps")
        st.divider()
        st.caption("Read-only: renders artifacts, never computes signals.")

    tabs = st.tabs(["Status", "Dataset", "Predictions", "Simulation"])
    with tabs[0]:
        _render_status()
    with tabs[1]:
        _render_dataset()
    with tabs[2]:
        _render_predictions()
    with tabs[3]:
        _render_simulation()


main()
