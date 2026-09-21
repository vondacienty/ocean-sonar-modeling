"""Tests for outlier.detect MAD-based gross-error detection."""

import math

import pytest

from ocean_sonar import outlier


def test_detect_basic_flags_far_depth():
    result = outlier.detect([10.0, 10.1, 10.2, 10.1, 50.0])
    assert isinstance(result, tuple)
    assert [r[0] for r in result] == [False, False, False, False, True]
    # m = 10.1, MAD = 0.1; score of 50.0 = 0.67448975 * 39.9 / 0.1
    assert result[4][1] == round(0.67448975 * 39.9 / 0.1, 6)
    assert result[4][2] == 50.0


def test_detect_result_item_types():
    for item in outlier.detect([1, 2.5, 3]):
        assert isinstance(item, tuple) and len(item) == 3
        assert isinstance(item[0], bool)
        assert isinstance(item[1], float)
        assert isinstance(item[2], float)


def test_detect_even_count_median():
    # sorted [1, 2, 3, 100] -> m = 2.5, deviations [1.5, 0.5, 0.5, 97.5]
    # MAD = 1.0; score of 100 = 0.67448975 * 97.5 > 3.5
    result = outlier.detect([100.0, 1.0, 3.0, 2.0])
    assert [r[0] for r in result] == [True, False, False, False]
    assert result[0][1] == round(0.67448975 * 97.5, 6)


def test_detect_preserves_input_order_and_input():
    depths = [30.0, 1.0, 2.0, 1.5, 1.2]
    snapshot = list(depths)
    result = outlier.detect(depths)
    assert depths == snapshot
    assert [r[2] for r in result] == [30.0, 1.0, 2.0, 1.5, 1.2]
    assert result[0][0] is True


def test_detect_accepts_tuple_and_ints():
    result = outlier.detect((1, 2, 3))
    assert [r[0] for r in result] == [False, False, False]
    assert [r[2] for r in result] == [1.0, 2.0, 3.0]


def test_detect_mad_zero_flags_only_unequal():
    result = outlier.detect([5.0, 5.0, 5.0, 9.0])
    assert [r[0] for r in result] == [False, False, False, True]
    assert [r[1] for r in result] == [0.0, 0.0, 0.0, 4.5]


def test_detect_mad_zero_score_uses_threshold():
    result = outlier.detect([5.0, 5.0, 5.0, 9.0], threshold=2)
    assert result[3][1] == 3.0


def test_detect_mad_zero_all_equal_flags_nothing():
    result = outlier.detect([7.0, 7.0, 7.0])
    assert [r[0] for r in result] == [False, False, False]
    assert [r[1] for r in result] == [0.0, 0.0, 0.0]


def test_detect_equality_with_threshold_not_flagged():
    # m = 1.0, MAD = 1.0 -> score of 0.0 and 2.0 is exactly 0.67448975
    result = outlier.detect([0.0, 1.0, 2.0], threshold=0.67448975)
    assert [r[0] for r in result] == [False, False, False]
    assert result[0][1] == 0.67449


def test_detect_score_rounded_to_six_decimals():
    result = outlier.detect([0.0, 1.0, 2.0])
    assert result[0][1] == 0.67449  # round(0.67448975, 6)


def test_detect_negative_zero_depth_normalized():
    result = outlier.detect([-0.0, 1.0, 2.0])
    assert result[0][2] == 0.0
    assert math.copysign(1.0, result[0][2]) == 1.0


def test_detect_depth_rounded_to_six_decimals():
    result = outlier.detect([1.00000004, 2.0, 3.0])
    assert result[0][2] == 1.0


def test_detect_custom_threshold_changes_flagging():
    depths = [10.0, 10.1, 10.2, 10.1, 12.0]
    # score of 12.0 = 0.67448975 * 1.9 / 0.1 = 12.815...
    assert outlier.detect(depths, threshold=3.5)[4][0] is True
    assert outlier.detect(depths, threshold=13.0)[4][0] is False


def test_container_type_error():
    with pytest.raises(TypeError, match="depths must be a list or tuple"):
        outlier.detect("1, 2, 3")


def test_length_error():
    with pytest.raises(ValueError, match="depths must have at least 3 elements"):
        outlier.detect([1.0, 2.0])


def test_element_type_error():
    with pytest.raises(TypeError, match="depths elements must be non-bool"):
        outlier.detect([1.0, True, 3.0])


def test_element_finite_error():
    with pytest.raises(ValueError, match="depths elements must be finite"):
        outlier.detect([1.0, math.inf, 3.0])


def test_element_negative_error():
    with pytest.raises(ValueError, match="depths elements must be >= 0"):
        outlier.detect([1.0, -0.5, 3.0])


def test_threshold_type_error():
    with pytest.raises(TypeError, match="threshold must be a non-bool"):
        outlier.detect([1.0, 2.0, 3.0], threshold="3.5")


def test_threshold_bool_type_error():
    with pytest.raises(TypeError, match="threshold must be a non-bool"):
        outlier.detect([1.0, 2.0, 3.0], threshold=True)


def test_threshold_finite_error():
    with pytest.raises(ValueError, match="threshold must be finite"):
        outlier.detect([1.0, 2.0, 3.0], threshold=math.nan)


def test_threshold_positive_error():
    with pytest.raises(ValueError, match="threshold must be positive"):
        outlier.detect([1.0, 2.0, 3.0], threshold=0.0)


# Overlapping errors: first error in the validation order wins.


def test_container_error_precedes_threshold_error():
    with pytest.raises(TypeError, match="depths must be a list or tuple"):
        outlier.detect("bad", threshold="bad")


def test_length_error_precedes_element_and_threshold_errors():
    with pytest.raises(ValueError, match="depths must have at least 3 elements"):
        outlier.detect([True, "bad"], threshold="bad")


def test_element_type_error_precedes_finite_and_negative():
    # nan is neither finite nor >= 0; type error on a bool still wins
    # when it comes first, and finite beats negative within an element.
    with pytest.raises(ValueError, match="depths elements must be finite"):
        outlier.detect([math.nan, -1.0, 3.0])


def test_first_element_error_wins():
    with pytest.raises(ValueError, match="depths elements must be >= 0"):
        outlier.detect([-1.0, "bad", 3.0])


def test_element_error_precedes_threshold_error():
    with pytest.raises(TypeError, match="depths elements must be non-bool"):
        outlier.detect([1.0, None, 3.0], threshold="bad")
