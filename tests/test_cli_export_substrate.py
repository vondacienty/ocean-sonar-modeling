"""End-to-end tests for the ``export-substrate`` CLI subcommand."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.substrate import batch

REPO_ROOT = Path(__file__).resolve().parents[1]

ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]


@pytest.fixture
def batch_path(tmp_path):
    path = tmp_path / "substrate.json"
    path.write_bytes(batch(ANALYSIS, INTENSITIES))
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


def test_success_silent_exit_0_and_file_written(tmp_path, batch_path):
    output = tmp_path / "copy.json"
    result = run_cli(
        ["export-substrate", batch_path, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == batch(ANALYSIS, INTENSITIES)


def test_input_file_not_modified(tmp_path, batch_path):
    before = Path(batch_path).read_bytes()
    result = run_cli(
        ["export-substrate", batch_path, "--output", str(tmp_path / "copy.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(batch_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-substrate"], id="missing-input-and-output"),
        pytest.param(["export-substrate", "in.json"], id="missing-output"),
        pytest.param(
            ["export-substrate", "a.json", "b.json", "--output", "o.json"],
            id="extra-positional",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-substrate" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "export_substrate",
        lambda path, output: calls.append((path, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-substrate", "in.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(path, output):
        calls.append((path, output))
        return b"{}"

    monkeypatch.setattr(cli_mod, "export_substrate", fake_export)
    rc = cli_mod.main(
        ["export-substrate", "in.json", "--output", "copy.json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [("in.json", "copy.json")]
    assert captured.out == ""
    assert captured.err == ""


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        ["export-substrate", missing, "--output", str(tmp_path / "o.json")],
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
        ["export-substrate", str(bad), "--output", str(tmp_path / "o.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_error(tmp_path, batch_path):
    result = run_cli(
        ["export-substrate", batch_path, "--output", batch_path],
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
    def raising(path, output):
        raise exc

    monkeypatch.setattr(cli_mod, "export_substrate", raising)
    rc = cli_mod.main(
        ["export-substrate", "in.json", "--output", "copy.json"]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_export_substrate(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-substrate" in result.stdout
