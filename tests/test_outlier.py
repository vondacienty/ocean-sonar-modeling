"""Tests for outlier.detect MAD gross-error detection."""

import math

import pytest

from ocean_sonar import outlier
from ocean_sonar.outlier import detect


def test_no_outlier_symmetric():
    # median 3.0, deviations [1, 1, 1], MAD 1, scores all 0.67448975.
    result = detect([2.0, 3.0, 4.0])
    assert result == (
        (False, 0.67449, 2.0),
        (False, 0.0, 3.0),
        (False, 0.67449, 4.0),
    )
    assert all(type(item[0]) is bool for item in result)
    assert all(type(item[1]) is float and type(item[2]) is float for item in result)


def test_obvious_outlier_flagged():
    # sorted [1, 2, 3, 100]: median 2.5, dev sorted [0.5, 0.5, 1.5, 97.5],
    # MAD = 1.0. Score of 100: 0.67448975 * 97.5 / 1.0 = 65.762750625.
    result = detect([1, 2, 3, 100])
    flags = [item[0] for item in result]
    assert flags == [False, False, False, True]
    assert result[3] == (True, 65.762751, 100.0)


def test_result_order_matches_input():
    result = detect([100, 1, 3, 2])
    assert [item[2] for item in result] == [100.0, 1.0, 3.0, 2.0]
    assert [item[0] for item in result] == [True, False, False, False]


def test_tuple_input_and_tuple_output():
    result = detect((2.0, 3.0, 4.0))
    assert isinstance(result, tuple)
    assert all(isinstance(item, tuple) for item in result)


def test_even_count_median_is_middle_mean():
    # [10, 20, 30, 40] -> median 25; dev sorted [5, 5, 15, 15] -> MAD 10.
    # score of 10: 0.67448975 * 15 / 10 = 1.011734625 -> 1.011735.
    result = detect([10, 20, 30, 40])
    assert result[0] == (False, 1.011735, 10.0)
    assert result[1] == (False, 0.337245, 20.0)


def test_mad_zero_only_non_median_values_flagged():
    # median 5.0, every deviation is 0 except the single spike.
    result = detect([5, 5, 5, 5, 9])
    assert [item[0] for item in result] == [False, False, False, False, True]
    assert result[4][1] == round(3.5 + 1, 6)
    assert result[0][1] == 0.0


def test_mad_zero_multiple_non_median_values():
    result = detect([7.0, 2.0, 2.0, 2.0])
    assert [item[0] for item in result] == [True, False, False, False]
    assert result[0][1] == 4.5
    assert result[1][1] == 0.0


def test_mad_zero_all_equal_flags_nothing():
    result = detect([3, 3, 3])
    assert [item[0] for item in result] == [False, False, False]
    assert all(item[1] == 0.0 for item in result)


def test_mad_zero_custom_threshold_fallback_score():
    result = detect([1.0, 1.0, 2.0], threshold=2.0)
    assert result[2] == (True, 3.0, 2.0)


def test_boundary_equal_score_not_flagged():
    # [0, 1, 1, 2, 2, 2, x]: median 2, deviations sorted
    # [0, 0, 0, 1, 1, 2, x-2], so MAD = 1. Place x at exactly
    # threshold / 0.67448975 from the median so its raw score is 3.5.
    x = 2 + 3.5 / 0.67448975
    result = detect([0, 1, 1, 2, 2, 2, x])
    assert result[-1][0] is False
    assert result[-1][1] == 3.5


def test_just_above_boundary_flagged():
    x = 2 + (3.5 + 1e-9) / 0.67448975
    result = detect([0, 1, 1, 2, 2, 2, x])
    assert result[-1][0] is True


def test_custom_threshold_changes_flags():
    # [1, 2, 3, 100]: median 2.5, MAD 1.0. Scores: 1 -> 1.011735,
    # 2/3 -> 0.337245, 100 -> 65.762751. A 0.5 threshold additionally
    # flags 1, but not 2 or 3.
    result = detect([1, 2, 3, 100], threshold=0.5)
    assert [item[0] for item in result] == [True, False, False, True]


