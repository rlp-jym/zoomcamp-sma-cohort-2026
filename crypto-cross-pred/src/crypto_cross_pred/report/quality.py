"""Data quality report: coverage, gaps and null rates per symbol.

Reads what the download stage wrote and reports what is missing. Nothing here fixes
data — it only measures it, so the transform stage can decide what to exclude.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from crypto_cross_pred.io import storage

logger = logging.getLogger(__name__)

COVERAGE_WARN = 0.95


@dataclass(frozen=True)
class QualitySummary:
    """Headline numbers for the printed report."""

    symbols: int
    total_rows: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    under_covered: tuple[str, ...]
    missing_funding: tuple[str, ...]
    missing_metrics: tuple[str, ...]

    def as_dict(self) -> dict:
        """JSON-friendly view."""
        return {
            "symbols": self.symbols,
            "total_rows": self.total_rows,
            "start": self.start.isoformat() if self.start is not None else None,
            "end": self.end.isoformat() if self.end is not None else None,
            "under_covered": list(self.under_covered),
            "missing_funding": list(self.missing_funding),
            "missing_metrics": list(self.missing_metrics),
        }


def _symbol_stats(symbol: str, raw_dir: Path) -> dict:
    """Coverage and gap statistics for one symbol."""
    klines = storage.read_parquet(storage.partition_path(raw_dir / "binance" / "klines", symbol))
    funding = storage.read_parquet(storage.partition_path(raw_dir / "binance" / "funding", symbol))
    metrics = storage.read_parquet(storage.partition_path(raw_dir / "binance" / "metrics", symbol))

    row: dict = {
        "symbol": symbol,
        "klines": 0,
        "start": None,
        "end": None,
        "coverage": 0.0,
        "gaps": 0,
        "funding": 0 if funding is None else len(funding),
        "metrics": 0 if metrics is None else len(metrics),
        "metrics_null_pct": None,
    }

    if klines is None or klines.empty:
        return row

    timestamps = pd.to_datetime(klines["ts"], utc=True).sort_values()
    expected = int((timestamps.iloc[-1] - timestamps.iloc[0]) / pd.Timedelta(hours=1)) + 1
    gaps = int((timestamps.diff().dropna() != pd.Timedelta(hours=1)).sum())

    row.update(
        {
            "klines": len(timestamps),
            "start": timestamps.iloc[0],
            "end": timestamps.iloc[-1],
            "coverage": round(len(timestamps) / expected, 4) if expected else 0.0,
            "gaps": gaps,
        }
    )

    if metrics is not None and not metrics.empty:
        value_columns = [column for column in metrics.columns if column != "ts"]
        row["metrics_null_pct"] = round(float(metrics[value_columns].isna().mean().max()), 4)

    return row


def build(raw_dir: Path, symbols: list[str]) -> pd.DataFrame:
    """Per-symbol quality frame."""
    rows = [_symbol_stats(symbol, raw_dir) for symbol in symbols]
    frame = pd.DataFrame(rows)
    return frame.sort_values("coverage").reset_index(drop=True)


def summarize(frame: pd.DataFrame) -> QualitySummary:
    """Headline numbers derived from the per-symbol frame."""
    if frame.empty:
        return QualitySummary(0, 0, None, None, (), (), ())

    started = frame["start"].dropna()
    ended = frame["end"].dropna()
    return QualitySummary(
        symbols=len(frame),
        total_rows=int(frame["klines"].sum()),
        start=started.min() if not started.empty else None,
        end=ended.max() if not ended.empty else None,
        under_covered=tuple(frame.loc[frame["coverage"] < COVERAGE_WARN, "symbol"]),
        missing_funding=tuple(frame.loc[frame["funding"] == 0, "symbol"]),
        missing_metrics=tuple(frame.loc[frame["metrics"] == 0, "symbol"]),
    )


def save(frame: pd.DataFrame, summary: QualitySummary, artifacts_dir: Path) -> tuple[Path, Path]:
    """Write the per-symbol parquet and the summary JSON."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = artifacts_dir / "quality_report.parquet"
    json_path = artifacts_dir / "quality_report.json"

    frame.to_parquet(parquet_path, index=False)
    json_path.write_text(json.dumps(summary.as_dict(), indent=2) + "\n", encoding="utf-8")
    return parquet_path, json_path


def render(frame: pd.DataFrame, summary: QualitySummary, *, worst: int = 10) -> str:
    """Human-readable report for the terminal."""
    if frame.empty:
        return "no data to report"

    lines = [
        f"symbols:        {summary.symbols}",
        f"kline rows:     {summary.total_rows:,}",
        f"range:          {summary.start:%Y-%m-%d} -> {summary.end:%Y-%m-%d}"
        if summary.start is not None and summary.end is not None
        else "range:          -",
        f"under {COVERAGE_WARN:.0%}:     {len(summary.under_covered)} symbols",
        f"no funding:     {len(summary.missing_funding)} symbols",
        f"no metrics:     {len(summary.missing_metrics)} symbols",
        "",
        "worst coverage:",
    ]
    header = f"  {'symbol':<18}{'rows':>10}{'coverage':>10}{'gaps':>7}{'funding':>9}{'metrics':>9}"
    lines.append(header)
    for _, row in frame.head(worst).iterrows():
        lines.append(
            f"  {row['symbol']:<18}{row['klines']:>10,}{row['coverage']:>10.1%}"
            f"{row['gaps']:>7}{row['funding']:>9,}{row['metrics']:>9,}"
        )
    return "\n".join(lines)
