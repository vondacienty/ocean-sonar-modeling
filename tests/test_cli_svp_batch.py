"""End-to-end tests for the ``svp-batch`` CLI subcommand."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocean_sonar.cli as cli_mod
from ocean_sonar.svp import batch

REPO_ROOT = Path(__file__).resolve().parents[1]

Z = [0, 10, 20]
C = [1500, 1480, 1510]
RAYS = [[30.0, 0.02], [45.0, 0.01]]


def write_request(path, *, rays=None, z0=0.0, limit=1000.0):
    """Write a canonical REQUEST JSON object with signature key order."""
    document = {
        "z": Z,
        "c": C,
        "rays": RAYS if rays is None else rays,
        "z0": z0,
        "limit": limit,
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


def test_svp_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json", limit=6.0)
    result = run_cli(["svp-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    expected = batch(Z, C, RAYS, 0.0, 6.0).decode("utf-8") + "\n"
    assert result.stdout == expected.encode("utf-8")
    assert result.stdout.count(b"\n") == 1
    decoded = json.loads(result.stdout)
    assert list(decoded.keys()) == ["results", "summary"]


def test_svp_batch_output_matches_function(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["svp-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == batch(Z, C, RAYS, 0.0, 1000.0) + b"\n"


def test_svp_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = Path(request).read_bytes()
    result = run_cli(["svp-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert Path(request).read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["svp-batch"], id="missing-request"),
        pytest.param(["svp-batch", "a.json", "b.json"], id="extra-positional"),
    ],
)
def test_svp_batch_argparse_errors_exit_2(tmp_path, args):
    result = run_cli(args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr.startswith(b"usage: ")
    assert b"svp-batch" in result.stderr


def test_svp_batch_argparse_error_never_calls_business(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "load_batch_request",
        lambda path: calls.append(path),
    )
    monkeypatch.setattr(cli_mod, "batch", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["svp-batch"])
    assert excinfo.value.code == 2
    assert calls == []


def test_svp_batch_calls_batch_exactly_once(monkeypatch, capsys):
    loaded = []
    calls = []
    sentinel = b'{"results":[]}'

    monkeypatch.setattr(
        cli_mod,
        "load_batch_request",
        lambda path: loaded.append(path) or {
            "z": [0],
            "c": [1500.0],
            "rays": [[30.0, 1.0]],
            "z0": 0.0,
            "limit": 1000.0,
        },
    )

    def fake_batch(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(cli_mod, "batch", fake_batch)
    rc = cli_mod.main(["svp-batch", "request.json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert loaded == ["request.json"]
    assert calls == [
        {
            "z": [0],
            "c": [1500.0],
            "rays": [[30.0, 1.0]],
            "z0": 0.0,
            "limit": 1000.0,
        }
    ]
    assert captured.out == sentinel.decode("utf-8") + "\n"
    assert captured.err == ""


def test_svp_batch_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["svp-batch", missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_svp_batch_directory_path(tmp_path):
    result = run_cli(["svp-batch", str(tmp_path)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR IsADirectoryError: ")
    assert result.stderr.endswith(b"\n")


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"{", id="invalid-json"),
        pytest.param(b"[1,2]", id="not-object"),
        pytest.param(
            b'{"z":[0],"c":[1500],"rays":[[30.0,1.0]],"z0":0.0}',
            id="missing-key",
        ),
        pytest.param(
            b'{"z":[0],"c":[1500],"rays":[[30.0,1.0]],'
            b'"limit":1000.0,"z0":0.0}',
            id="wrong-key-order",
        ),
    ],
)
def test_svp_batch_illegal_request_content(tmp_path, content):
    bad = tmp_path / "bad.json"
    bad.write_bytes(content)
    result = run_cli(["svp-batch", str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert result.stderr.endswith(b"\n")
    assert result.stderr.count(b"\n") == 1


def test_svp_batch_batch_validation_error_surfaces(tmp_path):
    # z0 is a float while a/t are ints: trace raises TypeError via batch.
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"z":[0],"c":[1500],"rays":[[30,1]],"z0":0.0,"limit":1000}',
        encoding="utf-8",
    )
    result = run_cli(["svp-batch", str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR TypeError: ")
    assert b"same type" in result.stderr


def test_svp_batch_negative_limit_surfaces(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"z":[0],"c":[1500],"rays":[[30.0,1.0]],"z0":0.0,"limit":-1}',
        encoding="utf-8",
    )
    result = run_cli(["svp-batch", str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(b"ERROR ValueError: ")
    assert b"limit" in result.stderr


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("path must be a str"), id="type-error"),
        pytest.param(ValueError("file is not valid JSON"), id="value-error"),
        pytest.param(
            FileNotFoundError(2, "No such file or directory", "x.json"),
            id="file-not-found",
        ),
        pytest.param(IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"),
    ],
)
def test_svp_batch_exception_format(monkeypatch, capsys, exc):
    def raising(path):
        raise exc

    monkeypatch.setattr(cli_mod, "load_batch_request", raising)
    rc = cli_mod.main(["svp-batch", "request.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == f"ERROR {type(exc).__name__}: {exc}\n"


def test_svp_batch_batch_exception_format(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_mod,
        "load_batch_request",
        lambda path: {
            "z": [0],
            "c": [1500.0],
            "rays": [],
            "z0": 0.0,
            "limit": 1000.0,
        },
    )
    exc = ValueError("rays must be non-empty")

    def raising(**kwargs):
        raise exc

    monkeypatch.setattr(cli_mod, "batch", raising)
    rc = cli_mod.main(["svp-batch", "request.json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "ERROR ValueError: rays must be non-empty\n"


def test_help_lists_svp_batch(tmp_path):
    result = run_cli(["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert b"svp-batch" in result.stdout
