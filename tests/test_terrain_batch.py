"""Tests for terrain.batch result shaping, limit validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import terrain


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


FLAT = [(1, 10.0), (1, 10.0), (1, 10.0), (1, 10.0)]
# Flat 3x3: the center has all four neighbours and a zero slope.
FLAT3 = [(1, 10.0)] * 9
# 3x3 grid whose center neighbour to the right is 2 m deeper.
BUMP = [
    (1, 10.0), (1, 10.0), (1, 10.0),
    (1, 10.0), (1, 10.0), (1, 12.0),
    (1, 10.0), (1, 10.0), (1, 10.0),
]


def test_batch_basic_exact_bytes():
    data = terrain.batch(1.0, 3, 3, BUMP)
    assert data == (
        b'{"results":[[null,0.0,false],[null,2.0,false],[null,2.0,false],'
        b'[null,0.0,false],[45.0,2.0,false],[null,2.0,false],'
        b'[null,0.0,false],[null,2.0,false],[null,2.0,false]],'
        b'"summary":{"count":9,"valid":1,"pass_count":0,"quality":"fail"}}'
    )


def test_batch_small_grid_has_no_slopes_so_quality_fails():
    document = decode(terrain.batch(1.0, 2, 2, FLAT))
    # A 2x2 grid has no cell with all four direct neighbours, so every
    # slope is null even though roughness is 0.
    assert document["results"] == [
        [None, 0.0, False],
        [None, 0.0, False],
        [None, 0.0, False],
        [None, 0.0, False],
    ]
    assert document["summary"] == {
        "count": 4,
        "valid": 0,
        "pass_count": 0,
        "quality": "fail",
    }


def test_batch_flat_interior_passes_default_limits():
    document = decode(terrain.batch(1.0, 3, 3, FLAT3))
    # Only the center cell has all four neighbours: slope 0, roughness 0.
    assert document["results"][4] == [0.0, 0.0, True]
    assert all(row[2] is False for i, row in enumerate(document["results"]) if i != 4)
    assert document["summary"] == {
        "count": 9,
        "valid": 1,
        "pass_count": 1,
        "quality": "pass",
    }


def test_batch_within_true_when_both_limits_satisfied():
    document = decode(
        terrain.batch(1.0, 3, 3, BUMP, slope_limit=45.0, roughness_limit=2.0)
    )
    assert document["results"][4] == [45.0, 2.0, True]
    assert document["summary"] == {
        "count": 9,
        "valid": 1,
        "pass_count": 1,
        "quality": "pass",
    }


def test_batch_within_uses_non_strict_comparison():
    # slope == slope_limit and roughness == roughness_limit still passes.
    document = decode(
        terrain.batch(1.0, 3, 3, BUMP, slope_limit=45, roughness_limit=2)
    )
    assert document["results"][4][2] is True
    assert document["summary"]["quality"] == "pass"


def test_batch_slope_limit_borders_within():
    # Just below 45 degrees must fail.
    document = decode(
        terrain.batch(1.0, 3, 3, BUMP, slope_limit=44.999999, roughness_limit=2)
    )
    assert document["results"][4][2] is False
    assert document["summary"] == {
        "count": 9,
        "valid": 1,
        "pass_count": 0,
        "quality": "fail",
    }


def test_batch_results_follow_grid_cell_order():
    document = decode(terrain.batch(1.0, 3, 3, BUMP))
    analysis = terrain.analyze(1.0, 3, 3, BUMP)
    assert len(document["results"]) == len(analysis)
    for row, (slope, roughness) in zip(document["results"], analysis):
        assert row[0] == slope
        assert row[1] == roughness


def test_batch_empty_cells_are_null_null_false():
    cells = [(0, None)] * 4
    document = decode(terrain.batch(1.0, 2, 2, cells))
    assert document["results"] == [[None, None, False]] * 4
    assert document["summary"] == {
        "count": 4,
        "valid": 0,
        "pass_count": 0,
        "quality": "fail",
    }


def test_batch_key_order():
    data = terrain.batch(1.0, 3, 3, BUMP)
    document = decode(data)
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == ["count", "valid", "pass_count", "quality"]
    assert type(json.loads(data)["summary"]["count"]) is int
    assert type(json.loads(data)["summary"]["valid"]) is int
    assert type(json.loads(data)["summary"]["pass_count"]) is int
    for row in document["results"]:
        assert type(row[2]) is bool


def test_batch_default_limits():
    # Default slope_limit=5.0 rejects the 45 degree center; roughness
    # default 1.0 also rejects its spread of 2.
    document = decode(terrain.batch(1.0, 3, 3, BUMP))
    assert document["results"][4] == [45.0, 2.0, False]


def test_batch_calls_analyze_exactly_once(monkeypatch):
    calls = []
    real_analyze = terrain.analyze

    def spy(*args):
        calls.append(args)
        return real_analyze(*args)

    monkeypatch.setattr(terrain, "analyze", spy)
    terrain.batch(1.0, 3, 3, BUMP, slope_limit=2.0, roughness_limit=3.0)
    assert calls == [(1.0, 3, 3, BUMP)]


def test_batch_analyze_exception_propagates_before_limit_validation():
    with pytest.raises(TypeError, match="r must be a non-bool int or float"):
        terrain.batch("bad", 1, 1, [(1, 1.0)], slope_limit=True)
    with pytest.raises(ValueError, match="nx must be > 0"):
        terrain.batch(1.0, 0, 1, [], slope_limit=0.0)


def test_batch_cell_error_prefix_passed_through():
    with pytest.raises(TypeError, match=r"^cells\[0\]: count must be a non-bool int$"):
        terrain.batch(1.0, 1, 1, [(True, 1.0)])
    with pytest.raises(ValueError, match=r"^cells\[1\]: mean must be finite$"):
        terrain.batch(1.0, 2, 1, [(1, 1.0), (1, math.inf)])


@pytest.mark.parametrize("name", ["slope_limit", "roughness_limit"])
@pytest.mark.parametrize("value", [True, False, "5", None, [5.0]])
def test_batch_limit_type_error(name, value):
    kwargs = {name: value}
    with pytest.raises(
        TypeError, match=rf"{name} must be a non-bool int or float"
    ):
        terrain.batch(1.0, 3, 3, BUMP, **kwargs)


@pytest.mark.parametrize("name", ["slope_limit", "roughness_limit"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_batch_limit_non_finite_error(name, value):
    kwargs = {name: value}
    with pytest.raises(ValueError, match=rf"{name} must be finite"):
        terrain.batch(1.0, 3, 3, BUMP, **kwargs)


@pytest.mark.parametrize("name", ["slope_limit", "roughness_limit"])
@pytest.mark.parametrize("value", [0, 0.0, -1, -0.5])
def test_batch_limit_must_be_positive_error(name, value):
    kwargs = {name: value}
    with pytest.raises(ValueError, match=rf"{name} must be > 0"):
        terrain.batch(1.0, 3, 3, BUMP, **kwargs)


def test_batch_limit_validation_order():
    # slope_limit is checked before roughness_limit.
    with pytest.raises(TypeError, match="slope_limit must be a non-bool int or float"):
        terrain.batch(1.0, 3, 3, BUMP, slope_limit="x", roughness_limit="y")
    with pytest.raises(ValueError, match="slope_limit must be > 0"):
        terrain.batch(1.0, 3, 3, BUMP, slope_limit=0.0, roughness_limit=0.0)


def test_batch_inputs_not_modified():
    cells = [list(cell) for cell in BUMP]
    snapshot = [list(cell) for cell in cells]
    terrain.batch(1.0, 3, 3, cells)
    assert cells == snapshot


def test_batch_result_is_bytes_without_bom_or_newline():
    data = terrain.batch(1.0, 3, 3, BUMP)
    assert isinstance(data, bytes)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")
