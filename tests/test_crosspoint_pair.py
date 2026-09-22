"""Tests for crosspoint.pair validation and greedy matching."""

import pytest

from ocean_sonar import crosspoint
from ocean_sonar.crosspoint import pair


def test_basic_pairing_in_first_order():
    result = pair(
        [(0, 0, 1), (10, 10, 2)],
        [(0.5, 0.0, 5), (10.1, 10.0, 7)],
        1.0,
    )
    assert result == ((0.0, 0.0, 1.0, 5.0), (10.0, 10.0, 2.0, 7.0))
    assert all(type(v) is float for item in result for v in item)


def test_second_points_are_not_reused():
    result = pair([(0, 0, 1), (0.1, 0, 2)], [(0, 0, 9)])
    assert result == ((0.0, 0.0, 1.0, 9.0),)


def test_equal_distance_keeps_earliest_second():
    result = pair([(0, 0, 1)], [(1, 0, 3), (-1, 0, 4)], 1.0)
    assert result == ((0.0, 0.0, 1.0, 3.0),)


def test_unmatched_points_are_skipped():
    result = pair([(0, 0, 1), (100, 100, 2)], [(0, 0, 9)])
    assert result == ((0.0, 0.0, 1.0, 9.0),)


def test_no_pairs_raises_value_error():
    with pytest.raises(ValueError, match="at least one point pair is required"):
        pair([(0, 0, 1)], [(100, 100, 2)], 1.0)


def test_tolerance_boundary_is_inclusive_and_unrounded():
    assert pair([(0, 0, 1)], [(1, 0, 2)], 1.0) == ((0.0, 0.0, 1.0, 2.0),)
    with pytest.raises(ValueError):
        pair([(0, 0, 1)], [(1.0000001, 0, 2)], 1.0)


def test_outputs_rounded_and_negative_zero_normalized():
    result = pair([(-0.0, -0.0, -0)], [(-0.0, -0.0, -0.0)])
    assert result == ((0.0, 0.0, 0.0, 0.0),)


def test_inputs_are_not_modified():
    first = [(0, 0, 1)]
    second = [[0.0, 0.0, 2.0]]
    pair(first, second)
    assert first == [(0, 0, 1)]
    assert second == [[0.0, 0.0, 2.0]]


def test_validation_order_containers_and_emptiness():
    with pytest.raises(TypeError, match="first must be a list or tuple"):
        pair("a", [])
    with pytest.raises(ValueError, match="first must be non-empty"):
        pair([], [])
    with pytest.raises(TypeError, match="second must be a list or tuple"):
        pair([[0, 0, 0]], "x")
    with pytest.raises(ValueError, match="second must be non-empty"):
        pair([[0, 0, 0]], [])


def test_validation_order_points():
    with pytest.raises(TypeError, match=r"first\[0\]: must be a list or tuple"):
        pair([1], [[0, 0, 0]])
    with pytest.raises(ValueError, match=r"first\[0\]: must have 3 elements"):
        pair([[0, 0]], [[0, 0, 0]])
    with pytest.raises(TypeError, match=r"first\[0\]: x must be a non-bool int or float"):
        pair([[True, 0, 0]], [[0, 0, 0]])
    with pytest.raises(ValueError, match=r"first\[0\]: y must be finite"):
        pair([[0, float("nan"), 0]], [[0, 0, 0]])
    with pytest.raises(ValueError, match=r"first\[0\]: d must be >= 0"):
        pair([[0, 0, -1]], [[0, 0, 0]])
    with pytest.raises(TypeError, match=r"second\[0\]: must be a list or tuple"):
        pair([[0, 0, 0]], [1])
    with pytest.raises(ValueError, match=r"second\[0\]: must have 3 elements"):
        pair([[0, 0, 0]], [[0, 0, 0, 0]])
    with pytest.raises(TypeError, match=r"second\[0\]: y must be a non-bool int or float"):
        pair([[0, 0, 0]], [[0, "z", 0]])
    # all first points are checked before any second point
    with pytest.raises(TypeError, match=r"first\[1\]"):
        pair([[0, 0, 0], 1], [2])


def test_tolerance_is_validated_last():
    with pytest.raises(TypeError, match="tolerance must be a non-bool int or float"):
        pair([[0, 0, 0]], [[0, 0, 0]], True)
    with pytest.raises(ValueError, match="tolerance must be finite"):
        pair([[0, 0, 0]], [[0, 0, 0]], float("inf"))
    with pytest.raises(ValueError, match="tolerance must be > 0"):
        pair([[0, 0, 0]], [[0, 0, 0]], 0)
    with pytest.raises(TypeError, match=r"second\[0\]"):
        pair([[0, 0, 0]], [1], True)


def test_export():
    assert crosspoint.__all__ == ["evaluate", "pair"]
    assert crosspoint.pair is pair
