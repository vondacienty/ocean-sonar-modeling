"""Overlapping-error tests for ``ocean_sonar.tide.reduce``.

Each case carries more than one defect on the same observation and
asserts that the first error in the per-i validation order wins:
time type, time finiteness, depth type, depth finiteness, depth
non-negativity, then time range.
"""

import math

import pytest

from ocean_sonar import tide

TIDE_TIMES = [0.0, 10.0]
LEVELS = [1.0, 2.0]


def reduce_one(time, depth):
    return tide.reduce([time], [depth], TIDE_TIMES, LEVELS)


def test_time_type_wins_over_time_finiteness_and_depth_type():
    # bool time is a type error even though the depth is also mistyped.
    with pytest.raises(TypeError, match=r"observation\[0\]: times elements must be non-bool int or float"):
        reduce_one(True, "deep")


def test_time_finiteness_wins_over_depth_type():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        reduce_one(math.nan, "deep")


def test_time_finiteness_wins_over_depth_type_inf():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        reduce_one(math.inf, None)


def test_depth_type_wins_over_depth_finiteness_and_range():
    # A bool depth is a type error even though it would also fail
    # finiteness/range-style checks, and the time is out of range.
    with pytest.raises(TypeError, match=r"observation\[0\]: depths elements must be non-bool int or float"):
        reduce_one(99.0, False)


def test_depth_type_wins_over_time_range():
    with pytest.raises(TypeError, match=r"observation\[0\]: depths elements must be non-bool int or float"):
        reduce_one(99.0, "deep")


def test_depth_finiteness_wins_over_non_negativity_and_range():
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be finite"):
        reduce_one(99.0, math.nan)


def test_depth_finiteness_wins_over_time_range_inf():
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be finite"):
        reduce_one(99.0, -math.inf)


def test_depth_non_negativity_wins_over_time_range():
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be >= 0"):
        reduce_one(99.0, -1.0)


def test_time_range_reported_when_only_defect():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be within the tide time range"):
        reduce_one(99.0, 1.0)


def test_earlier_observation_wins_over_later_one():
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        tide.reduce([math.nan, 99.0], ["deep", -1.0], TIDE_TIMES, LEVELS)
