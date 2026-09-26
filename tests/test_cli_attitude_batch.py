"""End-to-end tests for the ``attitude-batch`` CLI subcommand.

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
    "observations": [
        [0, 0, 10, 0, 0, 2.5],
        [0, 0, 10, 0, 0, 0.5],
    ],
    "limit": 1.0,
}

EXPECTED = (
    b'{"results":[[0.0,0.0,7.5,-2.5,false],[0.0,0.0,9.5,-0.5,true]],'
    b'"summary":{"count":2,"pass_count":1,'
    b'"max_abs_adjustment":2.5,"quality":"fail"}}\n'
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


def test_attitude_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_attitude_batch_optional_limit_may_be_omitted(tmp_path):
    document = {"observations": REQUEST["observations"]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b'{"results":[[0.0,0.0,7.5,-2.5,false],[0.0,0.0,9.5,-0.5,true]],'
        b'"summary":{"count":2,"pass_count":1,'
        b'"max_abs_adjustment":2.5,"quality":"fail"}}\n'
    )


def test_attitude_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before


def test_attitude_batch_calls_batch_exactly_once(tmp_path, monkeypatch, capsys):
    request = write_request(tmp_path / "request.json")
    calls = []
    real_batch = cli_mod._attitude_batch

    def spy(**kwargs):
        calls.append(kwargs)
        return real_batch(**kwargs)

    monkeypatch.setattr(cli_mod, "_attitude_batch", spy)
    assert cli_mod.main(["attitude-batch", request]) == 0
    assert calls == [REQUEST]
    assert capsys.readouterr().out == EXPECTED.decode("utf-8")


def test_attitude_batch_missing_required_key(tmp_path):
    raw = b'{"limit":1.0}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: request must contain 'observations'\n"


def test_attitude_batch_extra_key_rejected(tmp_path):
    document = dict(REQUEST, extra=1)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must not contain extra keys\n"


def test_attitude_batch_key_order_enforced(tmp_path):
    raw = b'{"limit":1.0,"observations":[[0,0,10,0,0,0]]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_attitude_batch_duplicate_keys_rejected(tmp_path):
    raw = b'{"observations":[[0,0,10,0,0,0]],"observations":[[0,0,10,0,0,0]]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains duplicate keys\n"
    )


def test_attitude_batch_non_object_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"[1,2,3]")
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must be a JSON object\n"


def test_attitude_batch_invalid_json_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"{not json")
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(b"ERROR ValueError: request file is not valid JSON:")


def test_attitude_batch_invalid_utf8_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"\xff\xfe")
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(b"ERROR ValueError: request file is not valid UTF-8:")


def test_attitude_batch_non_finite_constant_rejected(tmp_path):
    raw = b'{"observations":[[0,0,10,0,0,0]],"limit":NaN}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains a non-finite JSON constant: NaN\n"
    )


def test_attitude_batch_domain_error_reported(tmp_path):
    document = dict(REQUEST, limit=-1.0)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: limit must be >= 0\n"


def test_attitude_batch_observation_error_reported(tmp_path):
    document = {"observations": [["bad", 0, 10, 0, 0, 0]]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["attitude-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(
        b"ERROR TypeError: observation[0]: x must be a non-bool int or float"
    )


def test_attitude_batch_missing_argument_is_argparse_error(tmp_path):
    result = run_cli(["attitude-batch"], cwd=tmp_path)
    assert result.returncode == 2
