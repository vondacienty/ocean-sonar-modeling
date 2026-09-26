"""End-to-end tests for the ``compare-reports``/``export-comparison`` subcommands.

Both subcommands are exercised through ``python -m ocean_sonar`` subprocesses
(byte-exact stdout/stderr/exit-code assertions) and in-process
``ocean_sonar.cli.main`` calls (call-count, passthrough and atomic-write
semantics).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.crosspoint import render_comparison, serialize_comparison

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCES = ["trend_a.json", "trend_b.json"]


def _q6(value):
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def write_report(path, degraded, coverage_delta, score_delta, quality,
                 sources=SOURCES):
    """Write a canonical export_trends-compatible JSON trend report file."""
    document = {
        "sources": list(sources),
        "summary": {
            "file_count": len(sources),
            "changes": 1,
            "degraded": int(degraded),
            "coverage_delta": _q6(coverage_delta),
            "score_delta": _q6(score_delta),
            "worst": [0, 1, 0, 0, _q6(coverage_delta), _q6(score_delta)],
            "quality": quality,
        },
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
def pass_report_paths(tmp_path):
    return [
        write_report(tmp_path / f"report_{k}.json", 0, 0.1, 2.0, "pass")
        for k in range(2)
    ]


@pytest.fixture
def degraded_report_paths(tmp_path):
    return [
        write_report(tmp_path / "report_0.json", 0, 0.1, 2.0, "pass"),
        write_report(tmp_path / "report_1.json", 1, -0.1, -1.0, "fail"),
    ]


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
# compare-reports: success paths
# ---------------------------------------------------------------------------


def test_compare_reports_success_exact_output(tmp_path, degraded_report_paths):
    result = run_cli(["compare-reports", *degraded_report_paths], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b"QUALITY=fail;COUNT=1;WORST_INDEX=1\n"
        b"CHANGE[1]=1,-0.200000,-3.000000,fail\n"
    )


def test_compare_reports_paths_kept_in_command_line_order(tmp_path):
    # Deliberately non-sorted file names: output must follow argument order.
    paths = [
        write_report(tmp_path / "z_last.json", 0, 0.1, 2.0, "pass"),
        write_report(tmp_path / "a_first.json", 1, -0.1, -1.0, "fail"),
        write_report(tmp_path / "m_middle.json", 0, 0.2, 1.0, "pass"),
    ]
    result = run_cli(["compare-reports", *paths], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    expected = render_comparison(paths) + "\n"
    assert result.stdout == expected.encode("utf-8")
    assert result.stdout.split(b"\n")[1].startswith(b"CHANGE[1]=")


# ---------------------------------------------------------------------------
# compare-reports: argument parsing errors (exit 2, business never called)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="no-paths"),
        pytest.param(["only_one.json"], id="single-path"),
    ],
)
def test_compare_reports_too_few_paths_is_argparse_error(tmp_path, extra):
    result = run_cli(["compare-reports", *extra], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"compare-reports" in result.stderr


def test_compare_reports_too_few_paths_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "render_comparison", lambda paths: calls.append(paths)
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["compare-reports", "only_one.json"])
    assert excinfo.value.code == 2
    assert calls == []


# ---------------------------------------------------------------------------
# compare-reports: business exceptions (exit 1, ERROR line on stderr)
# ---------------------------------------------------------------------------


def test_compare_reports_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["compare-reports", missing, missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_compare_reports_corrupted_file(tmp_path, pass_report_paths):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    result = run_cli(
        ["compare-reports", pass_report_paths[0], str(bad)], cwd=tmp_path
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


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
def test_compare_reports_exception_passthrough(monkeypatch, capsys, exc):
    def raising(paths):
        raise exc

    monkeypatch.setattr(cli_mod, "render_comparison", raising)
    rc = cli_mod.main(["compare-reports", "a.json", "b.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_compare_reports_calls_business_exactly_once_with_ordered_list(
    monkeypatch, capsys
):
    calls = []

    def fake_render(paths):
        calls.append(paths)
        return "LINE1\nLINE2"

    monkeypatch.setattr(cli_mod, "render_comparison", fake_render)
    rc = cli_mod.main(["compare-reports", "z.json", "a.json", "m.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [["z.json", "a.json", "m.json"]]
    assert captured.out == "LINE1\nLINE2\n"
    assert captured.err == ""


def test_compare_reports_does_not_modify_input_files(tmp_path, degraded_report_paths):
    before = [Path(p).read_bytes() for p in degraded_report_paths]
    result = run_cli(["compare-reports", *degraded_report_paths], cwd=tmp_path)
    assert result.returncode == 0
    assert [Path(p).read_bytes() for p in degraded_report_paths] == before


# ---------------------------------------------------------------------------
# export-comparison: success paths
# ---------------------------------------------------------------------------


def test_export_comparison_success_silent_and_writes_payload(
    tmp_path, degraded_report_paths
):
    output = tmp_path / "comparison.json"
    result = run_cli(
        ["export-comparison", *degraded_report_paths, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    expected = serialize_comparison(degraded_report_paths)
    assert output.read_bytes() == expected
    # No temporary file is left behind.
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        ["report_0.json", "report_1.json", "comparison.json"]
    )


def test_export_comparison_overwrites_existing_output(tmp_path, pass_report_paths):
    output = tmp_path / "comparison.json"
    output.write_bytes(b"STALE")
    result = run_cli(
        ["export-comparison", *pass_report_paths, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert output.read_bytes() == serialize_comparison(pass_report_paths)


def test_export_comparison_calls_business_exactly_once(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_serialize(paths):
        calls.append(paths)
        return b"PAYLOAD"

    monkeypatch.setattr(cli_mod, "serialize_comparison", fake_serialize)
    output = tmp_path / "out.json"
    rc = cli_mod.main(
        ["export-comparison", "z.json", "a.json", "m.json", "--output", str(output)]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [["z.json", "a.json", "m.json"]]
    assert output.read_bytes() == b"PAYLOAD"
    assert captured.out == ""
    assert captured.err == ""


# ---------------------------------------------------------------------------
# export-comparison: argument parsing errors (exit 2, business never called)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="no-paths-no-output"),
        pytest.param(["only_one.json", "--output", "o.json"], id="single-path"),
        pytest.param(["a.json", "b.json"], id="missing-output"),
    ],
)
def test_export_comparison_argparse_errors(tmp_path, extra):
    result = run_cli(["export-comparison", *extra], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"export-comparison" in result.stderr


def test_export_comparison_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "serialize_comparison", lambda paths: calls.append(paths)
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["export-comparison", "a.json", "b.json"])
    assert excinfo.value.code == 2
    assert calls == []


# ---------------------------------------------------------------------------
# export-comparison: OUTPUT must not coincide with any REPORT
# ---------------------------------------------------------------------------


def test_export_comparison_output_same_as_report(tmp_path, degraded_report_paths):
    before = [Path(p).read_bytes() for p in degraded_report_paths]
    result = run_cli(
        ["export-comparison", *degraded_report_paths,
         "--output", degraded_report_paths[0]],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1
    # The report files are byte-identical and no output was produced.
    assert [Path(p).read_bytes() for p in degraded_report_paths] == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "report_0.json",
        "report_1.json",
    ]


def test_export_comparison_output_hardlink_to_report(tmp_path, degraded_report_paths):
    linked = tmp_path / "linked.json"
    os.link(degraded_report_paths[1], linked)
    before = Path(degraded_report_paths[1]).read_bytes()
    result = run_cli(
        ["export-comparison", *degraded_report_paths, "--output", str(linked)],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert Path(degraded_report_paths[1]).read_bytes() == before


def test_export_comparison_output_symlink_to_report(tmp_path, degraded_report_paths):
    linked = tmp_path / "linked.json"
    os.symlink(degraded_report_paths[0], linked)
    before = Path(degraded_report_paths[0]).read_bytes()
    result = run_cli(
        ["export-comparison", *degraded_report_paths, "--output", str(linked)],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert Path(degraded_report_paths[0]).read_bytes() == before


def test_export_comparison_output_normalized_path_matches_report(
    tmp_path, degraded_report_paths
):
    # A non-normalized spelling of a report path is still the same file.
    weird = str(tmp_path / "sub" / ".." / "report_0.json")
    before = Path(degraded_report_paths[0]).read_bytes()
    result = run_cli(
        ["export-comparison", *degraded_report_paths, "--output", weird],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert Path(degraded_report_paths[0]).read_bytes() == before


def test_paths_identify_same_file_fallback_when_samefile_fails(monkeypatch):
    def raising(first, second):
        raise FileNotFoundError(first)

    monkeypatch.setattr(os.path, "samefile", raising)
    assert cli_mod._paths_identify_same_file(
        os.path.join("sub", "..", "x.json"), "x.json"
    )
    assert not cli_mod._paths_identify_same_file("x.json", "y.json")


# ---------------------------------------------------------------------------
# export-comparison: failures leave OUTPUT and REPORTs untouched
# ---------------------------------------------------------------------------


def test_export_comparison_business_failure_leaves_output_byte_identical(
    tmp_path, pass_report_paths
):
    output = tmp_path / "comparison.json"
    output.write_bytes(b"ORIGINAL")
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        ["export-comparison", pass_report_paths[0], missing,
         "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert output.read_bytes() == b"ORIGINAL"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        ["report_0.json", "report_1.json", "comparison.json"]
    )


def test_export_comparison_replace_failure_cleans_temp_and_keeps_output(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cli_mod, "serialize_comparison", lambda paths: b"PAYLOAD")
    output = tmp_path / "out.json"
    output.write_bytes(b"ORIGINAL")

    def boom(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(cli_mod.os, "replace", boom)
    rc = cli_mod.main(
        ["export-comparison", "a.json", "b.json", "--output", str(output)]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "ERROR OSError: disk gone\n"
    assert output.read_bytes() == b"ORIGINAL"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_export_comparison_exception_passthrough(monkeypatch, capsys):
    def raising(paths):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_mod, "serialize_comparison", raising)
    rc = cli_mod.main(
        ["export-comparison", "a.json", "b.json", "--output", "o.json"]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "ERROR RuntimeError: boom\n"


def test_export_comparison_does_not_modify_input_files(
    tmp_path, degraded_report_paths
):
    before = [Path(p).read_bytes() for p in degraded_report_paths]
    output = tmp_path / "comparison.json"
    result = run_cli(
        ["export-comparison", *degraded_report_paths, "--output", str(output)],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert [Path(p).read_bytes() for p in degraded_report_paths] == before


# ---------------------------------------------------------------------------
# Regression: existing commands keep working
# ---------------------------------------------------------------------------


def test_help_lists_new_subcommands(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert b"compare-reports" in result.stdout
    assert b"export-comparison" in result.stdout
    assert b"render-trends" in result.stdout
    assert b"export-trends" in result.stdout
    assert b"rank-batches" in result.stdout
    assert b"version" in result.stdout
