"""End-to-end tests for the ``render-trends`` CLI subcommand.

The subcommand is exercised both through ``python -m ocean_sonar``
subprocesses (byte-exact stdout/stderr/exit-code assertions) and through
in-process ``ocean_sonar.cli.main`` calls (call-count and passthrough
semantics). Existing subcommands are regression-checked here as well.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.crosspoint import render_trends

REPO_ROOT = Path(__file__).resolve().parents[1]


def _q6(value):
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def write_trend(path, count, changes, degraded, coverage_delta, score_delta,
                worst, quality):
    """Write a canonical serialize_trend-compatible JSON trend file."""
    document = {
        "count": int(count),
        "changes": int(changes),
        "degraded": int(degraded),
        "coverage_delta": _q6(coverage_delta),
        "score_delta": _q6(score_delta),
        "worst": [
            int(worst[0]),
            int(worst[1]),
            int(worst[2]),
            _q6(worst[3]),
            _q6(worst[4]),
        ],
        "quality": quality,
    }
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return str(path)


@pytest.fixture
def pass_trend_paths(tmp_path):
    paths = []
    for k in range(2):
        paths.append(
            write_trend(
                tmp_path / f"same_{k}.json",
                2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
            )
        )
    return paths


@pytest.fixture
def degraded_trend_paths(tmp_path):
    p0 = write_trend(
        tmp_path / "trend_0.json",
        2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
    )
    p1 = write_trend(
        tmp_path / "trend_1.json",
        2, 1, 1, -0.1, -1.0, (1, 0, 0, -0.1, -1.0), "fail",
    )
    return [p0, p1]


def run_cli(args, cwd):
    """Run ``python -m ocean_sonar`` with the checkout importable."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "ocean_sonar", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_render_trends_success_exact_output(tmp_path, pass_trend_paths):
    result = run_cli(["render-trends", *pass_trend_paths], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b"TRENDS=2,2,0,0.100000,2.000000,pass\n"
        b"FILES=0:0.050000:1.000000|1:0.050000:1.000000;"
        b"RMSE=0.000000,0.000000;WORST_FILE=0\n"
        b"WORST=0,1,0,0,0.100000,2.000000\n"
    )


def test_render_trends_degraded_quality(tmp_path, degraded_trend_paths):
    result = run_cli(["render-trends", *degraded_trend_paths], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b"TRENDS=2,2,1,0.000000,0.500000,fail\n"
        b"FILES=0:0.050000:1.000000|1:-0.050000:-0.500000;"
        b"RMSE=0.100000,1.500000;WORST_FILE=1\n"
        b"WORST=1,1,0,0,-0.100000,-1.000000\n"
    )


def test_render_trends_paths_kept_in_command_line_order(tmp_path):
    # Deliberately non-sorted file names: output must follow argument order.
    paths = [
        write_trend(
            tmp_path / "z_last.json",
            2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
        ),
        write_trend(
            tmp_path / "a_first.json",
            2, 1, 1, -0.1, -1.0, (1, 0, 0, -0.1, -1.0), "fail",
        ),
        write_trend(
            tmp_path / "m_middle.json",
            3, 2, 0, 0.2, 1.0, (1, 0, 0, 0.2, 1.0), "pass",
        ),
    ]
    result = run_cli(["render-trends", *paths], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    expected = render_trends(paths) + "\n"
    assert result.stdout == expected.encode("utf-8")
    # Three files in argument order, not sorted order.
    assert result.stdout.split(b"\n")[1].startswith(b"FILES=0:")


# ---------------------------------------------------------------------------
# Argument parsing errors (exit 2, business function never called)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="no-paths"),
        pytest.param(["only_one.json"], id="single-path"),
    ],
)
def test_render_trends_too_few_paths_is_argparse_error(tmp_path, extra):
    result = run_cli(["render-trends", *extra], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"render-trends" in result.stderr


def test_render_trends_too_few_paths_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "render_trends", lambda paths: calls.append(paths)
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["render-trends", "only_one.json"])
    assert excinfo.value.code == 2
    assert calls == []


# ---------------------------------------------------------------------------
# Business-function exceptions (exit 1, ERROR line on stderr)
# ---------------------------------------------------------------------------


def test_render_trends_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["render-trends", missing, missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_render_trends_corrupted_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    ok = write_trend(
        tmp_path / "ok.json", 2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass"
    )
    result = run_cli(["render-trends", ok, str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_render_trends_directory_path(tmp_path, pass_trend_paths):
    result = run_cli(
        ["render-trends", pass_trend_paths[0], str(tmp_path)], cwd=tmp_path
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR IsADirectoryError: ")
    assert result.stderr.endswith(b"\n")


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("paths must be a list or tuple"), id="type-error"),
        pytest.param(ValueError("paths must contain at least 2 items"), id="value-error"),
        pytest.param(FileNotFoundError(2, "No such file or directory", "x.json"), id="file-not-found"),
        pytest.param(IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"),
        pytest.param(PermissionError(13, "Permission denied", "x.json"), id="other-oserror"),
    ],
)
def test_render_trends_exception_passthrough(monkeypatch, capsys, exc):
    def raising(paths):
        raise exc

    monkeypatch.setattr(cli_mod, "render_trends", raising)
    rc = cli_mod.main(["render-trends", "a.json", "b.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_render_trends_calls_business_exactly_once_with_ordered_list(
    monkeypatch, capsys
):
    calls = []

    def fake_render(paths):
        calls.append(paths)
        return "LINE1\nLINE2\nLINE3"

    monkeypatch.setattr(cli_mod, "render_trends", fake_render)
    rc = cli_mod.main(["render-trends", "z.json", "a.json", "m.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [["z.json", "a.json", "m.json"]]
    assert captured.out == "LINE1\nLINE2\nLINE3\n"
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Input files are not modified
# ---------------------------------------------------------------------------


def test_render_trends_does_not_modify_input_files(tmp_path, degraded_trend_paths):
    before = [Path(p).read_bytes() for p in degraded_trend_paths]
    result = run_cli(["render-trends", *degraded_trend_paths], cwd=tmp_path)
    assert result.returncode == 0
    assert [Path(p).read_bytes() for p in degraded_trend_paths] == before


# ---------------------------------------------------------------------------
# Regression: existing commands keep working
# ---------------------------------------------------------------------------


def test_version_regression(tmp_path):
    result = run_cli(["version"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""


def test_help_regression_lists_render_trends(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert b"render-trends" in result.stdout
    assert b"rank-batches" in result.stdout
    assert b"version" in result.stdout


def test_no_subcommand_regression(tmp_path):
    result = run_cli([], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert b"usage: " in result.stdout


def test_rank_batches_regression(tmp_path):
    missing = str(tmp_path / "missing.json")
    output = str(tmp_path / "out.json")
    result = run_cli(
        ["rank-batches", missing, "--output", output], cwd=tmp_path
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert not Path(output).exists()