def test_zero_depths_allowed():
    result = detect([0, 0, 1])
    assert result[0][2] == 0.0
    assert math.copysign(1.0, result[0][2]) == 1.0


def test_int_depths_become_float_outputs():
    result = detect([2, 3, 4])
    assert result[0][2] == 2.0
    assert type(result[0][2]) is float


def test_rounding_to_six_decimals():
    # median of [0.123456789, 1.0, 2.0] is 1.0; depth itself is rounded.
    result = detect([0.123456789, 1.0, 2.0])
    assert result[0][2] == 0.123457


def test_input_not_modified():
    data = [100, 1, 3, 2]
    snapshot = list(data)
    detect(data)
    assert data == snapshot


# --- validation ---------------------------------------------------------


def test_container_type_error():
    with pytest.raises(TypeError, match=r"depths must be a list or tuple"):
        detect({1, 2, 3})


def test_container_type_error_string():
    with pytest.raises(TypeError, match=r"depths must be a list or tuple"):
        detect("abc")


def test_too_few_elements():
    with pytest.raises(ValueError, match=r"at least 3"):
        detect([1, 2])


def test_empty_depths_value_error():
    with pytest.raises(ValueError, match=r"at least 3"):
        detect([])


def test_element_type_error():
    with pytest.raises(TypeError, match=r"depths\[1\]"):
        detect([1, "2", 3])


def test_bool_element_is_type_error():
    with pytest.raises(TypeError, match=r"depths\[0\]"):
        detect([True, 2, 3])


def test_element_non_finite():
    with pytest.raises(ValueError, match=r"depths\[2\] must be finite"):
        detect([1, 2, math.inf])


def test_element_nan_non_finite():
    with pytest.raises(ValueError, match=r"depths\[0\] must be finite"):
        detect([math.nan, 2, 3])


def test_negative_depth():
    with pytest.raises(ValueError, match=r"depths\[1\] must be >= 0"):
        detect([1, -0.5, 3])


def test_negative_zero_depth_allowed():
    result = detect([-0.0, 1.0, 2.0])
    assert result[0][2] == 0.0


def test_threshold_type_error():
    with pytest.raises(TypeError, match=r"threshold must be a non-bool int or float"):
        detect([1, 2, 3], threshold="3.5")


def test_threshold_bool_type_error():
    with pytest.raises(TypeError, match=r"threshold"):
        detect([1, 2, 3], threshold=True)


def test_threshold_non_finite():
    with pytest.raises(ValueError, match=r"threshold must be finite"):
        detect([1, 2, 3], threshold=math.inf)


def test_threshold_nan():
    with pytest.raises(ValueError, match=r"threshold must be finite"):
        detect([1, 2, 3], threshold=math.nan)


def test_threshold_zero():
    with pytest.raises(ValueError, match=r"threshold must be > 0"):
        detect([1, 2, 3], threshold=0)


def test_threshold_negative():
    with pytest.raises(ValueError, match=r"threshold must be > 0"):
        detect([1, 2, 3], threshold=-1.0)


def test_validation_order_container_before_length():
    # A set with one item fails the container check, not the length.
    with pytest.raises(TypeError, match=r"depths must be a list or tuple"):
        detect({1})


def test_validation_order_length_before_elements():
    with pytest.raises(ValueError, match=r"at least 3"):
        detect(["bad", "bad"])


def test_validation_order_element_before_threshold():
    # Even with a bad threshold, the element error wins.
    with pytest.raises(TypeError, match=r"depths\[0\]"):
        detect(["bad", 2, 3], threshold="bad")


def test_validation_order_element_finite_before_threshold():
    with pytest.raises(ValueError, match=r"depths\[0\] must be finite"):
        detect([math.inf, 2, 3], threshold=0)


def test_validation_order_negative_depth_before_threshold():
    with pytest.raises(ValueError, match=r"depths\[0\] must be >= 0"):
        detect([-1.0, 2, 3], threshold=0)


def test_first_bad_element_wins():
    with pytest.raises(TypeError, match=r"depths\[1\]"):
        detect([1, "x", -2.0])


def test_exported():
    assert outlier.__all__ == ["detect", "batch"]
    assert callable(outlier.detect)
    assert callable(outlier.batch)
