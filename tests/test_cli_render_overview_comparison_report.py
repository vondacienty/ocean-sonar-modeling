"""End-to-end tests for the ``render-overview-comparison-report`` CLI subcommand.

The subcommand is exercised both through ``python -m ocean_sonar``
subprocesses (byte-exact stdout/stderr/exit-code assertions) and through
in-process ``ocean_sonar.cli.main`` calls (call-count and passthrough
semantics).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar import product as product_mod

REPO_ROOT = Path(__file__).resolve().parents[1]


def trend_item(index=1, failed_delta=0, coverage_delta=0.1, quality="pass"):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "coverage_delta": coverage_delta,
        "quality": quality,
    }


def product_section(item=None):
    item = item or trend_item()
    quality = item["quality"]
    passed = 1 if quality == "pass" else 0
    return {
        "trend": {
            "changes": (item,),
            "worst": item,
            "quality": quality,
        },
        "summary": {
            "count": 1,
            "passed": passed,
            "failed": 1 - passed,
            "coverage_delta": item["coverage_delta"],
        },
        "quality": quality,
    }


def substrate_section(quality="pass"):
    regressed = 0 if quality == "pass" else 1
    return {
        "count": 2,
        "changes": 1,
        "regressed": regressed,
        "unknown_delta": 0,
        "unknown_ratio_delta": 0.0,
        "worst": (1, 0, 0.0, quality),
        "quality": quality,
    }


def crosspoint_section(quality="pass"):
    regressed = 0 if quality == "pass" else 1
    failed_delta = 1 if quality == "fail" else 0
    return {
        "sources": ["a.json", "b.json"],
        "trend": {
            "count": 2,
            "changes": 1,
            "regressed": regressed,
            "failed_delta": failed_delta,
            "pass_ratio_delta": 0.0,
            "worst": (1, failed_delta, 0.0, quality),
            "quality": quality,
        },
    }


def install_sections(monkeypatch, domains):
    product_quality, substrate_quality, crosspoint_quality = domains
    if product_quality == "pass":
        product = product_section()
    else:
        product = product_section(
            trend_item(failed_delta=1, coverage_delta=-0.2, quality="fail")
        )
    monkeypatch.setattr(
        product_mod, "quality_dashboard", lambda path: product
    )
    monkeypatch.setattr(
        product_mod.substrate,
        "load_aggregate_report_trend",
        lambda path: substrate_section(substrate_quality),
    )
    monkeypatch.setattr(
        product_mod.crosspoint,
        "load_audit_report_trend",
        lambda path: crosspoint_section(crosspoint_quality),
    )


@pytest.fixture
def report_path(tmp_path, monkeypatch):
    domains = ("pass", "pass", "pass")
    overview_paths = []
    for i in range(3):
        install_sections(monkeypatch, domains)
        data = product_mod.serialize_overview(
            "product.json", "substrate.json", "crosspoint.json"
        )
        p = tmp_path / f"overview{i}.json"
        p.write_bytes(data)
        overview_paths.append(str(p))

    trend_report_paths = []
    for i in range(2):
        trend_data = product_mod.serialize_overview_trend(
            [overview_paths[i], overview_paths[i + 1]]
        )
        trend_p = tmp_path / f"overview_trend{i}.json"
        trend_p.write_bytes(trend_data)
        trend_report_p = tmp_path / f"overview_trend_report{i}.json"
        product_mod.export_overview_trend_report(
            str(trend_p), str(trend_report_p)
        )
        trend_report_paths.append(str(trend_report_p))

    comparison_data = product_mod.serialize_overview_comparison(
        trend_report_paths
    )
    comparison_p = tmp_path / "overview_comparison.json"
    comparison_p.write_bytes(comparison_data)
    path = tmp_path / "overview_comparison_report.json"
    product_mod.export_overview_comparison_report(
        str(comparison_p), str(path)
    )
    return str(path)


def expected_for(report):
    return (
        b"REPORT=1,\""
        + str(Path(report).parent / "overview_comparison.json").encode("utf-8")
        + b"\",overview_comparison,pass\n"
        b"SUMMARY=1,0,0,0\n"
        b"WORST=1,0,0,pass\n"
    )


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


def test_success_exact_output(tmp_path, report_path):
    result = run_cli(
        ["render-overview-comparison-report", report_path], cwd=tmp_path
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == expected_for(report_path)


def test_input_file_not_modified(tmp_path, report_path):
    before = Path(report_path).read_bytes()
    result = run_cli(
        ["render-overview-comparison-report", report_path], cwd=tmp_path
    )
    assert result.returncode == 0
    assert Path(report_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["render-overview-comparison-report"], id="missing-input"),
        pytest.param(
            ["render-overview-comparison-report", "a.json", "b.json"],
            id="extra-positional",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"render-overview-comparison-report" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_render_overview_comparison_report",
        lambda path: calls.append(path),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["render-overview-comparison-report"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_render(path):
        calls.append(path)
        return "REPORT=1,\"x\",overview_comparison,pass"

    monkeypatch.setattr(
        cli_mod, "_render_overview_comparison_report", fake_render
    )
    rc = cli_mod.main(
        ["render-overview-comparison-report", "in.json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == ["in.json"]
    assert captured.out == "REPORT=1,\"x\",overview_comparison,pass\n"
    assert captured.err == ""


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        ["render-overview-comparison-report", missing], cwd=tmp_path
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_corrupted_input_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        ["render-overview-comparison-report", str(bad)], cwd=tmp_path
    )
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
        pytest.param(
            IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"
        ),
    ],
)
def test_exception_format(monkeypatch, capsys, exc):
    def raising(path):
        raise exc

    monkeypatch.setattr(
        cli_mod, "_render_overview_comparison_report", raising
    )
    rc = cli_mod.main(["render-overview-comparison-report", "in.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_render_overview_comparison_report(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"render-overview-comparison-report" in result.stdout


def test_cli_matches_python_function(tmp_path, report_path):
    result = run_cli(
        ["render-overview-comparison-report", report_path], cwd=tmp_path
    )
    assert result.returncode == 0
    assert result.stdout.decode("utf-8") == (
        product_mod.render_overview_comparison_report(report_path) + "\n"
    )
