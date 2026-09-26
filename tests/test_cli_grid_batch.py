"""End-to-end success regression tests for the ``grid-batch`` CLI subcommand.

A two-resolution request is run through ``python -m ocean_sonar`` with
byte-exact stdout/stderr/exit-code assertions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUEST = {
    "points": [
        [0.5, 0.5, 10.0],
        [1.5, 0.5, 20.0],
        [0.5, 1.5, 30.0],
        [3.5, 3.5, 40.0],
    ],
    "bounds": [0.0, 0.0, 4.0, 4.0],
    "resolutions": [1.0, 2.0],
}

EXPECTED = (
    b'{"results":['
    b'{"resolution":1.0,"nx":4,"ny":4,'
    b'"cells":[[1,10.0],[1,20.0],[0,null],[0,null],[1,30.0],[0,null],'
    b'[0,null],[0,null],[0,null],[0,null],[0,null],[0,null],[0,null],'
    b'[0,null],[0,null],[1,40.0]],"filled":4,"coverage":0.25},'
    b'{"resolution":2.0,"nx":2,"ny":2,'
    b'"cells":[[3,20.0],[0,null],[0,null],[1,40.0]],'
    b'"filled":2,"coverage":0.5}],'
    b'"summary":{"layer_count":2,"total_cells":20,"filled_cells":6,'
    b'"mean_coverage":0.375,"quality":"fail"}}\n'
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


def test_grid_batch_two_resolutions_success_exact_output(tmp_path):
    request = write_request(tmp_path / "request.json")
    result = run_cli(["grid-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED


def test_grid_batch_two_resolutions_pass_with_min_coverage(tmp_path):
    document = dict(REQUEST, min_coverage=0.2)
    request = write_request(tmp_path / "request.json", document)
    result = run_cli(["grid-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED.replace(
        b'"quality":"fail"', b'"quality":"pass"'
    )


def test_grid_batch_request_file_not_modified(tmp_path):
    request = write_request(tmp_path / "request.json")
    before = (tmp_path / "request.json").read_bytes()
    result = run_cli(["grid-batch", request], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "request.json").read_bytes() == before
