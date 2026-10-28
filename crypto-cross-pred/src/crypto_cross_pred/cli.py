"""Command-line entry point: ``python -m crypto_cross_pred.cli <command>``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from crypto_cross_pred.config import get_settings

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
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="crypto-cross-pred",
        description="Cross-sectional return prediction for crypto perpetual futures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("config", help="print the resolved configuration as JSON")

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a process exit code."""
    args = build_parser().parse_args(argv)

    if args.command == "config":
        print(get_settings().model_dump_json(indent=2))
        return 0

    raise NotImplementedError(
        f"stage '{args.command}' is not implemented yet; see docs/TASKS.md for its task"
    )


if __name__ == "__main__":
    sys.exit(main())
