"""Command-line entry point: ``python -m crypto_cross_pred.cli <command>``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from crypto_cross_pred.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="crypto-cross-pred",
        description="Cross-sectional return prediction for crypto perpetual futures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("config", help="print the resolved configuration as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a process exit code."""
    args = build_parser().parse_args(argv)

    if args.command == "config":
        print(get_settings().model_dump_json(indent=2))
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
