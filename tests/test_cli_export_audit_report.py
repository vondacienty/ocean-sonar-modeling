"""End-to-end tests for the ``export-audit-report`` CLI subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.crosspoint import serialize_audit, serialize_audit_report

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_comparison(path, changes):
    """Write a canonical serialize_comparison-shaped JSON file."""
    quality = "fail" if any(c["quality"] == "fail" for c in changes) else "pass"
    document = {"changes": changes, "worst": changes[0], "quality": quality}
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return str(path)


def change(index, degraded_delta, coverage_delta, score_delta, quality):
    return {
        "index": index,
        "degraded_delta": degraded_delta,
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "quality": quality,
    }


@pytest.fixture
def audit_path(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json", [change(1, 1, -0.2, -0.5, "fail")]
    )
    path = tmp_path / "audit.json"
    path.write_bytes(serialize_audit([p0, p1]))
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


def test_success_silent_exit_0_and_file_written(tmp_path, audit_path):
    output = tmp_path / "report.json"
    result = run_cli(
        ["export-audit-report", audit_path, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == serialize_audit_report(audit_path)


def test_audit_file_not_modified(tmp_path, audit_path):
    before = Path(audit_path).read_bytes()
    output = tmp_path / "report.json"
    result = run_cli(
        ["export-audit-report", audit_path, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(audit_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-audit-report"], id="missing-audit-and-output"),
        pytest.param(["export-audit-report", "audit.json"], id="missing-output"),
        pytest.param(
            ["export-audit-report", "a.json", "b.json", "--output", "o.json"],
            id="extra-positional",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-audit-report" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "export_audit_report",
        lambda audit_path, output: calls.append((audit_path, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-audit-report", "audit.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(audit_path, output):
        calls.append((audit_path, output))
        return b"{}"

    monkeypatch.setattr(cli_mod, "export_audit_report", fake_export)
    rc = cli_mod.main(
        ["export-audit-report", "audit.json", "--output", "report.json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [("audit.json", "report.json")]
    assert captured.out == ""
    assert captured.err == ""


def test_missing_audit_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        ["export-audit-report", missing, "--output", str(tmp_path / "o.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1
    assert not (tmp_path / "o.json").exists()


def test_corrupted_audit_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        ["export-audit-report", str(bad), "--output", str(tmp_path / "o.json")],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_error(tmp_path, audit_path):
    result = run_cli(
        ["export-audit-report", audit_path, "--output", audit_path],
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
    def raising(audit_path, output):
        raise exc

    monkeypatch.setattr(cli_mod, "export_audit_report", raising)
    rc = cli_mod.main(
        ["export-audit-report", "audit.json", "--output", "report.json"]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_export_audit_report(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-audit-report" in result.stdout
