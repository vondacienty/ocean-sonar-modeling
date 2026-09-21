"""Tests for strip.merge median depth-offset strip merging."""

import math

import pytest

from ocean_sonar import strip
from ocean_sonar.strip import merge


def test_first_strip_unchanged_second_aligned():
    # diffs [2, 3] -> median 2.5 subtracted from the second strip.
    result = merge(
        [
            [(0, 0, 10), (1, 0, 20)],
            [(0, 0, 12), (1, 0, 23)],
        ]
    )
    assert result == (
        (0.0, 0.0, 10.0),
        (1.0, 0.0, 20.0),
        (0.0, 0.0, 9.5),
        (1.0, 0.0, 20.5),
    )


def test_output_is_tuple_of_float_triples():
    result = merge([[(0, 0, 1), (1, 0, 2)], [(0, 0, 3), (1, 0, 4)]])
    assert isinstance(result, tuple)
    assert all(isinstance(item, tuple) and len(item) == 3 for item in result)
    assert all(type(v) is float for item in result for v in item)


def test_even_count_median_is_middle_mean():
    # diffs [1, 2, 3, 4] -> median 2.5.
    base = [(0, 0, 10), (10, 0, 10), (20, 0, 10), (30, 0, 10)]
    top = [(0, 0, 11), (10, 0, 12), (20, 0, 13), (30, 0, 14)]
    result = merge([base, top])
    assert [item[2] for item in result[4:]] == [8.5, 9.5, 10.5, 11.5]


def test_odd_count_median_is_middle_value():
    base = [(0, 0, 10), (10, 0, 10), (20, 0, 10)]
    top = [(0, 0, 13), (10, 0, 11), (20, 0, 12)]
    # diffs [3, 1, 2] -> sorted [1, 2, 3] -> median 2.
    result = merge([base, top])
    assert [item[2] for item in result[3:]] == [11.0, 9.0, 10.0]


def test_nearest_accumulated_point_wins():
    # (0.4, 0) is closer to (0, 0) than to (1, 0).
    result = merge(
        [
            [(0, 0, 10), (1, 0, 20)],
            [(0.4, 0, 15), (0.6, 0, 25)],
        ]
    )
    # diffs [15 - 10, 25 - 20] = [5, 5] -> offset 5.
    assert result[2] == (0.4, 0.0, 10.0)
    assert result[3] == (0.6, 0.0, 20.0)


def test_tie_goes_to_earliest_accumulated_point():
    # (1, 0) is equidistant from (0, 0) and (2, 0); the earlier
    # accumulated point (0, 0, 5) wins for both new points (reuse).
    result = merge(
        [
            [(0, 0, 5), (2, 0, 7)],
            [(1, 0, 10), (1, 0, 12)],
        ],
        tolerance=1.0,
    )
    # diffs [10 - 5, 12 - 5] = [5, 7] -> median 6.
    assert result[2] == (1.0, 0.0, 4.0)
    assert result[3] == (1.0, 0.0, 6.0)


def test_accumulated_point_may_be_reused():
    result = merge(
        [
            [(0, 0, 4)],
            [(0, 0, 6), (0, 0, 8)],
        ]
    )
    # Both new points match the single accumulated point:
    # diffs [2, 4] -> median 3.
    assert result == (
        (0.0, 0.0, 4.0),
        (0.0, 0.0, 3.0),
        (0.0, 0.0, 5.0),
    )


def test_distance_equal_to_tolerance_matches():
    result = merge(
        [
            [(0, 0, 1), (0, 2, 1)],
            [(0, 1, 5), (0, 1, 6)],
        ],
        tolerance=1.0,
    )
    # Both new points are at distance exactly 1 from both accumulated
    # points; ties go to (0, 0, 1): diffs [4, 5] -> median 4.5.
    assert result[2] == (0.0, 1.0, 0.5)
    assert result[3] == (0.0, 1.0, 1.5)


def test_distance_just_beyond_tolerance_does_not_match():
    # 1.0000001 > tolerance from (0, 0) and even farther from (10, 0).
    with pytest.raises(ValueError, match=r"strip\[1\]: fewer than 2"):
        merge(
            [
                [(0, 0, 1), (10, 0, 1)],
                [(0, 1.0000001, 5), (0, 1.0000001, 6)],
            ],
            tolerance=1.0,
        )


