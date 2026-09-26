"""End-to-end tests for the ``render-trends`` CLI subcommand.

Covers the ``ocean-sonar-modeling`` / ``python -m ocean_sonar`` behaviour of
``render-trends TREND TREND [TREND ...]``:

* success: stdout is exactly ``crosspoint.render_trends(paths)`` plus one
  trailing newline, stderr is empty, exit code 0;
* degraded trends keep the ``fail`` quality semantics of ``render_trends``;
* a single path is an argparse error: usage on stderr, exit code 2, and the
  business function is never called;
* missing/corrupted files surface the original exception as
  ``ERROR <异常类名>: <异常消息>`` on stderr with empty stdout and exit 1;
* input files are not modified;
* the pre-existing ``version``/``--help``/``rank-batches`` behaviour is
  unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli
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
def two_trend_paths(tmp_path):
    # File 0: one change, +0.1 coverage, +2.0 score, no degradation.
    p0 = write_trend(
        tmp_path / "trend_0.json",
        2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
    )
    # File 1: one change, -0.1 coverage, -1.0 score, pass -> fail.
    p1 = write_trend(
        tmp_path / "trend_1.json",
        2, 1, 1, -0.1, -1.0, (1, 0, 0, -0.1, -1.0), "fail",
    )
    return [p0, p1]


def run_cli(args):
    """Run ``python -m ocean_sonar`` from the checkout as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "ocean_sonar", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# In-process contract: exactly one call, CLI order, verbatim paths
# ---------------------------------------------------------------------------


def test_render_trends_called_once_with_cli_order(monkeypatch, capsys):
    calls = []

    def fake_render_trends(paths):
        calls.append(paths)
        return "LINE1\nLINE2\nLINE3"

    monkeypatch.setattr(cli, "render_trends", fake_render_trends)

    rc = cli.main(["render-trends", "b.json", "a.json", "c.json"])

    assert rc == 0
    assert calls == [["b.json", "a.json", "c.json"]]
    assert isinstance(calls[0], list)
    out, err = capsys.readouterr()
    assert out == "LINE1\nLINE2\nLINE3\n"
    assert err == ""


def test_single_path_is_argparse_error_and_never_calls_business(
    monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(
        cli, "render_trends", lambda paths: calls.append(paths)
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["render-trends", "only.json"])

    assert excinfo.value.code == 2
    assert calls == []
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("usage:")
    assert "render-trends" in err


def test_zero_paths_is_argparse_error(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli, "render_trends", lambda paths: calls.append(paths)
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["render-trends"])

    assert excinfo.value.code == 2
    assert calls == []
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("usage:")


def test_business_exception_is_reported_not_replaced(monkeypatch, capsys):
    def boom(paths):
        raise ValueError("broken trend payload")

    monkeypatch.setattr(cli, "render_trends", boom)

    rc = cli.main(["render-trends", "a.json", "b.json"])

    assert rc == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == "ERROR ValueError: broken trend payload\n"


# ---------------------------------------------------------------------------
# Subprocess end-to-end behaviour
# ---------------------------------------------------------------------------


def test_e2e_success_exact_output(two_trend_paths):
    expected = render_trends(two_trend_paths)

    result = run_cli(["render-trends", *two_trend_paths])

    assert result.returncode == 0
    assert result.stdout == (expected + "\n").encode("utf-8")
    assert result.stderr == b""


def test_e2e_degraded_quality(two_trend_paths):
    result = run_cli(["render-trends", *two_trend_paths])

    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        "TRENDS=2,2,1,0.000000,0.500000,fail\n"
        "FILES=0:0.050000:1.000000|1:-0.050000:-0.500000;"
        "RMSE=0.100000,1.500000;WORST_FILE=1\n"
        "WORST=1,1,0,0,-0.100000,-1.000000\n"
    ).encode("utf-8")


def test_e2e_single_path_exit_2():
    result = run_cli(["render-trends", "only.json"])

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage:")
    assert b"render-trends" in result.stderr


def test_e2e_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")

    result = run_cli(["render-trends", missing, missing])

    assert result.returncode == 1
    assert result.stdout == b""
    try:
        render_trends([missing, missing])
    except Exception as exc:
        expected_stderr = f"ERROR {type(exc).__name__}: {exc}\n".encode("utf-8")
    assert result.stderr == expected_stderr
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")


def test_e2e_corrupted_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    good = write_trend(
        tmp_path / "good.json",
        2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
    )

    result = run_cli(["render-trends", good, str(bad)])

    assert result.returncode == 1
    assert result.stdout == b""
    try:
        render_trends([good, str(bad)])
    except Exception as exc:
        expected_stderr = f"ERROR {type(exc).__name__}: {exc}\n".encode("utf-8")
    assert result.stderr == expected_stderr
    assert result.stderr.startswith(b"ERROR ValueError: ")


def test_e2e_input_files_not_modified(two_trend_paths):
    before = [Path(p).read_bytes() for p in two_trend_paths]

    result = run_cli(["render-trends", *two_trend_paths])

    assert result.returncode == 0
    assert [Path(p).read_bytes() for p in two_trend_paths] == before


# ---------------------------------------------------------------------------
# Regression: pre-existing commands are unchanged
# ---------------------------------------------------------------------------


def test_e2e_version_regression():
    result = run_cli(["version"])

    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""


def test_e2e_help_regression_and_lists_render_trends():
    result = run_cli(["--help"])

    assert result.returncode == 0
    assert result.stderr == b""
    assert b"version" in result.stdout
    assert b"rank-batches" in result.stdout
    assert b"render-trends" in result.stdout


def test_e2e_no_subcommand_regression():
    result = run_cli([])

    assert result.returncode == 0
    assert result.stderr == b""
    assert b"usage:" in result.stdout


def test_e2e_rank_batches_still_requires_output(tmp_path):
    result = run_cli(["rank-batches", str(tmp_path / "a.json")])

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage:")
