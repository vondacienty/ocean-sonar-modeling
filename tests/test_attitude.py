"""Tests for attitude.correct."""

import math

import pytest

from ocean_sonar.attitude import correct


def test_zero_attitude_identity():
    assert correct([[1, 2, 3, 0, 0, 0]]) == ((1.0, 2.0, 3.0),)


def test_heave_positive_up_reduces_depth():
    assert correct([[0, 0, 10, 0, 0, 2.5]]) == ((0.0, 0.0, 7.5),)


def test_roll_90_degrees():
    # Beam 1 m to starboard swings straight down under a 90 deg roll.
    assert correct([[0, 1, 0, 90, 0, 0]]) == ((0.0, 0.0, 1.0),)


def test_pitch_90_degrees():
    assert correct([[1, 0, 0, 0, 90, 0]]) == ((0.0, 0.0, -1.0),)


def test_roll_and_pitch_combined():
    # r = p = 45 deg, x = 0, y = 0, d = 1, heave = 0
    s = math.sin(math.radians(45))
    c = math.cos(math.radians(45))
    (X, Y, D), = correct([[0, 0, 1, 45, 45, 0]])
    assert (X, Y, D) == (
        round(c * s, 6),
        round(-s * 1, 6),
        round(c * c, 6),
    )
    assert X == 0.5 and Y == round(-math.sqrt(0.5), 6) and D == 0.5


def test_results_are_float_triples_in_order():
    result = correct([(1, 2, 3, 0, 0, 0), [4, 5, 6, 1, -1, 0.5]])
    assert isinstance(result, tuple)
    assert len(result) == 2
    for triple in result:
        assert isinstance(triple, tuple)
        assert len(triple) == 3
        assert all(type(v) is float for v in triple)
    assert result[0] == (1.0, 2.0, 3.0)


def test_rounding_to_6_decimals():
    (X, Y, D), = correct([[1 / 3, 0, 0, 0, 0, 0]])
    assert X == round(1 / 3, 6)


def test_negative_zero_normalized():
    (X, Y, D), = correct([[0, -0.0, 0, 0, 0, 0]])
    for v in (X, Y, D):
        assert v == 0.0
        assert math.copysign(1.0, v) > 0


def test_input_not_modified():
    obs = [[1, 2, 3, 4, 5, 6]]
    snapshot = [list(o) for o in obs]
    correct(obs)
    assert obs == snapshot


def test_outer_container_type():
    with pytest.raises(TypeError, match="observations must be a list or tuple"):
        correct("not a container")


def test_empty_observations():
    with pytest.raises(ValueError, match="observations must be non-empty"):
        correct([])


def test_item_container_type():
    with pytest.raises(TypeError, match=r"observation\[0\]: must be a list or tuple"):
        correct(["nope"])


def test_item_length():
    with pytest.raises(ValueError, match=r"observation\[1\]: must have 6 elements"):
        correct([[0, 0, 0, 0, 0, 0], [1, 2, 3]])


def test_field_type_error():
    with pytest.raises(TypeError, match=r"observation\[0\]: y must be a non-bool int or float"):
        correct([[0, True, 0, 0, 0, 0]])


def test_field_finite_error():
    with pytest.raises(ValueError, match=r"observation\[0\]: roll must be finite"):
        correct([[0, 0, 0, math.nan, 0, 0]])


def test_negative_depth():
    with pytest.raises(ValueError, match=r"observation\[0\]: d must be >= 0"):
        correct([[0, 0, -0.5, 0, 0, 0]])


def test_field_validation_order():
    # x is checked before y, y before d, and so on.
    with pytest.raises(TypeError, match=r"observation\[0\]: x must be"):
        correct([[None, None, None, None, None, None]])
    with pytest.raises(ValueError, match=r"observation\[0\]: heave must be finite"):
        correct([[0, 0, 0, 0, 0, math.inf]])


def test_first_item_error_wins():
    with pytest.raises(ValueError, match=r"observation\[1\]: pitch must be finite"):
        correct([[0, 0, 0, 0, 0, 0], [0, 0, 0, 0, math.inf, 0], ["bad"]])