def test_matching_uses_corrected_accumulated_depths():
    # The second strip is corrected to depth 10; the third strip then
    # matches those corrected (unrounded) depths.
    result = merge(
        [
            [(0, 0, 10), (1, 0, 10)],
            [(0, 0, 10.4), (1, 0, 10.4)],
            [(0, 0, 10.9), (1, 0, 10.9)],
        ]
    )
    assert [item[2] for item in result] == [10.0] * 6


def test_unmatched_points_still_get_offset():
    # The far-away point matches nothing but is shifted by the offset
    # derived from the two matched points.
    result = merge(
        [
            [(0, 0, 10), (1, 0, 10)],
            [(0, 0, 12), (1, 0, 12), (100, 0, 50)],
        ]
    )
    assert result[4] == (100.0, 0.0, 48.0)


def test_corrected_depth_may_be_negative():
    result = merge(
        [
            [(0, 0, 1), (1, 0, 1)],
            [(0, 0, 5), (1, 0, 5)],
        ]
    )
    # diffs [4, 4] -> offset 4 -> corrected depths 5 - 4 = 1.
    assert result[2] == (0.0, 0.0, 1.0)
    # An offset larger than a point's own depth yields a negative
    # corrected depth: diffs [9, 2] -> median 5.5 -> 3 - 5.5 = -2.5.
    result = merge(
        [
            [(0, 0, 1), (1, 0, 1)],
            [(0, 0, 10), (1, 0, 3)],
        ]
    )
    assert result[2] == (0.0, 0.0, 4.5)
    assert result[3] == (1.0, 0.0, -2.5)


def test_result_order_matches_input_order():
    strips = [
        [(2, 0, 1), (0, 0, 2)],
        [(0, 0, 4), (2, 0, 3)],
        [(2, 0, 5), (0, 0, 6)],
    ]
    result = merge(strips)
    assert [(item[0], item[1]) for item in result] == [
        (2.0, 0.0),
        (0.0, 0.0),
        (0.0, 0.0),
        (2.0, 0.0),
        (2.0, 0.0),
        (0.0, 0.0),
    ]


def test_tuple_inputs_accepted():
    result = merge(
        (
            ((0, 0, 1), (1, 0, 2)),
            ((0, 0, 3), (1, 0, 4)),
        )
    )
    assert isinstance(result, tuple)
    assert len(result) == 4


def test_int_values_become_float_outputs():
    result = merge([[(0, 0, 1), (1, 0, 2)], [(0, 0, 3), (1, 0, 4)]])
    assert result[0] == (0.0, 0.0, 1.0)
    assert all(type(v) is float for item in result for v in item)


def test_rounding_to_six_decimals():
    result = merge(
        [
            [(0.123456789, 0, 1.123456789), (1, 0, 2)],
            [(0.123456789, 0, 2.123456789), (1, 0, 3)],
        ]
    )
    assert result[0] == (0.123457, 0.0, 1.123457)
    # offset is exactly 1 -> second strip depths unchanged.
    assert result[2] == (0.123457, 0.0, 1.123457)


def test_negative_zero_normalized():
    result = merge(
        [
            [(-0.0, 0, 1), (1, 0, 1)],
            [(0, 0, 2), (1, 0, 2)],
        ]
    )
    assert result[0][0] == 0.0
    assert math.copysign(1.0, result[0][0]) == 1.0


def test_default_tolerance_is_one():
    # Points at distance exactly 1 match with the default tolerance.
    result = merge(
        [
            [(0, 0, 1), (0, 2, 1)],
            [(0, 1, 3), (0, 1, 4)],
        ]
    )
    assert result[2][2] == 0.5


def test_input_not_modified():
    strips = [
        [[0, 0, 1], [1, 0, 2]],
        [[0, 0, 3], [1, 0, 4]],
    ]
    snapshot = [[list(p) for p in s] for s in strips]
    merge(strips)
    assert strips == snapshot


# --- validation ---------------------------------------------------------


def test_strips_container_type_error():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge({((0, 0, 1),), ((0, 0, 2),)})


def test_strips_container_type_error_string():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge("strips")


def test_too_few_strips():
    with pytest.raises(ValueError, match=r"at least 2"):
        merge([[(0, 0, 1)]])


def test_empty_strips_value_error():
    with pytest.raises(ValueError, match=r"at least 2"):
        merge([])


def test_strip_container_type_error():
    with pytest.raises(TypeError, match=r"strip\[1\]: must be a list or tuple"):
        merge([[(0, 0, 1)], "not a strip"])


def test_strip_empty_value_error():
    with pytest.raises(ValueError, match=r"strip\[1\]: must be non-empty"):
        merge([[(0, 0, 1)], []])


