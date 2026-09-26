"""End-to-end tests for the ``terrain-batch`` CLI subcommand.

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
    "r": 1.0,
    "nx": 3,
    "ny": 3,
    "cells": [
        [1, 10], [1, 10], [1, 10],
        [1, 10], [1, 10], [1, 12],
        [1, 10], [1, 10], [1, 10],
    ],
    "slope_limit": 5.0,
    "roughness_limit": 1.0,
}

EXPECTED = (
    b'{"results":[[null,0.0,false],[null,2.0,false],[null,2.0,false],'
    b'[null,0.0,false],[45.0,2.0,false],[null,2.0,false],'
    b'[null,0.0,false],[null,2.0,false],[null,2.0,false]],'
    b'"summary":{"count":9,"valid":1,"pass_count":0,"quality":"fail"}}\n'
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


def test_terrain_batch_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_terrain_batch_optional_keys_may_be_omitted(tmp_path):
    document = {key: REQUEST[key] for key in ("r", "nx", "ny", "cells")}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    # Defaults are the same limits as in REQUEST.
    assert result.stdout == EXPECTED


def test_terrain_batch_first_optional_only_may_be_omitted(tmp_path):
    document = {
        key: REQUEST[key]
        for key in ("r", "nx", "ny", "cells", "roughness_limit")
    }
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert b'"quality":"fail"' in result.stdout


def test_terrain_batch_relaxed_limits_pass(tmp_path):
    document = dict(REQUEST, slope_limit=45, roughness_limit=2)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert b'"pass_count":1,"quality":"pass"' in result.stdout


def test_terrain_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before


def test_terrain_batch_calls_batch_exactly_once(tmp_path, monkeypatch, capsys):
    request = write_request(tmp_path / "request.json")
    calls = []
    real_batch = cli_mod._terrain_batch

    def spy(**kwargs):
        calls.append(kwargs)
        return real_batch(**kwargs)

    monkeypatch.setattr(cli_mod, "_terrain_batch", spy)
    assert cli_mod.main(["terrain-batch", request]) == 0
    assert calls == [REQUEST]
    assert capsys.readouterr().out == EXPECTED.decode("utf-8")


def test_terrain_batch_missing_required_key(tmp_path):
    document = {"nx": 3, "ny": 3, "cells": []}
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: request must contain 'r'\n"


def test_terrain_batch_extra_key_rejected(tmp_path):
    document = dict(REQUEST, extra=1)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must not contain extra keys\n"


def test_terrain_batch_key_order_enforced(tmp_path):
    raw = b'{"nx":3,"r":1.0,"ny":3,"cells":[]}'
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_terrain_batch_optional_order_enforced(tmp_path):
    raw = (
        b'{"r":1.0,"nx":3,"ny":3,"cells":[],'
        b'"roughness_limit":1.0,"slope_limit":5.0}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request keys must follow the batch signature order\n"
    )


def test_terrain_batch_duplicate_keys_rejected(tmp_path):
    raw = (
        b'{"r":1.0,"nx":3,"ny":3,"nx":3,"cells":[]}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains duplicate keys\n"
    )


def test_terrain_batch_non_object_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"[1,2,3]")
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == b"ERROR ValueError: request must be a JSON object\n"


def test_terrain_batch_invalid_json_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"{not json")
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid JSON:"
    )


def test_terrain_batch_invalid_utf8_rejected(tmp_path):
    request = write_request(tmp_path / "request.json", raw=b"\xff\xfe")
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith(
        b"ERROR ValueError: request file is not valid UTF-8:"
    )


def test_terrain_batch_non_finite_constant_rejected(tmp_path):
    raw = (
        b'{"r":1.0,"nx":3,"ny":3,'
        b'"cells":[[1,10],[1,10],[1,10],[1,10],[1,10],[1,12],[1,10],[1,10],[1,10]],'
        b'"slope_limit":Infinity}'
    )
    request = write_request(tmp_path / "request.json", raw=raw)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == (
        b"ERROR ValueError: request file is not valid JSON: "
        b"request contains a non-finite JSON constant: Infinity\n"
    )


def test_terrain_batch_domain_error_reported(tmp_path):
    document = dict(REQUEST, slope_limit=0.0)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: slope_limit must be > 0\n"


def test_terrain_batch_analyze_error_reported(tmp_path):
    document = dict(REQUEST, r=-1.0)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"ERROR ValueError: r must be > 0\n"


def test_terrain_batch_cell_error_reported(tmp_path):
    document = {
        "r": 1.0,
        "nx": 1,
        "ny": 1,
        "cells": [[1, None]],
    }
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["terrain-batch", request], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == (
        b"ERROR TypeError: cells[0]: mean must be a non-bool int or float\n"
    )
