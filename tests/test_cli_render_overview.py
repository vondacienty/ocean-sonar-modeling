"""End-to-end tests for the ``render-overview`` CLI subcommand.

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

EXPECTED = (
    b"OVERVIEW=pass,3,3,0\n"
    b"PRODUCT=pass,1,1,0,0.100000\n"
    b"SUBSTRATE=pass,2,1,0,0,0.000000\n"
    b"CROSSPOINT=pass,2,1,0,0,0.000000\n"
)


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


@pytest.fixture
def overview_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        product_mod,
        "quality_dashboard",
        lambda path: product_section(),
    )
    monkeypatch.setattr(
        product_mod.substrate,
        "load_aggregate_report_trend",
        lambda path: substrate_section(),
    )
    monkeypatch.setattr(
        product_mod.crosspoint,
        "load_audit_report_trend",
        lambda path: crosspoint_section(),
    )
    data = product_mod.serialize_overview(
        "product.json", "substrate.json", "crosspoint.json"
    )
    path = tmp_path / "overview.json"
    path.write_bytes(data)
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


def test_success_exact_output(tmp_path, overview_path):
    result = run_cli(["render-overview", overview_path], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_input_file_not_modified(tmp_path, overview_path):
    before = Path(overview_path).read_bytes()
    result = run_cli(["render-overview", overview_path], cwd=tmp_path)
    assert result.returncode == 0
    assert Path(overview_path).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["render-overview"], id="missing-input"),
        pytest.param(
            ["render-overview", "a.json", "b.json"], id="extra-positional"
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"render-overview" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "_render_overview", lambda path: calls.append(path)
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["render-overview"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_render(path):
        calls.append(path)
        return "OVERVIEW=pass,3,3,0"

    monkeypatch.setattr(cli_mod, "_render_overview", fake_render)
    rc = cli_mod.main(["render-overview", "in.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == ["in.json"]
    assert captured.out == "OVERVIEW=pass,3,3,0\n"
    assert captured.err == ""


def test_missing_input_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["render-overview", missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_corrupted_input_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(["render-overview", str(bad)], cwd=tmp_path)
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

    monkeypatch.setattr(cli_mod, "_render_overview", raising)
    rc = cli_mod.main(["render-overview", "in.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_help_lists_render_overview(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"render-overview" in result.stdout
