"""Tests for strip.merge overlapping-strip depth alignment."""

import math

import pytest

from ocean_sonar import strip
from ocean_sonar.strip import merge


# --- behaviour ----------------------------------------------------------


def test_first_strip_accumulated_unchanged():
    result = merge(
        [
            [(0.0, 0.0, 10.0), (1.0, 2.0, 3.0)],
            [(0.0, 0.0, 11.0), (1.0, 2.0, 4.0)],
        ]
    )
    assert result[0] == (0.0, 0.0, 10.0)
    assert result[1] == (1.0, 2.0, 3.0)


def test_uniform_bias_removed():
    # Every overlap point of strip 2 reads exactly 2 m too deep.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
            [(0.0, 0.0, 12.0), (10.0, 0.0, 22.0)],
        ]
    )
    assert result == (
        (0.0, 0.0, 10.0),
        (10.0, 0.0, 20.0),
        (0.0, 0.0, 10.0),
        (10.0, 0.0, 20.0),
    )


def test_median_offset_even_count_middle_mean():
    # Differences 1 and -1 sort to [-1, 1]; median is their mean 0, so
    # the strip is accumulated unchanged.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
            [(0.0, 0.0, 11.0), (10.0, 0.0, 19.0)],
        ]
    )
    assert result[2] == (0.0, 0.0, 11.0)
    assert result[3] == (10.0, 0.0, 19.0)


def test_median_uses_mean_of_two_middle_values():
    # Differences [1, 2, 3, 100] sort to [1, 2, 3, 100], median 2.5.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (30.0, 0.0, 0.0)],
            [(0.0, 0.0, 11.0), (10.0, 0.0, 2.0), (20.0, 0.0, 3.0), (30.0, 0.0, 100.0)],
        ]
    )
    assert [point[2] for point in result[4:]] == [8.5, -0.5, 0.5, 97.5]


def test_nearest_within_tolerance_is_chosen():
    # Accumulated points at x = 0 (depth 10) and x = 1 (depth 20).
    # The new point (0.4, 0) is nearer to x = 0 -> old depth 10,
    # difference 2; the other new point gives difference -5.
    # Median of [-5, 2] is -1.5, so depths are shifted up by 1.5.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (1.0, 0.0, 20.0)],
            [(0.4, 0.0, 12.0), (0.0, 0.9, 5.0)],
        ]
    )
    assert result[2] == (0.4, 0.0, 13.5)
    assert result[3] == (0.0, 0.9, 6.5)


def test_tie_picks_earliest_accumulated_point():
    # (0.5, 0) is exactly equidistant (0.5) from both accumulated
    # points; the earliest one (depth 10) must win. With the later
    # depth 20 wrongly chosen the median of [-8, -5] would be -6.5.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (1.0, 0.0, 20.0)],
            [(0.5, 0.0, 12.0), (0.0, 0.9, 5.0)],
        ]
    )
    assert result[2] == (0.5, 0.0, 13.5)
    assert result[3] == (0.0, 0.9, 6.5)


def test_distance_equal_to_tolerance_matches():
    # Both new points are exactly one unit from the accumulated point.
    result = merge(
        [
            [(0.0, 0.0, 10.0)],
            [(1.0, 0.0, 11.0), (0.0, 1.0, 12.0)],
        ],
        tolerance=1.0,
    )
    assert [point[2] for point in result[1:]] == [9.5, 10.5]


def test_points_farther_than_tolerance_do_not_match():
    # (2, 0) is 2 m away, outside the default tolerance; only the
    # coincident point matches -> fewer than two matches.
    with pytest.raises(ValueError, match=r"strip\[1\]: at least 2 matches required"):
        merge(
            [
                [(0.0, 0.0, 10.0)],
                [(0.0, 0.0, 11.0), (2.0, 0.0, 12.0)],
            ],
            tolerance=1.0,
        )


