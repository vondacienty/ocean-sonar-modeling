"""Command line entry point for ocean-sonar-modeling."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .crosspoint import export_trends, render_trends
from .report import rank_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocean-sonar-modeling", description="Ocean survey and seabed terrain modelling")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="print the current version")
    rank_parser = sub.add_parser("rank-batches", help="rank serialized batch summaries and write the ranking")
    rank_parser.add_argument("inputs", nargs="+", metavar="INPUT", help="batch summary JSON files, in ranking input order")
    rank_parser.add_argument("--output", required=True, help="output file overwritten with the ranking JSON")
    trends_parser = sub.add_parser("render-trends", help="render multi-file trend summaries as three lines")
    trends_parser.add_argument("trend_first", metavar="TREND", help="first trend JSON file")
    trends_parser.add_argument("trend_second", metavar="TREND", help="second trend JSON file")
    trends_parser.add_argument("trend_rest", nargs="*", metavar="TREND", help="additional trend JSON files")
    export_parser = sub.add_parser("export-trends", help="aggregate multi-file trend summaries into a JSON report")
    export_parser.add_argument("export_first", metavar="TREND", help="first trend JSON file")
    export_parser.add_argument("export_second", metavar="TREND", help="second trend JSON file")
    export_parser.add_argument("export_rest", nargs="*", metavar="TREND", help="additional trend JSON files")
    export_parser.add_argument("--output", required=True, help="output file overwritten with the trend report JSON")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "rank-batches":
        try:
            rank_files(args.inputs, args.output)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    if args.command == "render-trends":
        paths = [args.trend_first, args.trend_second, *args.trend_rest]
        try:
            text = render_trends(paths)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(text + "\n")
        return 0

    if args.command == "export-trends":
        paths = [args.export_first, args.export_second, *args.export_rest]
        try:
            export_trends(paths, args.output)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
