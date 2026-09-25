"""Tests for terrain.cross_scale."""

import math

import pytest

from ocean_sonar import terrain


def _fine(means, nx=4, ny=4):
    cells = [(1, m) if m is not None else (0, None) for m in means]
    return (1.0, nx, ny, cells)


def _coarse(means, nx=2, ny=2):
    cells = [(4, m) if m is not None else (0, None) for m in means]
    return (2.0, nx, ny, cells)


def test_cross_scale_all_matched_pass():
    result = terrain.cross_scale(_fine([1.0] * 16), _coarse([1.0] * 4))
    assert result == {
        "matched": 4,
        "missing": 0,
        "bias": 0.0,
        "rmse": 0.0,
        "max_abs": 0.0,
        "within_tolerance": 4,
        "quality": "pass",
    }


def test_cross_scale_residual_statistics():
    # coarse cell (0, 0) sees fine means 1, 2, 3, 4 -> block mean 2.5,
    # residual 2.0 - 2.5 = -0.5; the other residuals are 0.
    fine_means = [
        1.0, 2.0, 1.0, 1.0,
        3.0, 4.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0,
    ]
    result = terrain.cross_scale(
        _fine(fine_means), _coarse([2.0, 1.0, 1.0, 1.0])
    )
    assert result["matched"] == 4
    assert result["missing"] == 0
    assert result["bias"] == -0.125
    assert result["rmse"] == 0.25
    assert result["max_abs"] == 0.5
    assert result["within_tolerance"] == 4
    assert result["quality"] == "pass"


def test_cross_scale_missing_and_empty_coarse_cells():
    # coarse cell (0, 0): fine block empty -> missing.
    # coarse cell (1, 1): empty -> not counted.
    fine_means = [
        None, None, 1.0, 1.0,
        None, None, 1.0, 1.0,
        1.0, 1.0, None, None,
        1.0, 1.0, None, None,
    ]
    result = terrain.cross_scale(
        _fine(fine_means), _coarse([2.0, 1.0, 1.0, None])
    )
    assert result["matched"] == 2
    assert result["missing"] == 1
    assert result["quality"] == "fail"


def test_cross_scale_no_matched_cells_zeroes_metrics():
    fine_means = [None] * 16
    result = terrain.cross_scale(_fine(fine_means), _coarse([1.0] * 4))
    assert result == {
        "matched": 0,
        "missing": 4,
        "bias": 0.0,
        "rmse": 0.0,
        "max_abs": 0.0,
        "within_tolerance": 0,
        "quality": "fail",
    }


def test_cross_scale_tolerance_boundary_is_inclusive():
    result = terrain.cross_scale(
        _fine([1.0] * 16), _coarse([1.5] * 4), tolerance=0.5
    )
    assert result["within_tolerance"] == 4
    assert result["quality"] == "pass"
    result = terrain.cross_scale(
        _fine([1.0] * 16), _coarse([1.5] * 4), tolerance=0.4
    )
    assert result["within_tolerance"] == 0
    assert result["quality"] == "fail"


def test_cross_scale_key_order():
    result = terrain.cross_scale(_fine([1.0] * 16), _coarse([1.0] * 4))
    assert list(result) == [
        "matched",
        "missing",
        "bias",
        "rmse",
        "max_abs",
        "within_tolerance",
        "quality",
    ]


def test_cross_scale_negative_zero_normalized():
    result = terrain.cross_scale(_fine([1.0] * 16), _coarse([1.0] * 4))
    for key in ("bias", "rmse", "max_abs"):
        assert result[key] == 0.0
        assert math.copysign(1.0, result[key]) == 1.0


def test_cross_scale_inputs_not_modified():
    fine = [1.0, 4, 4, [[1, 1.0]] * 16]
    coarse = [2.0, 2, 2, [[4, 1.0]] * 4]
    snapshot = ([list(c) for c in fine[3]], [list(c) for c in coarse[3]])
    terrain.cross_scale(fine, coarse)
    assert [list(c) for c in fine[3]] == snapshot[0]
    assert [list(c) for c in coarse[3]] == snapshot[1]


def test_fine_validated_before_coarse():
    with pytest.raises(TypeError, match=r"^fine: must be a list or tuple"):
        terrain.cross_scale("bad", "bad")


def test_fine_cell_prefix():
    fine = _fine([1.0] * 16)
    fine[3][0] = (True, 1.0)
    with pytest.raises(
        TypeError, match=r"^fine\.cells\[0\]: count must be a non-bool int"
    ):
        terrain.cross_scale(fine, _coarse([1.0] * 4))


def test_coarse_cell_prefix():
    coarse = _coarse([1.0] * 4)
    coarse[3][2] = (0, 1.0)
    with pytest.raises(
        ValueError,
        match=r"^coarse\.cells\[2\]: mean must be None when count is 0",
    ):
        terrain.cross_scale(_fine([1.0] * 16), coarse)


def test_tolerance_validated_after_grids():
    with pytest.raises(
        TypeError, match=r"^tolerance must be a non-bool int or float"
    ):
        terrain.cross_scale(_fine([1.0] * 16), _coarse([1.0] * 4), "bad")
    with pytest.raises(ValueError, match=r"^tolerance must be finite"):
        terrain.cross_scale(
            _fine([1.0] * 16), _coarse([1.0] * 4), math.inf
        )
    with pytest.raises(ValueError, match=r"^tolerance must be > 0"):
        terrain.cross_scale(_fine([1.0] * 16), _coarse([1.0] * 4), 0.0)


def test_resolution_relation_errors():
    with pytest.raises(ValueError, match=r"fine\.r must be < coarse\.r"):
        terrain.cross_scale(_fine([1.0] * 16), (1.0, 2, 2, [(1, 1.0)] * 4))
    with pytest.raises(
        ValueError, match=r"positive integer multiple of fine\.r"
    ):
        terrain.cross_scale(_fine([1.0] * 16), (1.5, 2, 2, [(1, 1.0)] * 4))


def test_dimension_relation_error():
    with pytest.raises(ValueError, match=r"scale factor times"):
        terrain.cross_scale(
            _fine([1.0] * 16), (4.0, 2, 2, [(1, 1.0)] * 4)
        )
