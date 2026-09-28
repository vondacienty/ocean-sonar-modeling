"""End-to-end tests for the ``export-overview-comparison-report`` CLI subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar import product as product_mod

REPO_ROOT = Path(__file__).resolve().parents[1]


def trend_report(regressed=0):
    changes = 1
    passed = changes - regressed
    quality = "pass" if regressed == 0 else "fail"
    return {
        "schema_version": 1,
        "source": {"path": "x.json", "kind": "overview_trend"},
        "summary": {
            "count": 2,
            "changes": changes,
            "regressed": regressed,
            "passed": passed,
        },
        "worst": {
            "index": 1,
            "qualities": ["pass", "pass", "pass", quality],
            "regressions": [False, False, False, regressed == 1],
            "quality": quality,
        },
        "quality": quality,
    }


def write_trend_report(path, regressed=0):
    data = json.dumps(
        trend_report(regressed), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    Path(path).write_bytes(data)


@pytest.fixture
def comparison_path(tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    write_trend_report(first, 0)
    write_trend_report(second, 1)
    data = product_mod.serialize_overview_comparison(
        [str(first), str(second)]
    )
    comparison = tmp_path / "comparison.json"
    comparison.write_bytes(data)
    return str(comparison)


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


def test_success_silent_exit_0_and_file_written(tmp_path, comparison_path):
    output = tmp_path / "report.json"
    result = run_cli(
        [
            "export-overview-comparison-report",
            comparison_path,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    expected = product_mod.serialize_overview_comparison_report(comparison_path)
    assert output.read_bytes() == expected
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not output.read_bytes().endswith(b"\n")
    document = json.loads(output.read_bytes())
    assert list(document.keys()) == [
        "schema_version",
        "source",
        "summary",
        "worst",
        "quality",
    ]


def test_input_file_not_modified(tmp_path, comparison_path):
    before = Path(comparison_path).read_bytes()
    output = tmp_path / "report.json"
    result = run_cli(
        [
            "export-overview-comparison-report",
            comparison_path,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(comparison_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-overview-comparison-report"], id="missing-all"),
        pytest.param(
            ["export-overview-comparison-report", "c.json"],
            id="missing-output",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-overview-comparison-report" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_export_overview_comparison_report",
        lambda path, output: calls.append((path, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-overview-comparison-report", "c.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(path, output):
        calls.append((path, output))
        return b"{}"

    monkeypatch.setattr(
        cli_mod, "_export_overview_comparison_report", fake_export
    )
    rc = cli_mod.main(
        [
            "export-overview-comparison-report",
            "comparison.json",
            "--output",
            "report.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [("comparison.json", "report.json")]
    assert captured.out == ""
    assert captured.err == ""


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    output = tmp_path / "report.json"
    result = run_cli(
        [
            "export-overview-comparison-report",
            missing,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1
    assert not output.exists()


def test_corrupted_input_file(tmp_path, comparison_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        [
            "export-overview-comparison-report",
            str(bad),
            "--output",
            str(tmp_path / "report.json"),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_error(tmp_path, comparison_path):
    result = run_cli(
        [
            "export-overview-comparison-report",
            comparison_path,
            "--output",
            comparison_path,
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
    def raising(path, output):
        raise exc

    monkeypatch.setattr(
        cli_mod, "_export_overview_comparison_report", raising
    )
    rc = cli_mod.main(
        [
            "export-overview-comparison-report",
            "comparison.json",
            "--output",
            "report.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_export_overview_comparison_report(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-overview-comparison-report" in result.stdout