def test_accumulated_point_may_be_reused():
    # A single accumulated point serves both new points.
    result = merge(
        [
            [(0.0, 0.0, 10.0)],
            [(0.1, 0.0, 11.0), (-0.1, 0.0, 12.0)],
        ]
    )
    assert [point[2] for point in result[1:]] == [9.5, 10.5]


def test_unmatched_points_still_accumulated_with_correction():
    # Differences [1, 1] -> b = 1; the far-away point matches nothing
    # but is still shifted and accumulated.
    result = merge(
        [
            [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
            [(0.0, 0.0, 11.0), (10.0, 0.0, 21.0), (100.0, 100.0, 5.0)],
        ]
    )
    assert result[4] == (100.0, 100.0, 4.0)


def test_three_strip_chain_matches_corrected_depths():
    result = merge(
        [
            [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
            [(0.0, 0.0, 11.0), (10.0, 0.0, 21.0)],
            [(0.0, 0.0, 10.5), (10.0, 0.0, 20.5)],
        ]
    )
    assert result == (
        (0.0, 0.0, 10.0),
        (10.0, 0.0, 20.0),
        (0.0, 0.0, 10.0),
        (10.0, 0.0, 20.0),
        (0.0, 0.0, 10.0),
        (10.0, 0.0, 20.0),
    )


def test_corrected_depths_are_not_rounded_between_strips():
    # Strip 2's offset is the fraction 2/3; strip 3's offset relative
    # to the *unrounded* corrected depths is exactly 0.2. Rounding the
    # intermediate depths to 6 decimals would bias b and round the last
    # depth to 5.0 instead of 5.000001.
    v = 2 / 3
    result = merge(
        [
            [(0.0, 0.0, 10.0)],
            [
                (0.0, 0.0, 10.0 + v),
                (1.0, 0.0, 10.0 + v),
                (5.0, 0.0, 7.0),
                (6.0, 0.0, 8.0),
            ],
            [
                (5.0, 0.0, 7.0 - v + 0.2),
                (6.0, 0.0, 8.0 - v + 0.2),
                (20.0, 0.0, 5.0000006 + 0.2),
            ],
        ]
    )
    assert result[-1] == (20.0, 0.0, 5.000001)


def test_custom_tolerance_changes_matches():
    with pytest.raises(ValueError, match=r"at least 2 matches required"):
        merge(
            [
                [(0.0, 0.0, 10.0)],
                [(1.5, 0.0, 11.0), (0.0, 1.5, 12.0)],
            ],
            tolerance=1.0,
        )
    result = merge(
        [
            [(0.0, 0.0, 10.0)],
            [(1.5, 0.0, 11.0), (0.0, 1.5, 12.0)],
        ],
        tolerance=2.0,
    )
    assert [point[2] for point in result[1:]] == [9.5, 10.5]


def test_default_tolerance_is_one():
    # Points exactly on the unit circle match with the default.
    result = merge(
        [
            [(0.0, 0.0, 10.0)],
            [(0.0, 1.0, 11.0), (1.0, 0.0, 12.0)],
        ]
    )
    assert len(result) == 3


def test_flat_output_in_strip_and_point_order():
    result = merge(
        [
            [(0.0, 0.0, 1.0)],
            [(2.0, 3.0, 2.0), (4.0, 5.0, 3.0)],
            [(6.0, 7.0, 4.0), (8.0, 9.0, 5.0), (10.0, 11.0, 6.0)],
        ],
        tolerance=100.0,
    )
    assert isinstance(result, tuple)
    assert [(p[0], p[1]) for p in result] == [
        (0.0, 0.0),
        (2.0, 3.0),
        (4.0, 5.0),
        (6.0, 7.0),
        (8.0, 9.0),
        (10.0, 11.0),
    ]
    assert all(isinstance(point, tuple) for point in result)
    assert all(type(value) is float for point in result for value in point)


def test_int_inputs_become_float_outputs():
    result = merge(
        [
            [(0, 0, 10)],
            [(0, 0, 10), (1, 0, 20)],
        ]
    )
    assert result[0] == (0.0, 0.0, 10.0)
    assert all(type(value) is float for point in result for value in point)


def test_negative_zero_normalized():
    # Matching differences are 0.0000001 and 0.0000003; median 0.0000002.
    # The unmatched far point has depth 0.0000001 and becomes
    # -0.0000001, which rounds to a positive-normalized 0.0; the
    # -0.0 x coordinate must likewise come out as 0.0.
    result = merge(
        [
            [(-0.0, 0.0, 10.0), (1.0, 0.0, 20.0)],
            [(0.0, 0.0, 10.0000001), (1.0, 0.0, 20.0000003), (100.0, 100.0, 0.0000001)],
        ]
    )
    for point in result:
        for value in point:
            assert math.copysign(1.0, value) == 1.0
    assert result[0][0] == 0.0
    assert result[-1][2] == 0.0


def test_inputs_not_modified():
    strips = [
        [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
        [(0.0, 0.0, 12.0), (10.0, 0.0, 22.0)],
    ]
    snapshot = [[list(point) for point in s] for s in strips]
    merge(strips)
    assert [[list(point) for point in s] for s in strips] == snapshot


# --- validation ---------------------------------------------------------


def test_strips_container_type_error():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge({((0.0, 0.0, 1.0),), ((0.0, 0.0, 2.0),)})


def test_strips_container_type_error_string():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge("ab")


def test_too_few_strips_empty():
    with pytest.raises(ValueError, match=r"strips must have at least 2 elements"):
        merge([])


def test_too_few_strips_single():
    with pytest.raises(ValueError, match=r"strips must have at least 2 elements"):
        merge([[(0.0, 0.0, 1.0)]])


def test_length_checked_before_strip_contents():
    # The single strip is itself invalid, but the count wins.
    with pytest.raises(ValueError, match=r"strips must have at least 2 elements"):
        merge([[]])


def test_strip_item_type_error():
    with pytest.raises(TypeError, match=r"strip\[1\]: must be a list or tuple"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                "not-a-strip",
            ]
        )


def test_empty_strip_value_error():
    with pytest.raises(ValueError, match=r"strip\[1\]: must be non-empty"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [],
            ]
        )


def test_first_strip_empty_value_error():
    with pytest.raises(ValueError, match=r"strip\[0\]: must be non-empty"):
        merge(
            [
                [],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_point_container_type_error():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: must be a list or tuple"):
        merge(
            [
                [1.0],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_point_wrong_length_too_few():
    with pytest.raises(ValueError, match=r"strip\[1\]: point\[1\]: must have 3 elements"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 1.0), (0.0, 0.0)],
            ]
        )


def test_point_wrong_length_too_many():
    with pytest.raises(ValueError, match=r"strip\[0\]: point\[0\]: must have 3 elements"):
        merge(
            [
                [(0.0, 0.0, 1.0, 2.0)],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_x_type_error():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: x must be a non-bool int or float"):
        merge(
            [
                [("0", 0.0, 1.0)],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_y_type_error():
    with pytest.raises(TypeError, match=r"strip\[1\]: point\[0\]: y must be a non-bool int or float"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, None, 1.0)],
            ]
        )


def test_d_type_error():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: d must be a non-bool int or float"):
        merge(
            [
                [(0.0, 0.0, "1")],
                [(0.0, 0.0, 1.0)],
            ]
        )


@pytest.mark.parametrize("field", ["x", "y", "d"])
def test_bool_value_is_type_error(field):
    point = {"x": 0.0, "y": 0.0, "d": 1.0}
    point[field] = True
    with pytest.raises(TypeError, match=rf"strip\[0\]: point\[0\]: {field} must be a non-bool int or float"):
        merge(
            [
                [tuple(point[k] for k in ("x", "y", "d"))],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_non_finite_x():
    with pytest.raises(ValueError, match=r"strip\[0\]: point\[0\]: x must be finite"):
        merge(
            [
                [(math.inf, 0.0, 1.0)],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_nan_y():
    with pytest.raises(ValueError, match=r"strip\[1\]: point\[0\]: y must be finite"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, math.nan, 1.0)],
            ]
        )


def test_non_finite_d():
    with pytest.raises(ValueError, match=r"strip\[0\]: point\[0\]: d must be finite"):
        merge(
            [
                [(0.0, 0.0, math.inf)],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_negative_depth():
    with pytest.raises(ValueError, match=r"strip\[1\]: point\[0\]: d must be >= 0"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, -0.5)],
            ]
        )


def test_negative_zero_depth_allowed():
    result = merge(
        [
            [(0.0, 0.0, -0.0)],
            [(0.0, 0.0, 1.0), (1.0, 0.0, 2.0)],
        ]
    )
    assert result[0][2] == 0.0


def test_tolerance_type_error():
    with pytest.raises(TypeError, match=r"tolerance must be a non-bool int or float"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance="1",
        )


def test_tolerance_bool_type_error():
    with pytest.raises(TypeError, match=r"tolerance must be a non-bool int or float"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance=True,
        )


def test_tolerance_non_finite():
    with pytest.raises(ValueError, match=r"tolerance must be finite"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance=math.inf,
        )


def test_tolerance_nan():
    with pytest.raises(ValueError, match=r"tolerance must be finite"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance=math.nan,
        )


def test_tolerance_zero():
    with pytest.raises(ValueError, match=r"tolerance must be > 0"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance=0,
        )


def test_tolerance_negative():
    with pytest.raises(ValueError, match=r"tolerance must be > 0"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 2.0)],
            ],
            tolerance=-1.0,
        )


