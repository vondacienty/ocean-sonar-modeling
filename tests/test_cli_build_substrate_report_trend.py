"""End-to-end tests for the ``build-substrate-report-trend`` CLI subcommand."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.substrate import (
    batch,
    dump_aggregate,
    serialize_aggregate_report,
    serialize_aggregate_report_trend,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

UNKNOWN_ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]]
CLEAN_ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [2.0, 0.3], [6.0, 2.0]]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]


def write_report(tmp_path, name, analyses):
    """Write one aggregate report whose batches have the given unknown counts."""
    batch_paths = []
    for i, analysis in enumerate(analyses):
        path = tmp_path / f"{name}_batch{i}.json"
        path.write_bytes(batch(analysis, INTENSITIES))
        batch_paths.append(str(path))
    aggregate_path = tmp_path / f"{name}_aggregate.json"
    aggregate_path.write_bytes(dump_aggregate(batch_paths))
    report_path = tmp_path / f"{name}_report.json"
    report_path.write_bytes(serialize_aggregate_report(str(aggregate_path)))
    return str(report_path)


@pytest.fixture
def report_paths(tmp_path):
    first = write_report(tmp_path, "r0", [UNKNOWN_ANALYSIS, CLEAN_ANALYSIS])
    second = write_report(tmp_path, "r1", [CLEAN_ANALYSIS, CLEAN_ANALYSIS])
    return [first, second]


def run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "ocean_sonar", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
    )


def test_success_silent_exit_0_and_file_written(tmp_path, report_paths):
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "build-substrate-report-trend",
            report_paths[0],
            report_paths[1],
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == serialize_aggregate_report_trend(report_paths)


def test_three_reports_silent_exit_0(tmp_path, report_paths):
    third = write_report(tmp_path, "r2", [UNKNOWN_ANALYSIS, UNKNOWN_ANALYSIS])
    paths = [*report_paths, third]
    output = tmp_path / "trend.json"
    result = run_cli(
        ["build-substrate-report-trend", *paths, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == serialize_aggregate_report_trend(paths)


def test_input_files_not_modified(tmp_path, report_paths):
    before = [Path(path).read_bytes() for path in report_paths]
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "build-substrate-report-trend",
            *report_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    after = [Path(path).read_bytes() for path in report_paths]
    assert after == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["build-substrate-report-trend"], id="missing-all"),
        pytest.param(
            ["build-substrate-report-trend", "r.json"], id="only-one-report"
        ),
        pytest.param(
            ["build-substrate-report-trend", "a.json", "b.json"],
            id="missing-output",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"build-substrate-report-trend" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "serialize_aggregate_report_trend",
        lambda paths: calls.append(paths),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["build-substrate-report-trend", "r.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_serialize(paths):
        calls.append(list(paths))
        return b"{}"

    monkeypatch.setattr(cli_mod, "serialize_aggregate_report_trend", fake_serialize)
    monkeypatch.chdir(tmp_path)
    rc = cli_mod.main(
        [
            "build-substrate-report-trend",
            "a.json",
            "b.json",
            "c.json",
            "--output",
            "trend.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [["a.json", "b.json", "c.json"]]
    assert captured.out == ""
    assert captured.err == ""
    assert (tmp_path / "trend.json").read_bytes() == b"{}"


def test_missing_report_file(tmp_path, report_paths):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        [
            "build-substrate-report-trend",
            report_paths[0],
            missing,
            "--output",
            str(tmp_path / "o.json"),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1
    assert not (tmp_path / "o.json").exists()


def test_corrupted_report_file(tmp_path, report_paths):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        [
            "build-substrate-report-trend",
            str(bad),
            report_paths[1],
            "--output",
            str(tmp_path / "o.json"),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_error(tmp_path, report_paths):
    result = run_cli(
        [
            "build-substrate-report-trend",
            *report_paths,
            "--output",
            report_paths[0],
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert b"same file" in result.stderr
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("output must be a str"), id="type-error"),
        pytest.param(
            ValueError("output must not be empty"), id="value-error"
        ),
        pytest.param(
            FileNotFoundError(2, "No such file or directory", "x.json"),
            id="file-not-found",
        ),
        pytest.param(
            IsADirectoryError(21, "Is a directory", "x"),
            id="is-a-directory",
        ),
    ],
)
def test_exception_format(monkeypatch, capsys, exc):
    def raising(paths):
        raise exc

    monkeypatch.setattr(cli_mod, "serialize_aggregate_report_trend", raising)
    rc = cli_mod.main(
        [
            "build-substrate-report-trend",
            "a.json",
            "b.json",
            "--output",
            "trend.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_build_substrate_report_trend(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"build-substrate-report-trend" in result.stdout
