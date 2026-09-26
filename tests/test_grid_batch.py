"""Success regression for ``grid.batch`` / ``grid-batch`` at two resolutions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ocean_sonar import grid

REPO_ROOT = Path(__file__).resolve().parents[1]

# 4x4 points over a 4x4 square; depth depends only on x. At r=1 the grid
# is 4x4 (16 filled cells), at r=2 it is 2x2 (4 filled cells, each
# averaging four soundings).
POINTS = [[x, y, 10 + 2 * x] for y in range(4) for x in range(4)]
BOUNDS = [0, 0, 4, 4]
RESOLUTIONS = [1, 2]

EXPECTED = (
    b'{"results":['
    b'{"resolution":1.0,"nx":4,"ny":4,'
    b'"cells":[[1,10.0],[1,12.0],[1,14.0],[1,16.0],'
    b'[1,10.0],[1,12.0],[1,14.0],[1,16.0],'
    b'[1,10.0],[1,12.0],[1,14.0],[1,16.0],'
    b'[1,10.0],[1,12.0],[1,14.0],[1,16.0]],'
    b'"filled":16,"coverage":1.0},'
    b'{"resolution":2.0,"nx":2,"ny":2,'
    b'"cells":[[4,11.0],[4,15.0],[4,11.0],[4,15.0]],'
    b'"filled":4,"coverage":1.0}'
    b'],"summary":{"layer_count":2,"total_cells":20,"filled_cells":20,'
    b'"mean_coverage":1.0,"quality":"pass"}}'
)


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_dual_resolution_batch_exact_bytes():
    data = grid.batch(POINTS, BOUNDS, RESOLUTIONS)
    assert data == EXPECTED


def test_dual_resolution_batch_shapes_and_order():
    document = decode(grid.batch(POINTS, BOUNDS, RESOLUTIONS))
    assert list(document) == ["results", "summary"]
    assert [layer["resolution"] for layer in document["results"]] == [1.0, 2.0]
    assert [(layer["nx"], layer["ny"]) for layer in document["results"]] == [
        (4, 4),
        (2, 2),
    ]
    assert document["summary"] == {
        "layer_count": 2,
        "total_cells": 20,
        "filled_cells": 20,
        "mean_coverage": 1.0,
        "quality": "pass",
    }


def test_dual_resolution_batch_inputs_not_modified():
    points = [list(point) for point in POINTS]
    snapshot = [list(point) for point in points]
    grid.batch(points, list(BOUNDS), list(RESOLUTIONS))
    assert points == snapshot


def test_dual_resolution_grid_batch_cli_success(tmp_path):
    request = {
        "points": POINTS,
        "bounds": BOUNDS,
        "resolutions": RESOLUTIONS,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "ocean_sonar", "grid-batch", str(request_path)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == EXPECTED + b"\n"
