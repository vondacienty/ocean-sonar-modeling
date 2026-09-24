"""Command line entry point for ocean-sonar-modeling."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from . import report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocean-sonar-modeling", description="Ocean survey and seabed terrain modelling")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="print the current version")

    rank_parser = sub.add_parser(
        "rank-batches",
        help="rank serialized batch summaries and write the ranking",
    )
    rank_parser.add_argument("inputs", nargs="+", metavar="INPUT", help="batch summary file to rank")
    rank_parser.add_argument("--output", required=True, help="file the ranking JSON is written to")

    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "rank-batches":
        try:
            report.rank_files(args.inputs, args.output)
        except Exception as exc:
            print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
