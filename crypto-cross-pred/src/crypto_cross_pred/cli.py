"""Command-line entry point: ``python -m crypto_cross_pred.cli <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import date

from crypto_cross_pred.config import PROJECT_ROOT, get_settings
from crypto_cross_pred.data import download as download_module
from crypto_cross_pred.data.universe import load_universe
from crypto_cross_pred.io import huggingface
from crypto_cross_pred.io.artifacts import artifact_status, newest_artifact_mtime
from crypto_cross_pred.report import quality

DEFAULT_UNIVERSE_FILE = PROJECT_ROOT / "config" / "universe.json"

#: Pipeline stages, in execution order. ``all`` runs them end to end.
STAGES: tuple[str, ...] = (
    "download",
    "transform",
    "features",
    "train",
    "predict",
    "simulate",
    "notify",
)

_HELP: dict[str, str] = {
    "download": "fetch raw data (incremental) or pull an HF snapshot",
    "transform": "raw sources -> unified schema",
    "features": "build the feature families",
    "train": "fit models on the dev period",
    "predict": "score the latest data",
    "simulate": "run the trading simulations",
    "notify": "send alerts",
    "all": "run every stage in order",
    "status": "show which artifacts exist on disk",
}


def _print_status() -> int:
    """Print one line per artifact family."""
    header = f"{'artifact':<14}{'files':>7}{'rows':>12}  {'latest':<30}"
    print(header)
    print("-" * len(header))
    for info in artifact_status():
        print(f"{info.name:<14}{info.files:>7}{info.rows:>12,}  {info.latest_name:<30}")

    written = newest_artifact_mtime()
    print()
    if written is None:
        print("no artifacts yet - start with: cli download --source binance")
    else:
        print(f"newest artifact written: {written:%Y-%m-%d %H:%M:%S} UTC")
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    """Backfill raw data from the Binance archive."""
    if args.source == "hf":
        target = huggingface.pull_data(get_settings().paths.resolve().data_dir)
        print(f"pulled HF snapshot into {target}")
        return 0

    settings = get_settings()
    paths = settings.paths.resolve()

    if args.symbols:
        symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    else:
        if not DEFAULT_UNIVERSE_FILE.exists():
            raise FileNotFoundError(
                f"{DEFAULT_UNIVERSE_FILE} not found; run the universe selection first"
            )
        symbols = [entry.symbol for entry in load_universe(DEFAULT_UNIVERSE_FILE)]

    if args.limit:
        symbols = symbols[: args.limit]

    start = date.fromisoformat(args.since) if args.since else settings.dates.dev_start
    end = min(settings.dates.holdout_end, date.today())
    datasets = tuple(item.strip() for item in args.datasets.split(",") if item.strip())

    if args.incremental:
        print(f"incremental: {len(symbols)} symbols")
        results = download_module.incremental(symbols, raw_dir=paths.raw_dir, workers=args.workers)
        added_klines = sum(item["klines"] for _, item in results)
        added_funding = sum(item["funding"] for _, item in results)
        print()
        print(f"new klines:  {added_klines:,}")
        print(f"new funding: {added_funding:,}")
        return 0

    print(f"symbols: {len(symbols)}  {symbols[:3]}{'...' if len(symbols) > 3 else ''}")
    print(f"period:  {start} -> {end}")
    print(f"datasets: {', '.join(datasets)}")

    results = download_module.backfill(
        symbols,
        start=start,
        end=end,
        raw_dir=paths.raw_dir,
        datasets=datasets,
        workers=args.workers,
    )

    header = f"{'dataset':<10}{'symbols':>9}{'files':>9}{'rows':>14}{'new':>14}"
    print()
    print(header)
    print("-" * len(header))
    for dataset in datasets:
        rows = [item for item in results if item.dataset == dataset]
        print(
            f"{dataset:<10}{len(rows):>9}"
            f"{sum(item.files for item in rows):>9}"
            f"{sum(item.rows for item in rows):>14,}"
            f"{sum(item.added for item in rows):>14,}"
        )
    return 0


def _cmd_quality() -> int:
    """Build, print and save the data quality report."""
    settings = get_settings()
    paths = settings.paths.resolve()

    if not DEFAULT_UNIVERSE_FILE.exists():
        raise FileNotFoundError(f"{DEFAULT_UNIVERSE_FILE} not found")
    symbols = [entry.symbol for entry in load_universe(DEFAULT_UNIVERSE_FILE)]

    frame = quality.build(paths.raw_dir, symbols)
    summary = quality.summarize(frame)
    parquet_path, json_path = quality.save(frame, summary, paths.artifacts_dir)

    print(quality.render(frame, summary))
    print()
    print(f"saved {parquet_path.name} and {json_path.name} to {paths.artifacts_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="crypto-cross-pred",
        description="Cross-sectional return prediction for crypto perpetual futures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("config", help="print the resolved configuration as JSON")
    subparsers.add_parser("status", help=_HELP["status"])
    subparsers.add_parser("quality", help="coverage, gaps and null rates per symbol")

    for stage in (*STAGES, "all"):
        stage_parser = subparsers.add_parser(stage, help=_HELP[stage])
        if stage in {"download", "all"}:
            stage_parser.add_argument(
                "--source",
                choices=("binance", "hf"),
                default="binance",
                help="download fresh data or read a prebuilt HF snapshot (default: binance)",
            )
        if stage == "download":
            stage_parser.add_argument(
                "--since",
                metavar="YYYY-MM-DD",
                default=None,
                help="earliest date to backfill (default: config dev_start)",
            )
            stage_parser.add_argument(
                "--symbols",
                default=None,
                help="comma-separated symbols (default: config/universe.json)",
            )
            stage_parser.add_argument(
                "--datasets",
                default=",".join(download_module.DATASETS),
                help="comma-separated subset of " + ",".join(download_module.DATASETS),
            )
            stage_parser.add_argument(
                "--limit",
                type=int,
                default=None,
                help="only the first N symbols (smoke tests)",
            )
            stage_parser.add_argument(
                "--workers",
                type=int,
                default=4,
                help="parallel downloads (default: 4)",
            )
            stage_parser.add_argument(
                "--incremental",
                action="store_true",
                help="only fetch bars after the last stored timestamp (REST)",
            )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a process exit code."""
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "config":
        print(get_settings().model_dump_json(indent=2))
        return 0

    if args.command == "status":
        return _print_status()

    if args.command == "download":
        return _cmd_download(args)

    if args.command == "quality":
        return _cmd_quality()

    raise NotImplementedError(
        f"stage '{args.command}' is not implemented yet; see docs/TASKS.md for its task"
    )


if __name__ == "__main__":
    sys.exit(main())
