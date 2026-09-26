"""End-to-end tests for the ``substrate-batch`` CLI subcommand.

The subcommand is exercised both through ``python -m ocean_sonar``
subprocesses (byte-exact stdout/stderr/exit-code assertions) and through
in-process ``ocean_sonar.cli.main`` calls (call-count semantics).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import ocean_sonar.cli as cli_mod

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUEST = {
    "analysis": [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]],
    "intensities": [0.4, 0.6, 0.7, 0.6],
}

EXPECTED = (
    b'{"results":[["mud",1.0],["rock",1.0],["unknown",0.0],["rock",1.0]],'
    b'"summary":{"count":4,"unknown":1,"quality":"fail"}}\n'
)


def write_request(path, document=REQUEST, raw=None):
    if raw is None:
        raw = json.dumps(document).encode("utf-8")
    path.write_bytes(raw)
    return str(path)


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


def test_substrate_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_substrate_batch_all_known_passes(tmp_path):
    document = {
        "analysis": [[3.0, 0.5], [6.0, 2.0]],
        "intensities": [0.4, 0.6],
    }
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == (
        b'{"results":[["mud",1.0],["rock",1.0]],'
        b'"summary":{"count":2,"unknown":0,"quality":"pass"}}\n'
    )


def test_substrate_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before


def test_substrate_batch_calls_batch_exactly_once(tmp_path, monkeypatch, capsys):
    request = write_request(tmp_path / "request.json")
    calls = []
    real_batch = cli_mod._substrate_batch

    def spy(**kwargs):
        calls.append(kwargs)
        return real_batch(**kwargs)

    monkeypatch.setattr(cli_mod, "_substrate_batch", spy)
    assert cli_mod.main(["substrate-batch", request]) == 0
    assert calls == [REQUEST]
    assert capsys.readouterr().out == EXPECTED.decode("utf-8")


def test_substrate_batch_missing_required_key(tmp_path):
    document = {"analysis": [[1.0, 0.0]]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: request must contain 'intensities'\n"


def test_substrate_batch_extra_key_rejected(tmp_path):
    document = dict(REQUEST, extra=1)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must not contain extra keys\n"


def test_substrate_batch_key_order_enforced(tmp_path):
    raw = b'{"intensities":[0.5],"analysis":[[1.0,0.0]]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_substrate_batch_duplicate_keys_rejected(tmp_path):
    raw = b'{"analysis":[[1.0,0.0]],"analysis":[[1.0,0.0]],"intensities":[0.5]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains duplicate keys\n"
    )


def test_substrate_batch_non_object_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"[1,2,3]")
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must be a JSON object\n"


def test_substrate_batch_invalid_json_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"{not json")
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid JSON:"
    )


def test_substrate_batch_invalid_utf8_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"\xff\xfe")
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid UTF-8:"
    )


def test_substrate_batch_non_finite_constant_rejected(tmp_path):
    raw = b'{"analysis":[[1.0,0.0]],"intensities":[Infinity]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains a non-finite JSON constant: Infinity\n"
    )


def test_substrate_batch_domain_error_reported(tmp_path):
    document = {"analysis": [[1.0, 0.0]], "intensities": [1.5]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: intensities[0]: must be in [0, 1]\n"


def test_substrate_batch_grid_error_reported(tmp_path):
    document = {"analysis": [[1.0, None]], "intensities": [0.5]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["substrate-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == (
        b"ERROR TypeError: analysis[0]: q must be a non-bool int or float\n"
    )
