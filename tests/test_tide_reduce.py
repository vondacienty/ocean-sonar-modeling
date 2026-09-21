"""Tests for tide.reduce per-observation validation order."""

import math

import pytest

from ocean_sonar import tide


def test_reduce_basic_interpolation():
    assert tide.reduce([0.5], [10.0], [0, 1], [1.0, 3.0]) == (8.0,)


def test_time_type_error_precedes_depth_type_error():
    with pytest.raises(TypeError, match=r"observation\[0\]: times elements"):
        tide.reduce(["bad"], ["bad"], [0, 1], [0.0, 0.0])


def test_time_finite_error_precedes_depth_type_error():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        tide.reduce([math.inf], ["bad"], [0, 1], [0.0, 0.0])


def test_depth_type_error_precedes_depth_finite_error():
    with pytest.raises(TypeError, match=r"observation\[0\]: depths elements"):
        tide.reduce([0.5], [True], [0, 1], [0.0, 0.0])


def test_depth_finite_error_precedes_depth_negative_error():
    # nan is neither finite nor >= 0; the finite error must win.
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be finite"):
        tide.reduce([0.5], [math.nan], [0, 1], [0.0, 0.0])


def test_depth_negative_error_precedes_time_range_error():
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be >= 0"):
        tide.reduce([5.0], [-1.0], [0, 1], [0.0, 0.0])


def test_time_range_error_after_all_value_checks():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be within"):
        tide.reduce([5.0], [1.0], [0, 1], [0.0, 0.0])


def test_first_observation_error_wins():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        tide.reduce([math.inf, 0.5], [1.0, "bad"], [0, 1], [0.0, 0.0])