def test_point_container_type_error():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[1\]: must be a list or tuple"):
        merge([[(0, 0, 1), 5], [(0, 0, 2)]])


def test_point_length_value_error():
    with pytest.raises(ValueError, match=r"strip\[0\]: point\[0\]: must have exactly 3"):
        merge([[(0, 0)], [(0, 0, 2)]])
    with pytest.raises(ValueError, match=r"must have exactly 3"):
        merge([[(0, 0, 1, 2)], [(0, 0, 2)]])


def test_value_type_error():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: values must be non-bool"):
        merge([[("0", 0, 1)], [(0, 0, 2)]])


def test_bool_value_is_type_error():
    with pytest.raises(TypeError, match=r"strip\[1\]: point\[0\]: values must be non-bool"):
        merge([[(0, 0, 1)], [(0, True, 1)]])


def test_value_non_finite():
    with pytest.raises(ValueError, match=r"strip\[0\]: point\[0\]: values must be finite"):
        merge([[(0, math.inf, 1)], [(0, 0, 2)]])
    with pytest.raises(ValueError, match=r"values must be finite"):
        merge([[(0, 0, math.nan)], [(0, 0, 2)]])


def test_negative_depth_value_error():
    with pytest.raises(ValueError, match=r"strip\[1\]: point\[0\]: d must be >= 0"):
        merge([[(0, 0, 1)], [(0, 0, -0.5)]])


def test_tolerance_type_error():
    with pytest.raises(TypeError, match=r"tolerance must be a non-bool int or float"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance="1.0")


def test_tolerance_bool_type_error():
    with pytest.raises(TypeError, match=r"tolerance"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance=True)


def test_tolerance_non_finite():
    with pytest.raises(ValueError, match=r"tolerance must be finite"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance=math.inf)
    with pytest.raises(ValueError, match=r"tolerance must be finite"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance=math.nan)


def test_tolerance_zero_and_negative():
    with pytest.raises(ValueError, match=r"tolerance must be > 0"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance=0)
    with pytest.raises(ValueError, match=r"tolerance must be > 0"):
        merge([[(0, 0, 1)], [(0, 0, 2)]], tolerance=-1.0)


def test_no_matches_value_error():
    with pytest.raises(ValueError, match=r"strip\[1\]: fewer than 2"):
        merge([[(0, 0, 1), (1, 0, 1)], [(100, 0, 2), (101, 0, 2)]])


def test_single_match_value_error():
    with pytest.raises(ValueError, match=r"strip\[1\]: fewer than 2"):
        merge([[(0, 0, 1), (1, 0, 1)], [(0, 0, 2), (100, 0, 2)]])


def test_later_strip_match_failure_after_earlier_success():
    strips = [
        [(0, 0, 1), (1, 0, 1)],
        [(0, 0, 2), (1, 0, 2)],
        [(100, 0, 3), (101, 0, 3)],
    ]
    with pytest.raises(ValueError, match=r"strip\[2\]: fewer than 2"):
        merge(strips)


# --- validation order ---------------------------------------------------


def test_validation_order_container_before_length():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge({1})


def test_validation_order_length_before_strips():
    with pytest.raises(ValueError, match=r"at least 2"):
        merge(["bad"])


def test_validation_order_strip_before_points():
    # strip[0] itself is bad; its points are never inspected.
    with pytest.raises(TypeError, match=r"strip\[0\]: must be a list or tuple"):
        merge(["bad", [(0, 0, 1)]])


def test_validation_order_first_strip_wins():
    with pytest.raises(ValueError, match=r"strip\[0\]: must be non-empty"):
        merge([[], "also bad"])


def test_validation_order_first_point_wins():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]"):
        merge([["bad", (0, 0, -1)], [(0, 0, 1)]])


def test_validation_order_value_order_within_point():
    # x is checked before y and d.
    with pytest.raises(TypeError, match=r"values must be non-bool"):
        merge([[("x", math.inf, -1)], [(0, 0, 1)]])


def test_validation_order_finite_before_negative_d():
    with pytest.raises(ValueError, match=r"values must be finite"):
        merge([[(0, 0, -math.inf)], [(0, 0, 1)]])


def test_validation_order_strips_before_tolerance():
    with pytest.raises(TypeError, match=r"strip\[0\]"):
        merge(["bad", [(0, 0, 1)]], tolerance="bad")
    with pytest.raises(ValueError, match=r"at least 2"):
        merge([[(0, 0, 1)]], tolerance=0)


def test_exported():
    assert strip.__all__ == ["merge"]
    assert callable(strip.merge)
