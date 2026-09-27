"""End-to-end tests for the ``export-overview-trend`` CLI subcommand."""

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
def overview_paths(tmp_path, monkeypatch):
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
    first = product_mod.serialize_overview(
        "product.json", "substrate.json", "crosspoint.json"
    )
    p0 = tmp_path / "overview0.json"
    p0.write_bytes(first)
    p1 = tmp_path / "overview1.json"
    p1.write_bytes(first)
    return [str(p0), str(p1)]


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


def test_success_silent_exit_0_and_file_written(tmp_path, overview_paths):
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-trend",
            overview_paths[0],
            overview_paths[1],
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    scratch = tmp_path / "scratch.json"
    assert output.read_bytes() == product_mod.export_overview_trend(
        overview_paths, str(scratch)
    )


def test_three_overviews_silent_exit_0(tmp_path, overview_paths):
    third = tmp_path / "overview2.json"
    third.write_bytes(Path(overview_paths[1]).read_bytes())
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-trend",
            overview_paths[0],
            overview_paths[1],
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
    assert list(document.keys()) == [
        "count",
        "changes",
        "regressed",
        "worst",
        "quality",
    ]
    assert document["count"] == 3
    assert len(document["changes"]) == 2


def test_input_files_not_modified(tmp_path, overview_paths):
    before = [Path(path).read_bytes() for path in overview_paths]
    output = tmp_path / "trend.json"
    result = run_cli(
        [
            "export-overview-trend",
            *overview_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    after = [Path(path).read_bytes() for path in overview_paths]
    assert after == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["export-overview-trend"], id="missing-all"),
        pytest.param(
            ["export-overview-trend", "o.json"], id="only-one-overview"
        ),
        pytest.param(
            ["export-overview-trend", "a.json", "b.json"],
            id="missing-output",
        ),
    ],
)
def test_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-overview-trend" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_export_overview_trend",
        lambda paths, output: calls.append((paths, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-overview-trend", "a.json", "b.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_calls_business_exactly_once(monkeypatch, capsys):
    calls = []

    def fake_export(paths, output):
        calls.append((list(paths), output))
        return b"{}"

    monkeypatch.setattr(cli_mod, "_export_overview_trend", fake_export)
    rc = cli_mod.main(
        [
            "export-overview-trend",
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


def test_missing_overview_file(tmp_path, overview_paths):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        [
            "export-overview-trend",
            overview_paths[0],
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


def test_corrupted_overview_file(tmp_path, overview_paths):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        [
            "export-overview-trend",
            str(bad),
            overview_paths[1],
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


def test_output_overlap_error(tmp_path, overview_paths):
    result = run_cli(
        [
            "export-overview-trend",
            *overview_paths,
            "--output",
            overview_paths[0],
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

    monkeypatch.setattr(cli_mod, "_export_overview_trend", raising)
    rc = cli_mod.main(
        [
            "export-overview-trend",
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


def test_help_lists_export_overview_trend(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"export-overview-trend" in result.stdout
