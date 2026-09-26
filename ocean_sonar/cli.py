"""Command line entry point for ocean-sonar-modeling."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from . import __version__
from .crosspoint import (
    audit_comparisons,
    export_audit,
    export_trends,
    render_audit,
    render_comparison,
    render_trends,
    serialize_comparison,
)
from .report import rank_files


def _resolved_path(path):
    """Normalized absolute path with symlinks resolved, for non-existing files."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _reject_output_overlap(output, paths):
    """Reject ``output`` naming the same file as any of ``paths``.

    Existing files are compared with ``os.path.samefile`` so soft and hard
    links are recognized; when either side does not exist, the normalized
    ``realpath`` strings are compared instead.
    """
    output_exists = os.path.exists(output)
    output_resolved = _resolved_path(output)
    for path in paths:
        if output_exists and os.path.exists(path):
            same = os.path.samefile(output, path)
        else:
            same = output_resolved == _resolved_path(path)
        if same:
            raise ValueError(
                f"output must not be the same file as a report: "
                f"{output!r} and {path!r}"
            )


def _atomic_write_bytes(output, data):
    """Write ``data`` to ``output`` via a fsynced temp file and ``os.replace``.

    The temporary file lives in ``output``'s directory. On any failure before
    the replacement the temporary file is removed and an existing ``output``
    is left untouched.
    """
    directory = os.path.dirname(os.path.abspath(output)) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix="." + os.path.basename(output) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, output)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _export_comparison_file(paths, output):
    data = serialize_comparison(paths)
    _reject_output_overlap(output, paths)
    _atomic_write_bytes(output, data)


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
    compare_parser = sub.add_parser("compare-reports", help="compare successive trend report snapshots as text lines")
    compare_parser.add_argument("compare_first", metavar="REPORT", help="first trend report JSON file")
    compare_parser.add_argument("compare_second", metavar="REPORT", help="second trend report JSON file")
    compare_parser.add_argument("compare_rest", nargs="*", metavar="REPORT", help="additional trend report JSON files")
    export_comparison_parser = sub.add_parser("export-comparison", help="compare successive trend report snapshots and write one JSON file")
    export_comparison_parser.add_argument("compare_first", metavar="REPORT", help="first trend report JSON file")
    export_comparison_parser.add_argument("compare_second", metavar="REPORT", help="second trend report JSON file")
    export_comparison_parser.add_argument("compare_rest", nargs="*", metavar="REPORT", help="additional trend report JSON files")
    export_comparison_parser.add_argument("--output", required=True, help="output file atomically overwritten with the comparison JSON")
    audit_comparisons_parser = sub.add_parser("audit-comparisons", help="audit comparison JSON files and print one compact JSON summary")
    audit_comparisons_parser.add_argument("audit_first", metavar="FILE", help="first comparison JSON file")
    audit_comparisons_parser.add_argument("audit_second", metavar="FILE", help="second comparison JSON file")
    audit_comparisons_parser.add_argument("audit_rest", nargs="*", metavar="FILE", help="additional comparison JSON files")
    export_audit_parser = sub.add_parser("export-audit", help="audit comparison JSON files and write one JSON audit")
    export_audit_parser.add_argument("audit_first", metavar="FILE", help="first comparison JSON file")
    export_audit_parser.add_argument("audit_second", metavar="FILE", help="second comparison JSON file")
    export_audit_parser.add_argument("audit_rest", nargs="*", metavar="FILE", help="additional comparison JSON files")
    export_audit_parser.add_argument("--output", required=True, help="output file atomically overwritten with the audit JSON")
    render_audit_parser = sub.add_parser("render-audit", help="render one audit JSON file as two summary lines")
    render_audit_parser.add_argument("audit", metavar="AUDIT", help="audit JSON file")
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
        paths = [args.compare_first, args.compare_second, *args.compare_rest]
        try:
            text = render_comparison(paths)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(text + "\n")
        return 0

    if args.command == "export-comparison":
        paths = [args.compare_first, args.compare_second, *args.compare_rest]
        try:
            _export_comparison_file(paths, args.output)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    if args.command == "audit-comparisons":
        paths = [args.audit_first, args.audit_second, *args.audit_rest]
        try:
            result = audit_comparisons(paths)
            text = json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(text + "\n")
        return 0

    if args.command == "export-audit":
        paths = [args.audit_first, args.audit_second, *args.audit_rest]
        try:
            export_audit(paths, args.output)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        return 0

    if args.command == "render-audit":
        try:
            text = render_audit(args.audit)
        except Exception as exc:
            sys.stderr.write(f"ERROR {type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(text + "\n")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
