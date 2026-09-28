"""End-to-end tests for the ``export-overview-comparison-report-trend`` CLI subcommand."""

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


def comparison_report(failed, regressed_delta, passed_delta, quality):
    return {
        "schema_version": 1,
        "source": {"path": "x.json", "kind": "overview_comparison"},
        "summary": {
            "count": 3,
            "failed": failed,
            "regressed_delta": regressed_delta,
            "passed_delta": passed_delta,
        },
        "worst": {
            "index": 1,
            "regressed_delta": regressed_delta,
            "passed_delta": passed_delta,
            "quality": quality,
        },
        "quality": quality,
    }


def write_report(path, failed, regressed_delta, passed_delta, quality):
    doc = comparison_report(
        failed, regressed_delta, passed_delta, quality
    )
    Path(path).write_bytes(
        json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


@pytest.fixture
def report_paths(tmp_path):
    first = tmp_path / "report_a.json"
    second = tmp_path / "report_b.json"
    write_report(first, 0, 0, 2, "pass")
    write_report(second, 1, 1, 1, "fail")
    return [str(first), str(second)]


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


def test_exported():
    assert (
        "export_overview_comparison_report_trend" in product_mod.__all__
    )
    assert hasattr(
        product_mod, "export_overview_comparison_report_trend"
    )


def test_success_silent_exit_0_and_file_written(tmp_path, report_paths):
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-comparison-report-trend",
            *report_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    scratch = tmp_path / "scratch.json"
    expected = product_mod.export_overview_comparison_report_trend(
        report_paths, str(scratch)
    )
    assert output.read_bytes() == expected
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not output.read_bytes().endswith(b"\n")
    document = json.loads(output.read_bytes())
    assert list(document.keys()) == [
        "count",
        "changes",
        "regressed",
        "worst",
        "quality",
    ]


def test_three_reports_silent_exit_0(tmp_path, report_paths):
    third = tmp_path / "report_c.json"
    write_report(third, 1, 0, 1, "fail")
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-comparison-report-trend",
            *report_paths,
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
    assert document["count"] == 3
    assert len(document["changes"]) == 2


def test_reports_keep_command_line_order(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_export(paths, output):
        calls.append((list(paths), output))
        return b"{}"

    monkeypatch.setattr(
        cli_mod,
        "_export_overview_comparison_report_trend",
        fake_export,
    )
    rc = cli_mod.main(
        [
            "export-overview-comparison-report-trend",
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


def test_input_files_not_modified(tmp_path, report_paths):
    before = [Path(path).read_bytes() for path in report_paths]
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-comparison-report-trend",
            *report_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert [Path(path).read_bytes() for path in report_paths] == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(
            ["export-overview-comparison-report-trend"],
            id="missing-all",
        ),
        pytest.param(
            ["export-overview-comparison-report-trend", "a.json"],
            id="only-one-report",
        ),
        pytest.param(
            ["export-overview-comparison-report-trend", "a.json", "b.json"],
            id="missing-output",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-overview-comparison-report-trend" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_export_overview_comparison_report_trend",
        lambda paths, output: calls.append((paths, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(
            ["export-overview-comparison-report-trend", "a.json", "b.json"]
        )
    assert excinfo.value.code == 2
    assert calls == []


def test_missing_report_file(tmp_path, report_paths):
    missing = str(tmp_path / "missing.json")
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-comparison-report-trend",
            report_paths[0],
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


def test_corrupted_report_file(tmp_path, report_paths):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        [
            "export-overview-comparison-report-trend",
            str(bad),
            report_paths[1],
            "--output",
            str(tmp_path / "trend.json"),
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
            "export-overview-comparison-report-trend",
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

    monkeypatch.setattr(
        cli_mod,
        "_export_overview_comparison_report_trend",
        raising,
    )
    rc = cli_mod.main(
        [
            "export-overview-comparison-report-trend",
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


def test_help_lists_command(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-overview-comparison-report-trend" in result.stdout


def test_module_entry_matches_cli(tmp_path, report_paths):
    output = tmp_path / "trend.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get(
        "PYTHONPATH", ""
    )
    env["PYTHONIOENCODING"] = "utf-8"
    args = [
        sys.executable,
        "-m",
        "ocean_sonar",
        "export-overview-comparison-report-trend",
        *report_paths,
        "--output",
        str(output),
    ]
    result = subprocess.run(
        args, cwd=str(tmp_path), env=env, capture_output=True
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == (
        product_mod.serialize_overview_comparison_report_trend(report_paths)
    )


def test_product_calls_serializer_once(tmp_path, monkeypatch, report_paths):
    calls = []
    original = product_mod.serialize_overview_comparison_report_trend

    def counting(paths):
        calls.append(list(paths))
        return original(paths)

    monkeypatch.setattr(
        product_mod,
        "serialize_overview_comparison_report_trend",
        counting,
    )
    output = str(tmp_path / "trend.json")
    returned = product_mod.export_overview_comparison_report_trend(
        report_paths, output
    )
    assert calls == [report_paths]
    assert returned == Path(output).read_bytes()


def test_product_paths_error_precedes_output(tmp_path):
    with pytest.raises(ValueError, match="at least 2 items"):
        product_mod.export_overview_comparison_report_trend(
            ["a.json"], 123
        )
