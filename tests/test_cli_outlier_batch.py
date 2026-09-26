"""End-to-end tests for the ``outlier-batch`` CLI subcommand.

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
    "depths": [1, 2, 3, 100],
    "threshold": 3.5,
    "max_outlier_ratio": 0.1,
}

EXPECTED = (
    b'{"results":[[false,1.011735,1.0],[false,0.337245,2.0],'
    b'[false,0.337245,3.0],[true,65.762751,100.0]],'
    b'"summary":{"count":4,"outlier_count":1,"outlier_ratio":0.25,'
    b'"max_score":65.762751,"quality":"fail"}}\n'
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


def test_outlier_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_outlier_batch_optional_keys_may_be_omitted(tmp_path):
    document = {"depths": [2.0, 3.0, 4.0]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b'{"results":[[false,0.67449,2.0],[false,0.0,3.0],[false,0.67449,4.0]],'
        b'"summary":{"count":3,"outlier_count":0,"outlier_ratio":0.0,'
        b'"max_score":0.67449,"quality":"pass"}}\n'
    )


def test_outlier_batch_threshold_only_may_be_omitted(tmp_path):
    document = {"depths": [1, 2, 3, 100], "max_outlier_ratio": 0.25}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert b'"quality":"pass"' in result.stdout


def test_outlier_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before


def test_outlier_batch_calls_batch_exactly_once(tmp_path, monkeypatch, capsys):
    request = write_request(tmp_path / "request.json")
    calls = []
    real_batch = cli_mod._outlier_batch

    def spy(**kwargs):
        calls.append(kwargs)
        return real_batch(**kwargs)

    monkeypatch.setattr(cli_mod, "_outlier_batch", spy)
    assert cli_mod.main(["outlier-batch", request]) == 0
    assert calls == [REQUEST]
    assert capsys.readouterr().out == EXPECTED.decode("utf-8")


def test_outlier_batch_missing_required_key(tmp_path):
    document = {"threshold": 3.5}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: request must contain 'depths'\n"


def test_outlier_batch_extra_key_rejected(tmp_path):
    document = dict(REQUEST, extra=1)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must not contain extra keys\n"


def test_outlier_batch_key_order_enforced(tmp_path):
    raw = b'{"threshold":3.5,"depths":[1,2,3,100]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_outlier_batch_second_optional_order_enforced(tmp_path):
    raw = b'{"depths":[1,2,3,100],"max_outlier_ratio":0.1,"threshold":3.5}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_outlier_batch_duplicate_keys_rejected(tmp_path):
    raw = (
        b'{"depths":[1,2,3],"depths":[4,5,6],"threshold":3.5,'
        b'"max_outlier_ratio":0.1}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains duplicate keys\n"
    )


def test_outlier_batch_non_object_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"[1,2,3]")
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must be a JSON object\n"


def test_outlier_batch_invalid_json_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"{not json")
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid JSON:"
    )


def test_outlier_batch_invalid_utf8_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"\xff\xfe")
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid UTF-8:"
    )


def test_outlier_batch_non_finite_constant_rejected(tmp_path):
    raw = b'{"depths":[1,2,3],"threshold":NaN}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains a non-finite JSON constant: NaN\n"
    )


def test_outlier_batch_domain_error_reported(tmp_path):
    document = dict(REQUEST, max_outlier_ratio=1.5)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == (
        b"ERROR ValueError: max_outlier_ratio must be in [0, 1]\n"
    )


def test_outlier_batch_detect_error_reported(tmp_path):
    document = {"depths": [1, 2]}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["outlier-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"ERROR ValueError: depths must have at least 3 elements\n" == result.stderr
