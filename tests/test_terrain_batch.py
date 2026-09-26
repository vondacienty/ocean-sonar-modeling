"""Tests for terrain.batch threshold checks, summary shaping and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import terrain

FLAT_CELLS = [[1, 5.0]] * 9
GRADIENT_CELLS = [[1, float(x)] for _y in range(3) for x in range(3)]

FLAT_EXPECTED = (
    b'{"results":[[null,0.0,false],[null,0.0,false],[null,0.0,false],'
    b'[null,0.0,false],[0.0,0.0,true],[null,0.0,false],[null,0.0,false],'
    b'[null,0.0,false],[null,0.0,false]],'
    b'"summary":{"count":9,"valid":1,"pass_count":1,"quality":"pass"}}'
)

GRADIENT_EXPECTED = (
    b'{"results":[[null,1.0,false],[null,2.0,false],[null,1.0,false],'
    b'[null,1.0,false],[45.0,2.0,true],[null,1.0,false],[null,1.0,false],'
    b'[null,2.0,false],[null,1.0,false]],'
    b'"summary":{"count":9,"valid":1,"pass_count":1,"quality":"pass"}}'
)


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_flat_grid_exact_bytes():
    assert terrain.batch(1.0, 3, 3, FLAT_CELLS) == FLAT_EXPECTED


def test_batch_gradient_grid_exact_bytes_with_custom_limits():
    data = terrain.batch(
        1.0, 3, 3, GRADIENT_CELLS, slope_limit=50.0, roughness_limit=3.0
    )
    assert data == GRADIENT_EXPECTED


def test_batch_key_order():
    document = decode(terrain.batch(1.0, 3, 3, FLAT_CELLS))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "count",
        "valid",
        "pass_count",
        "quality",
    ]


def test_batch_default_limits_fail_on_steep_slope():
    # The centre slope is 45.0 and its roughness 2.0, both above the
    # default limits of 5.0 and 1.0.
    document = decode(terrain.batch(1.0, 3, 3, GRADIENT_CELLS))
    assert document["results"][4] == [45.0, 2.0, False]
    assert document["summary"] == {
        "count": 9,
        "valid": 1,
        "pass_count": 0,
        "quality": "fail",
    }


def test_batch_within_false_when_slope_is_none():
    # Boundary cells lack all four neighbours: slope is null, so within
    # is false even though roughness is within its limit.
    document = decode(terrain.batch(1.0, 3, 3, FLAT_CELLS))
    assert document["results"][0] == [None, 0.0, False]
    assert document["summary"]["valid"] == 1
    assert document["summary"]["pass_count"] == 1


def test_batch_summary_counts_are_json_ints():
    data = terrain.batch(1.0, 3, 3, FLAT_CELLS)
    summary = json.loads(data)["summary"]
    assert type(summary["count"]) is int
    assert type(summary["valid"]) is int
    assert type(summary["pass_count"]) is int


def test_batch_all_empty_cells_fail():
    document = decode(terrain.batch(1.0, 2, 2, [[0, None]] * 4))
    assert document["results"] == [[None, None, False]] * 4
    assert document["summary"] == {
        "count": 4,
        "valid": 0,
        "pass_count": 0,
        "quality": "fail",
    }


def test_batch_int_limits_accepted():
    document = decode(
        terrain.batch(1.0, 3, 3, GRADIENT_CELLS, slope_limit=45, roughness_limit=2)
    )
    assert document["results"][4] == [45.0, 2.0, True]
    assert document["summary"]["quality"] == "pass"


def test_batch_limit_equal_to_value_passes():
    document = decode(
        terrain.batch(
            1.0, 3, 3, GRADIENT_CELLS, slope_limit=45.0, roughness_limit=2.0
        )
    )
    assert document["summary"]["pass_count"] == 1
    assert document["summary"]["quality"] == "pass"


def test_batch_analyze_called_exactly_once(monkeypatch):
    calls = []
    real_analyze = terrain.analyze

    def spy(r, nx, ny, cells):
        calls.append((r, nx, ny, cells))
        return real_analyze(r, nx, ny, cells)

    monkeypatch.setattr(terrain, "analyze", spy)
    terrain.batch(1.0, 3, 3, GRADIENT_CELLS, slope_limit=50.0)
    assert calls == [(1.0, 3, 3, GRADIENT_CELLS)]


def test_batch_inputs_not_modified():
    cells = [[1, float(x)] for _y in range(3) for x in range(3)]
    snapshot = [list(cell) for cell in cells]
    terrain.batch(1.0, 3, 3, cells)
    assert cells == snapshot


@pytest.mark.parametrize("bad", [True, "5.0", None, [5.0]])
def test_batch_slope_limit_type_error(bad):
    with pytest.raises(TypeError, match="slope_limit must be a non-bool int or float"):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, slope_limit=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_batch_slope_limit_not_finite(bad):
    with pytest.raises(ValueError, match="slope_limit must be finite"):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, slope_limit=bad)


@pytest.mark.parametrize("bad", [0, 0.0, -1.5])
def test_batch_slope_limit_not_positive(bad):
    with pytest.raises(ValueError, match="slope_limit must be > 0"):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, slope_limit=bad)


@pytest.mark.parametrize("bad", [True, "1.0", None])
def test_batch_roughness_limit_type_error(bad):
    with pytest.raises(
        TypeError, match="roughness_limit must be a non-bool int or float"
    ):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, roughness_limit=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_batch_roughness_limit_not_finite(bad):
    with pytest.raises(ValueError, match="roughness_limit must be finite"):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, roughness_limit=bad)


@pytest.mark.parametrize("bad", [0, 0.0, -0.5])
def test_batch_roughness_limit_not_positive(bad):
    with pytest.raises(ValueError, match="roughness_limit must be > 0"):
        terrain.batch(1.0, 3, 3, FLAT_CELLS, roughness_limit=bad)


def test_batch_slope_limit_validated_before_roughness_limit():
    with pytest.raises(TypeError, match="slope_limit"):
        terrain.batch(
            1.0, 3, 3, FLAT_CELLS, slope_limit=True, roughness_limit=False
        )


def test_batch_grid_validated_before_limits():
    # The grid error wins over a bad limit: analyze runs first.
    with pytest.raises(ValueError, match="cells\\[0\\]: count must be >= 0"):
        terrain.batch(1.0, 1, 1, [[-1, None]], slope_limit=True)


def test_batch_analyze_errors_propagate_with_cell_prefix():
    with pytest.raises(TypeError, match="cells\\[1\\]: count must be a non-bool int"):
        terrain.batch(1.0, 2, 1, [[1, 5.0], [True, 5.0]])


def test_batch_analyze_type_errors_propagate():
    with pytest.raises(TypeError, match="r must be a non-bool int or float"):
        terrain.batch("1.0", 3, 3, FLAT_CELLS)
    with pytest.raises(ValueError, match="nx must be > 0"):
        terrain.batch(1.0, 0, 3, FLAT_CELLS)
