"""End-to-end tests for the ``export-substrate-report`` CLI subcommand."""

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
)

REPO_ROOT = Path(__file__).resolve().parents[1]

ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]
OTHER_ANALYSIS = [[2.0, 0.3], [6.0, 2.0]]
OTHER_INTENSITIES = [0.6, 0.6]


@pytest.fixture
def aggregate_path(tmp_path):
    batch_a = tmp_path / "batch_a.json"
    batch_a.write_bytes(batch(ANALYSIS, INTENSITIES))
    batch_b = tmp_path / "batch_b.json"
    batch_b.write_bytes(batch(OTHER_ANALYSIS, OTHER_INTENSITIES))
    path = tmp_path / "aggregate.json"
    path.write_bytes(dump_aggregate([str(batch_a), str(batch_b)]))
    return str(path)


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


def test_success_silent_exit_0_and_file_written(tmp_path, aggregate_path):
    output = tmp_path / "report.json"
    result = run_cli(
        ["export-substrate-report", aggregate_path, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == serialize_aggregate_report(aggregate_path)


def test_input_file_not_modified(tmp_path, aggregate_path):
    before = Path(aggregate_path).read_bytes()
    result = run_cli(
        [
            "export-substrate-report",
            aggregate_path,
            "--output",
            str(tmp_path / "report.json"),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(aggregate_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-substrate-report"], id="missing-input-and-output"),
        pytest.param(["export-substrate-report", "in.json"], id="missing-output"),
        pytest.param(
            ["export-substrate-report", "a.json", "b.json", "--output", "o.json"],
            id="extra-positional",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-substrate-report" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "serialize_aggregate_report",
        lambda path: calls.append(path),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-substrate-report", "in.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_serialize(path):
        calls.append(path)
        return b"{}"

    monkeypatch.setattr(cli_mod, "serialize_aggregate_report", fake_serialize)
    monkeypatch.chdir(tmp_path)
    rc = cli_mod.main(
        ["export-substrate-report", "in.json", "--output", "report.json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == ["in.json"]
    assert captured.out == ""
    assert captured.err == ""
    assert (tmp_path / "report.json").read_bytes() == b"{}"


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        ["export-substrate-report", missing, "--output", str(tmp_path / "o.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1
    assert not (tmp_path / "o.json").exists()


def test_corrupted_input_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        ["export-substrate-report", str(bad), "--output", str(tmp_path / "o.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_error(tmp_path, aggregate_path):
    result = run_cli(
        ["export-substrate-report", aggregate_path, "--output", aggregate_path],
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
        pytest.param(ValueError("output must not be empty"), id="value-error"),
        pytest.param(
            FileNotFoundError(2, "No such file or directory", "x.json"),
            id="file-not-found",
        ),
        pytest.param(IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"),
    ],
)
def test_exception_format(monkeypatch, capsys, exc):
    def raising(path):
        raise exc

    monkeypatch.setattr(cli_mod, "serialize_aggregate_report", raising)
    rc = cli_mod.main(
        ["export-substrate-report", "in.json", "--output", "report.json"]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_export_substrate_report(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-substrate-report" in result.stdout
