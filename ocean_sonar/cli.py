"""Command line entry point for ocean-sonar-modeling."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

from . import __version__
from .crosspoint import (
    export_trends,
    render_comparison,
    render_trends,
    serialize_comparison,
)
from .report import rank_files


def _paths_identify_same_file(first: str, second: str) -> bool:
    """Whether two paths identify the same file, links included.

    Existing files are recognized with ``os.path.samefile`` (which sees
    through symlinks and hard links); when either path does not exist the
    comparison falls back to ``normcase(realpath(abspath(path)))``.
    """
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(os.path.realpath(os.path.abspath(first))) == (
            os.path.normcase(os.path.realpath(os.path.abspath(second)))
        )


def _write_bytes_atomically(output: str, payload: bytes) -> None:
    """Write ``payload`` to ``output`` via a same-directory temporary file.

    The payload is written, flushed and ``os.fsync``-ed in a temporary
    file in ``output``'s directory, then ``os.replace``-ed into place.
    On any failure before the replacement the temporary file is removed
    and an existing ``output`` is left byte-identical.
    """
    directory = os.path.dirname(os.path.abspath(output))
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".export-comparison-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _export_comparison(paths: list[str], output: str, payload: bytes) -> None:
    """Guard ``output`` against the report paths, then write atomically."""
    for report in paths:
        if _paths_identify_same_file(report, output):
            raise ValueError(
                f"output {output!r} must not identify the same file "
                f"as report {report!r}"
            )
    _write_bytes_atomically(output, payload)


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
    export_parser = sub.add_parser("export-trends", help="aggregate trend JSON files into one report")
    export_parser.add_argument("trend_first", metavar="TREND", help="first trend JSON file")
    export_parser.add_argument("trend_second", metavar="TREND", help="second trend JSON file")
    export_parser.add_argument("trend_rest", nargs="*", metavar="TREND", help="additional trend JSON files")
    export_parser.add_argument("--output", required=True, help="output file overwritten with the trend report JSON")
    compare_parser = sub.add_parser("compare-reports", help="render the comparison of successive trend reports as text lines")
    compare_parser.add_argument("report_first", metavar="REPORT", help="first trend report JSON file")
    compare_parser.add_argument("report_second", metavar="REPORT", help="second trend report JSON file")
    compare_parser.add_argument("report_rest", nargs="*", metavar="REPORT", help="additional trend report JSON files")
    comparison_parser = sub.add_parser("export-comparison", help="serialize the comparison of successive trend reports into one JSON file")
    comparison_parser.add_argument("report_first", metavar="REPORT", help="first trend report JSON file")
    comparison_parser.add_argument("report_second", metavar="REPORT", help="second trend report JSON file")
    comparison_parser.add_argument("report_rest", nargs="*", metavar="REPORT", help="additional trend report JSON files")
    comparison_parser.add_argument("--output", required=True, help="output file atomically overwritten with the comparison JSON")
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
        paths = [args.trend_first, args.trend_second, *args.trend_rest]
        try:
            export_trends(paths, args.output)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    if args.command == "compare-reports":
        paths = [args.report_first, args.report_second, *args.report_rest]
        try:
            text = render_comparison(paths)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(text + "\n")
        return 0

    if args.command == "export-comparison":
        paths = [args.report_first, args.report_second, *args.report_rest]
        try:
            payload = serialize_comparison(paths)
            _export_comparison(paths, args.output, payload)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
