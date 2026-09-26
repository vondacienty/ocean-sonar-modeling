"""End-to-end tests for the ``audit-comparisons`` CLI subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.crosspoint import audit_comparisons

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_comparison(path, changes):
    """Write a canonical serialize_comparison-shaped JSON file."""
    quality = "fail" if any(c["quality"] == "fail" for c in changes) else "pass"
    document = {"changes": changes, "worst": changes[0], "quality": quality}
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return str(path)


def change(index, degraded_delta, coverage_delta, score_delta, quality):
    return {
        "index": index,
        "degraded_delta": degraded_delta,
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "quality": quality,
    }


@pytest.fixture
def comparison_paths(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json", [change(1, 1, -0.2, -0.5, "fail")]
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


def test_audit_comparisons_success_exact_output(tmp_path, comparison_paths):
    result = run_cli(
        ["audit-comparisons", *comparison_paths], cwd=tmp_path
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b'{"files":2,"changes":2,"failed":1,'
        b'"worst":[1,1,1,-0.2,-0.5,"fail"],"quality":"fail"}\n'
    )
    assert result.stdout.count(b"\n") == 1
    decoded = json.loads(result.stdout)
    assert list(decoded.keys()) == [
        "files",
        "changes",
        "failed",
        "worst",
        "quality",
    ]
    assert decoded["worst"] == [1, 1, 1, -0.2, -0.5, "fail"]


def test_audit_comparisons_output_matches_function(tmp_path, comparison_paths):
    result = run_cli(
        ["audit-comparisons", *comparison_paths], cwd=tmp_path
    )
    expected = json.dumps(
        audit_comparisons(comparison_paths),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"
    assert result.stdout == expected.encode("utf-8")


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="no-paths"),
        pytest.param(["only_one.json"], id="single-path"),
    ],
)
def test_audit_comparisons_too_few_paths_is_argparse_error(tmp_path, extra):
    result = run_cli(["audit-comparisons", *extra], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"audit-comparisons" in result.stderr


def test_audit_comparisons_too_few_paths_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod, "audit_comparisons", lambda paths: calls.append(paths)
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["audit-comparisons", "only_one.json"])
    assert excinfo.value.code == 2
    assert calls == []


def test_audit_comparisons_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    ok = write_comparison(
        tmp_path / "ok.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    result = run_cli(["audit-comparisons", ok, missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_audit_comparisons_corrupted_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    ok = write_comparison(
        tmp_path / "ok.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    result = run_cli(["audit-comparisons", ok, str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_audit_comparisons_directory_path(tmp_path, comparison_paths):
    result = run_cli(
        ["audit-comparisons", comparison_paths[0], str(tmp_path)],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR IsADirectoryError: ")
    assert result.stderr.endswith(b"\n")


def test_audit_comparisons_calls_business_exactly_once_with_ordered_list(
    monkeypatch, capsys
):
    calls = []

    def fake_audit(paths):
        calls.append(paths)
        return {
            "files": 2,
            "changes": 1,
            "failed": 0,
            "worst": (0, 1, 0, 0.0, 0.0, "pass"),
            "quality": "pass",
        }

    monkeypatch.setattr(cli_mod, "audit_comparisons", fake_audit)
    rc = cli_mod.main(["audit-comparisons", "z.json", "a.json", "m.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [["z.json", "a.json", "m.json"]]
    assert captured.out == (
        '{"files":2,"changes":1,"failed":0,'
        '"worst":[0,1,0,0.0,0.0,"pass"],"quality":"pass"}\n'
    )
    assert captured.err == ""


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("paths must be a list or tuple"), id="type-error"),
        pytest.param(ValueError("paths must contain at least 2 items"), id="value-error"),
        pytest.param(FileNotFoundError(2, "No such file or directory", "x.json"), id="file-not-found"),
        pytest.param(IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"),
    ],
)
def test_audit_comparisons_exception_passthrough(monkeypatch, capsys, exc):
    def raising(paths):
        raise exc

    monkeypatch.setattr(cli_mod, "audit_comparisons", raising)
    rc = cli_mod.main(["audit-comparisons", "a.json", "b.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_audit_comparisons_does_not_modify_input_files(
    tmp_path, comparison_paths
):
    before = [Path(p).read_bytes() for p in comparison_paths]
    result = run_cli(
        ["audit-comparisons", *comparison_paths], cwd=tmp_path
    )
    assert result.returncode == 0
    assert [Path(p).read_bytes() for p in comparison_paths] == before


def test_help_lists_audit_comparisons(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"audit-comparisons" in result.stdout
