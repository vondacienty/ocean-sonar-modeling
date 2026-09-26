"""End-to-end tests for the ``render-substrate`` CLI subcommand.

The subcommand is exercised both through ``python -m ocean_sonar``
subprocesses (byte-exact stdout/stderr/exit-code assertions) and through
in-process ``ocean_sonar.cli.main`` calls (call-count semantics).
"""

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

EXPECTED = (
    b"SUBSTRATE=4,1,fail\n"
    b"RESULT[0]=mud,1.000000\n"
    b"RESULT[1]=rock,1.000000\n"
    b"RESULT[2]=unknown,0.000000\n"
    b"RESULT[3]=rock,1.000000\n"
)


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


def test_success_exact_output(tmp_path, batch_path):
    result = run_cli(["render-substrate", batch_path], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_input_file_not_modified(tmp_path, batch_path):
    before = Path(batch_path).read_bytes()
    result = run_cli(["render-substrate", batch_path], cwd=tmp_path)
    assert result.returncode == 0
    assert Path(batch_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["render-substrate"], id="missing-input"),
        pytest.param(["render-substrate", "a.json", "b.json"], id="extra-positional"),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"render-substrate" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_mod, "render_substrate", lambda path: calls.append(path))
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["render-substrate"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_render(path):
        calls.append(path)
        return "SUBSTRATE=0,0,pass"

    monkeypatch.setattr(cli_mod, "render_substrate", fake_render)
    rc = cli_mod.main(["render-substrate", "in.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == ["in.json"]
    assert captured.out == "SUBSTRATE=0,0,pass\n"
    assert captured.err == ""


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["render-substrate", missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_corrupted_input_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(["render-substrate", str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("path must be a str"), id="type-error"),
        pytest.param(ValueError("path must not be empty"), id="value-error"),
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

    monkeypatch.setattr(cli_mod, "render_substrate", raising)
    rc = cli_mod.main(["render-substrate", "in.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_render_substrate(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"render-substrate" in result.stdout