def test_strips_validated_before_tolerance():
    with pytest.raises(TypeError, match=r"strips must be a list or tuple"):
        merge("ab", tolerance=0)
    with pytest.raises(ValueError, match=r"strip\[0\]: must be non-empty"):
        merge(
            [
                [],
                [(0.0, 0.0, 1.0)],
            ],
            tolerance=0,
        )


def test_strip_index_order_first_bad_wins():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: must be a list or tuple"):
        merge(
            [
                [1.0],
                [2.0],
            ]
        )


def test_point_index_order_first_bad_wins():
    with pytest.raises(ValueError, match=r"strip\[1\]: point\[1\]: must have 3 elements"):
        merge(
            [
                [(0.0, 0.0, 1.0)],
                [(0.0, 0.0, 1.0), (0.0, 0.0), (0.0, 0.0, -1.0)],
            ]
        )


def test_field_order_x_before_d():
    with pytest.raises(TypeError, match=r"strip\[0\]: point\[0\]: x must be a non-bool int or float"):
        merge(
            [
                [("x", 0.0, -1.0)],
                [(0.0, 0.0, 1.0)],
            ]
        )


def test_insufficient_matches_zero():
    with pytest.raises(ValueError, match=r"strip\[1\]: at least 2 matches required"):
        merge(
            [
                [(0.0, 0.0, 10.0)],
                [(100.0, 100.0, 1.0), (200.0, 200.0, 2.0)],
            ]
        )


def test_insufficient_matches_one():
    with pytest.raises(ValueError, match=r"strip\[2\]: at least 2 matches required"):
        merge(
            [
                [(0.0, 0.0, 10.0)],
                [(0.0, 0.0, 11.0), (1.0, 0.0, 12.0)],
                [(0.0, 0.0, 11.0), (200.0, 200.0, 2.0)],
            ]
        )


def test_exported():
    assert strip.__all__ == ["merge", "batch"]
    assert callable(strip.merge)
    assert callable(strip.batch)
