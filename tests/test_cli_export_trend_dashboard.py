"""End-to-end tests for the ``export-trend-dashboard`` CLI subcommand."""

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


def item(index, failed_delta, regressed_delta, passed_delta, quality):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "regressed_delta": regressed_delta,
        "passed_delta": passed_delta,
        "quality": quality,
    }


def trend_doc(changes):
    regressed = sum(1 for c in changes if c["quality"] == "fail")
    worst = min(
        changes,
        key=lambda c: (
            c["passed_delta"],
            -c["failed_delta"],
            -c["regressed_delta"],
            c["index"],
        ),
    )
    quality = "pass" if regressed == 0 else "fail"
    return {
        "count": len(changes) + 1,
        "changes": changes,
        "regressed": regressed,
        "worst": worst,
        "quality": quality,
    }


@pytest.fixture
def trend_path(tmp_path):
    doc = trend_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 1, -1, "fail"),
        ]
    )
    path = tmp_path / "trend.json"
    path.write_bytes(
        product_mod._dump_overview_comparison_report_trend(doc)
    )
    return str(path)


def run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get(
        "PYTHONPATH", ""
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "ocean_sonar", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
    )


def test_help_lists_command(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-trend-dashboard" in result.stdout


def test_success_silent_exit_0_and_file_written(tmp_path, trend_path):
    output = tmp_path / "dashboard.json"
    result = run_cli(
        [
            "export-trend-dashboard",
            trend_path,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    scratch = tmp_path / "scratch.json"
    expected = product_mod.export_trend_dashboard(
        trend_path, str(scratch)
    )
    assert output.read_bytes() == expected
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not output.read_bytes().endswith(b"\n")
    document = json.loads(output.read_bytes())
    assert list(document.keys()) == ["trend", "summary", "quality"]
    assert document["summary"] == {
        "reports": 3,
        "passed": 1,
        "regressed": 1,
        "ratio": 0.5,
        "worst": 2,
    }
    assert document["quality"] == "fail"


def test_input_file_not_modified(tmp_path, trend_path):
    before = Path(trend_path).read_bytes()
    output = tmp_path / "dashboard.json"
    result = run_cli(
        [
            "export-trend-dashboard",
            trend_path,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(trend_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-trend-dashboard"], id="missing-all"),
        pytest.param(
            ["export-trend-dashboard", "t.json"], id="missing-output"
        ),
        pytest.param(
            [
                "export-trend-dashboard",
                "t.json",
                "extra",
                "--output",
                "o.json",
            ],
            id="extra-positional",
        ),
        pytest.param(
            [
                "export-trend-dashboard",
                "t.json",
                "--output",
                "o.json",
                "--bogus",
            ],
            id="unknown-option",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-trend-dashboard" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_export_trend_dashboard",
        lambda path, output: calls.append((path, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-trend-dashboard", "t.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(path, output):
        calls.append((path, output))
        return b"{}"

    monkeypatch.setattr(
        cli_mod, "_export_trend_dashboard", fake_export
    )
    rc = cli_mod.main(
        [
            "export-trend-dashboard",
            "trend.json",
            "--output",
            "dashboard.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [("trend.json", "dashboard.json")]
    assert captured.out == ""
    assert captured.err == ""


def test_missing_trend_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        [
            "export-trend-dashboard",
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


def test_corrupted_trend_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        [
            "export-trend-dashboard",
            str(bad),
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


def test_output_overlap_error(tmp_path, trend_path):
    result = run_cli(
        [
            "export-trend-dashboard",
            trend_path,
            "--output",
            trend_path,
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

    monkeypatch.setattr(cli_mod, "_export_trend_dashboard", raising)
    rc = cli_mod.main(
        [
            "export-trend-dashboard",
            "t.json",
            "--output",
            "o.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"
