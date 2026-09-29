"""End-to-end tests for the ``export-dashboard-history-report`` CLI."""

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


def dashboard_doc(changes):
    n = len(changes)
    r = sum(1 for c in changes if c["quality"] == "fail")
    p = n - r
    ratio = round(float(p / n), 6)
    if ratio == 0:
        ratio = 0.0
    worst = min(
        changes,
        key=lambda c: (
            c["passed_delta"],
            -c["failed_delta"],
            -c["regressed_delta"],
            c["index"],
        ),
    )
    return {
        "trend": {
            "count": n + 1,
            "changes": changes,
            "regressed": r,
            "worst": worst,
            "quality": "pass" if r == 0 else "fail",
        },
        "summary": {
            "reports": n + 1,
            "passed": p,
            "regressed": r,
            "ratio": ratio,
            "worst": worst["index"],
        },
        "quality": "pass" if r == 0 else "fail",
    }


def write_dashboard(tmp_path, doc, name):
    path = tmp_path / name
    path.write_bytes(
        product_mod._dump_overview_comparison_report_trend(doc)
    )
    return str(path)


@pytest.fixture
def dashboard_paths(tmp_path):
    passing = dashboard_doc(
        [item(i + 1, 0, 0, 1, "pass") for i in range(3)]
    )
    one_fail = dashboard_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 1, -1, "fail"),
            item(3, 0, 0, 1, "pass"),
        ]
    )
    two_fail = dashboard_doc(
        [
            item(1, 1, 1, -1, "fail"),
            item(2, 1, 1, -1, "fail"),
            item(3, 0, 0, 1, "pass"),
        ]
    )
    return (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, two_fail, "c.json"),
    )


@pytest.fixture
def history_path(tmp_path, dashboard_paths):
    path = tmp_path / "history.json"
    path.write_bytes(
        product_mod.serialize_dashboard_history(list(dashboard_paths))
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
    assert b"export-dashboard-history-report" in result.stdout


def test_success_silent_exit_0_and_file_written(
    tmp_path, history_path, dashboard_paths
):
    output = tmp_path / "report.json"
    result = run_cli(
        [
            "export-dashboard-history-report",
            history_path,
            *dashboard_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    scratch = tmp_path / "scratch.json"
    expected = product_mod.export_dashboard_history_report(
        history_path, list(dashboard_paths), str(scratch)
    )
    assert output.read_bytes() == expected
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not output.read_bytes().endswith(b"\n")
    document = json.loads(output.read_bytes())
    assert list(document.keys()) == [
        "schema_version",
        "source",
        "history",
        "summary",
        "quality",
    ]


def test_dashboard_order_preserved_and_called_once(monkeypatch, capsys):
    calls = []

    def fake_export(path, paths, output):
        calls.append((path, list(paths), output))
        return b"{}"

    monkeypatch.setattr(
        cli_mod, "_export_dashboard_history_report", fake_export
    )
    rc = cli_mod.main(
        [
            "export-dashboard-history-report",
            "history.json",
            "a.json",
            "b.json",
            "c.json",
            "--output",
            "report.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [
        ("history.json", ["a.json", "b.json", "c.json"], "report.json")
    ]
    assert captured.out == ""
    assert captured.err == ""


def test_input_files_not_modified(
    tmp_path, history_path, dashboard_paths
):
    before_history = Path(history_path).read_bytes()
    before = [Path(p).read_bytes() for p in dashboard_paths]
    output = tmp_path / "report.json"
    result = run_cli(
        [
            "export-dashboard-history-report",
            history_path,
            *dashboard_paths,
            "--output",
            str(output),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert Path(history_path).read_bytes() == before_history
    assert [Path(p).read_bytes() for p in dashboard_paths] == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(
            ["export-dashboard-history-report"],
            id="missing-all",
        ),
        pytest.param(
            ["export-dashboard-history-report", "h.json"],
            id="missing-dashboards",
        ),
        pytest.param(
            ["export-dashboard-history-report", "h.json", "a.json"],
            id="only-one-dashboard",
        ),
        pytest.param(
            ["export-dashboard-history-report", "h.json", "a.json", "b.json"],
            id="missing-output",
        ),
        pytest.param(
            [
                "export-dashboard-history-report",
                "h.json",
                "a.json",
                "b.json",
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
    assert b"export-dashboard-history-report" in result.stderr


def test_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_export_dashboard_history_report",
        lambda path, paths, output: calls.append((path, paths, output)),
    )
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(
            ["export-dashboard-history-report", "h.json", "a.json"]
        )
    assert excinfo.value.code == 2
    assert calls == []


def test_missing_history_file(tmp_path, dashboard_paths):
    missing = str(tmp_path / "missing.json")
    result = run_cli(
        [
            "export-dashboard-history-report",
            missing,
            *dashboard_paths,
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


def test_cross_check_mismatch(tmp_path, history_path, dashboard_paths):
    other = dashboard_doc(
        [
            item(1, 1, 1, -1, "fail"),
            item(2, 1, 1, -1, "fail"),
            item(3, 0, 0, 1, "pass"),
        ]
    )
    replaced = write_dashboard(tmp_path, other, "a.json")
    result = run_cli(
        [
            "export-dashboard-history-report",
            history_path,
            replaced,
            dashboard_paths[1],
            dashboard_paths[2],
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
    assert not (tmp_path / "o.json").exists()


def test_output_overlap_with_history(tmp_path, history_path, dashboard_paths):
    result = run_cli(
        [
            "export-dashboard-history-report",
            history_path,
            *dashboard_paths,
            "--output",
            history_path,
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert b"same file" in result.stderr
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_output_overlap_with_dashboard(
    tmp_path, history_path, dashboard_paths
):
    result = run_cli(
        [
            "export-dashboard-history-report",
            history_path,
            *dashboard_paths,
            "--output",
            dashboard_paths[1],
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
    def raising(path, paths, output):
        raise exc

    monkeypatch.setattr(
        cli_mod, "_export_dashboard_history_report", raising
    )
    rc = cli_mod.main(
        [
            "export-dashboard-history-report",
            "h.json",
            "a.json",
            "b.json",
            "--output",
            "o.json",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"
