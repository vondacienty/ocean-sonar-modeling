"""End-to-end tests for the ``export-quality-trend`` CLI subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.product import export_quality_trend

REPO_ROOT = Path(__file__).resolve().parents[1]


def dump_report(report):
    return json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def valid_report(**changes):
    report = {
        "layers": 2,
        "total": 4,
        "valid": 3,
        "coverage": 0.75,
        "terrain_exceed": 1,
        "unknown": 0,
        "worst": 1,
        "crosspoint": "pass",
        "quality": "fail",
    }
    report.update(changes)
    return report


def write_report(path, report):
    path.write_bytes(dump_report(report))
    return str(path)


@pytest.fixture
def report_paths(tmp_path):
    p0 = write_report(tmp_path / "r0.json", valid_report())
    p1 = write_report(
        tmp_path / "r1.json",
        valid_report(
            valid=4,
            coverage=1.0,
            terrain_exceed=0,
            unknown=0,
            worst=0,
            crosspoint="pass",
            quality="pass",
        ),
    )
    return [p0, p1]


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
            "export-quality-trend",
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
    scratch = tmp_path / "scratch.json"
    assert output.read_bytes() == export_quality_trend(
        report_paths, str(scratch)
    )


def test_three_reports_silent_exit_0(tmp_path, report_paths):
    third = tmp_path / "r2.json"
    third.write_bytes(Path(report_paths[1]).read_bytes())
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-quality-trend",
            report_paths[0],
            report_paths[1],
            str(third),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    document = json.loads(output.read_bytes())
    assert list(document.keys()) == ["changes", "worst", "quality"]
    assert len(document["changes"]) == 2


def test_input_files_not_modified(tmp_path, report_paths):
    before = [Path(path).read_bytes() for path in report_paths]
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-quality-trend",
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
        pytest.param(["export-quality-trend"], id="missing-all"),
        pytest.param(["export-quality-trend", "r.json"], id="only-one-report"),
        pytest.param(
            ["export-quality-trend", "a.json", "b.json"],
            id="missing-output",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-quality-trend" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "export_quality_trend",
        lambda paths, output: calls.append((paths, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-quality-trend", "a.json", "b.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(paths, output):
        calls.append((list(paths), output))
        return b"{}"

    monkeypatch.setattr(cli_mod, "export_quality_trend", fake_export)
    rc = cli_mod.main(
        [
            "export-quality-trend",
            "a.json",
            "b.json",
            "c.json",
            "--output",
            "trend.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(["a.json", "b.json", "c.json"], "trend.json")]
    assert captured.out == ""
    assert captured.err == ""


def test_missing_report_file(tmp_path, report_paths):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        [
            "export-quality-trend",
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
            "export-quality-trend",
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
            "export-quality-trend",
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
    def raising(paths, output):
        raise exc

    monkeypatch.setattr(cli_mod, "export_quality_trend", raising)
    rc = cli_mod.main(
        [
            "export-quality-trend",
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


def test_help_lists_export_quality_trend(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-quality-trend" in result.stdout
