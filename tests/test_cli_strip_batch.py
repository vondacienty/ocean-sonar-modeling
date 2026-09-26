"""End-to-end tests for the ``strip-batch`` CLI subcommand.

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
    "strips": [
        [[0.0, 0.0, 10.0], [10.0, 0.0, 20.0]],
        [[0.0, 0.0, 12.0], [10.0, 0.0, 22.0]],
    ],
    "tolerance": 1.0,
    "max_adjustment": 1.0,
}

EXPECTED = (
    b'{"results":[[0.0,0.0,10.0],[10.0,0.0,20.0],'
    b'[0.0,0.0,10.0],[10.0,0.0,20.0]],'
    b'"summary":{"strip_count":2,"point_count":4,"pass_count":1,'
    b'"max_abs_adjustment":2.0,"quality":"fail"}}\n'
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


def test_strip_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_strip_batch_optional_keys_may_be_omitted(tmp_path):
    document = {
        "strips": [
            [[0.0, 0.0, 10.0], [10.0, 0.0, 20.0]],
            [[0.0, 0.0, 10.0], [10.0, 0.0, 20.0]],
        ]
    }
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b'{"results":[[0.0,0.0,10.0],[10.0,0.0,20.0],'
        b'[0.0,0.0,10.0],[10.0,0.0,20.0]],'
        b'"summary":{"strip_count":2,"point_count":4,"pass_count":2,'
        b'"max_abs_adjustment":0.0,"quality":"pass"}}\n'
    )


def test_strip_batch_tolerance_only_may_be_omitted(tmp_path):
    document = dict(REQUEST)
    del document["tolerance"]
    document["max_adjustment"] = 2.0
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert b'"quality":"pass"' in result.stdout


def test_strip_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before


def test_strip_batch_calls_batch_exactly_once(tmp_path, monkeypatch, capsys):
    request = write_request(tmp_path / "request.json")
    calls = []
    real_batch = cli_mod._strip_batch

    def spy(**kwargs):
        calls.append(kwargs)
        return real_batch(**kwargs)

    monkeypatch.setattr(cli_mod, "_strip_batch", spy)
    assert cli_mod.main(["strip-batch", request]) == 0
    assert calls == [REQUEST]
    assert capsys.readouterr().out == EXPECTED.decode("utf-8")


def test_strip_batch_missing_required_key(tmp_path):
    document = {"tolerance": 1.0}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: request must contain 'strips'\n"


def test_strip_batch_extra_key_rejected(tmp_path):
    document = dict(REQUEST, extra=1)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must not contain extra keys\n"


def test_strip_batch_key_order_enforced(tmp_path):
    raw = b'{"tolerance":1.0,"strips":[[[0,0,1],[1,0,2]],[[0,0,1],[1,0,2]]]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_strip_batch_second_optional_order_enforced(tmp_path):
    raw = (
        b'{"strips":[[[0,0,1],[1,0,2]],[[0,0,1],[1,0,2]]],'
        b'"max_adjustment":1.0,"tolerance":1.0}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_strip_batch_duplicate_keys_rejected(tmp_path):
    raw = (
        b'{"strips":[[[0,0,1],[1,0,2]],[[0,0,1],[1,0,2]]],'
        b'"strips":[[[0,0,1],[1,0,2]],[[0,0,1],[1,0,2]]],"tolerance":1.0}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains duplicate keys\n"
    )


def test_strip_batch_non_object_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"[1,2,3]")
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must be a JSON object\n"


def test_strip_batch_invalid_json_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"{not json")
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid JSON:"
    )


def test_strip_batch_invalid_utf8_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"\xff\xfe")
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid UTF-8:"
    )


def test_strip_batch_non_finite_constant_rejected(tmp_path):
    raw = (
        b'{"strips":[[[0,0,1],[1,0,2]],[[0,0,1],[1,0,2]]],'
        b'"tolerance":NaN}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains a non-finite JSON constant: NaN\n"
    )


def test_strip_batch_domain_error_reported(tmp_path):
    document = dict(REQUEST, max_adjustment=-0.5)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == (
        b"ERROR ValueError: max_adjustment must be >= 0\n"
    )


def test_strip_batch_merge_error_reported(tmp_path):
    document = {"strips": [[[0.0, 0.0, 1.0]]]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["strip-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == (
        b"ERROR ValueError: strips must have at least 2 elements\n"
    )
