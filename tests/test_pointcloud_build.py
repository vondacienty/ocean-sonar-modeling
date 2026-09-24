"""Tests for pointcloud.build."""

import math

import pytest

from ocean_sonar import pointcloud


def test_vertical_beam_zero_attitude_zero_tide():
    # d = 1500 * 0.1 / 2 = 75; x = 0; y = 2; level 1 -> 74.
    result = pointcloud.build(
        [(0.0, 0.1, 2.0, 0.0, 0.0, 0.0)],
        [0, 100],
        [1500.0, 1500.0],
        [0.0, 10.0],
        [1.0, 1.0],
    )
    assert result == ((0.0, 2.0, 74.0),)


def test_z0_heave_interpolation_and_datum():
    # z0 = 0, int types throughout; d = 1500; heave 1 -> 1499;
    # level at t = 2 is 0.4; datum 3 -> 1499 - 0.4 + 3 = 1501.6.
    result = pointcloud.build(
        [(0, 2, 5, 0, 0, 1)],
        [0, 1000],
        [1500, 1500],
        [0, 10],
        [0, 2],
        z0=0,
        datum=3,
    )
    assert result == ((0.0, 5.0, 1501.6),)


def test_results_in_order_are_float_triples():
    result = pointcloud.build(
        [
            (0.0, 0.1, 0.0, 0.0, 0.0, 0.0),
            (0.0, 0.2, 1.0, 0.0, 0.0, 2.5),
        ],
        [0],
        [1500.0],
        [0, 1],
        [0.0, 0.0],
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result == ((0.0, 0.0, 75.0), (0.0, 1.0, 147.5))
    for triple in result:
        assert isinstance(triple, tuple)
        assert len(triple) == 3
        assert all(type(v) is float for v in triple)


def test_attitude_changes_xy_d():
    # Vertical beam gives x = 0, d = 1500 * 0.1 / 2 = 75; with y = 1 and
    # a 90 deg roll: X = y = 1, Y = -d = -75, D = y = 1.
    result = pointcloud.build(
        [(0.0, 0.1, 1.0, 90.0, 0.0, 0.0)],
        [0],
        [1500.0],
        [0, 1],
        [0.0, 0.0],
    )
    assert result == ((0.0, -75.0, 1.0),)


def test_negative_zero_normalized():
    # d = 15, heave = 15 -> attitude D = 0; tide level 0 -> D = 0.
    result = pointcloud.build(
        [(0.0, 0.02, 0.0, 0.0, 0.0, 15.0)],
        [0],
        [1500.0],
        [0, 1],
        [0.0, 0.0],
    )
    assert result == ((0.0, 0.0, 0.0),)
    for value in result[0]:
        assert math.copysign(1.0, value) > 0


def test_input_not_modified():
    observations = [(0.0, 0.1, 2.0, 0.0, 0.0, 0.0)]
    z = [0, 100]
    c = [1500.0, 1500.0]
    tide_times = [0.0, 10.0]
    levels = [1.0, 1.0]
    snapshot = [list(observations), list(z), list(c), list(tide_times), list(levels)]
    pointcloud.build(observations, z, c, tide_times, levels)
    assert [list(observations), list(z), list(c), list(tide_times), list(levels)] == snapshot


def test_stages_called_once_in_order(monkeypatch):
    import ocean_sonar.attitude as attitude_module
    import ocean_sonar.singlebeam as singlebeam_module
    import ocean_sonar.tide as tide_module

    calls = []
    real_singlebeam = singlebeam_module.correct
    real_attitude = attitude_module.correct
    real_tide = tide_module.reduce
    beam = real_singlebeam([0, 100], [1500.0, 1500.0], [0.0], [0.1], 0.0)

    def fake_singlebeam(*args, **kwargs):
        calls.append("singlebeam")
        return beam

    def fake_attitude(observations):
        calls.append("attitude")
        return real_attitude(observations)

    def fake_tide(*args, **kwargs):
        calls.append("tide")
        return real_tide(*args, **kwargs)

    monkeypatch.setattr(singlebeam_module, "correct", fake_singlebeam)
    monkeypatch.setattr(attitude_module, "correct", fake_attitude)
    monkeypatch.setattr(tide_module, "reduce", fake_tide)

    result = pointcloud.build(
        [(0.0, 0.1, 2.0, 0.0, 0.0, 0.0)],
        [0, 100],
        [1500.0, 1500.0],
        [0.0, 10.0],
        [1.0, 1.0],
    )
    assert calls == ["singlebeam", "attitude", "tide"]
    assert result == ((0.0, 2.0, 74.0),)


def test_singlebeam_error_propagates_unchanged():
    # Faster layer at grazing angle raises total internal reflection.
    with pytest.raises(ValueError, match=r"observation\[0\]: total internal reflection"):
        pointcloud.build(
            [(88.0, 1.0, 0.0, 0.0, 0.0, 0.0)],
            [0, 1],
            [1500.0, 3000.0],
            [0, 1],
            [0.0, 0.0],
        )


def test_tide_error_propagates_unchanged():
    with pytest.raises(
        ValueError,
        match=r"observation\[0\]: time must be within the tide time range",
    ):
        pointcloud.build(
            [(0.0, 2.0, 0.0, 0.0, 0.0, 0.0)],
            [0],
            [1500.0],
            [0, 1],
            [0.0, 0.0],
        )


def test_observations_container_type():
    with pytest.raises(TypeError, match="observations must be a list or tuple"):
        pointcloud.build("nope", [0], [1500.0], [0, 1], [0.0, 0.0])


def test_observations_empty():
    with pytest.raises(ValueError, match="observations must be non-empty"):
        pointcloud.build([], [0], [1500.0], [0, 1], [0.0, 0.0])


def test_item_container_type():
    with pytest.raises(TypeError, match=r"observation\[0\]: must be a list or tuple"):
        pointcloud.build(["nope"], [0], [1500.0], [0, 1], [0.0, 0.0])


def test_item_length():
    with pytest.raises(ValueError, match=r"observation\[1\]: must have 6 elements"):
        pointcloud.build(
            [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0), (1.0, 2.0, 3.0)],
            [0],
            [1500.0],
            [0, 1],
            [0.0, 0.0],
        )


def test_field_type_errors_in_order():
    with pytest.raises(TypeError, match=r"observation\[0\]: angle must be a non-bool"):
        pointcloud.build(
            [(True, 0.1, 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(TypeError, match=r"observation\[0\]: time must be a non-bool"):
        pointcloud.build(
            [(0.0, "t", 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(TypeError, match=r"observation\[0\]: y must be a non-bool"):
        pointcloud.build(
            [(0.0, 0.1, None, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(TypeError, match=r"observation\[0\]: heave must be a non-bool"):
        pointcloud.build(
            [(0.0, 0.1, 0.0, 0.0, 0.0, False)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )


def test_angle_time_z0_same_type():
    with pytest.raises(
        TypeError,
        match=r"observation\[0\]: angle, time and z0 must have the same type",
    ):
        pointcloud.build(
            [(0, 0.1, 0, 0, 0, 0)],
            [0], [1500], [0, 1], [0, 0],
        )
    with pytest.raises(
        TypeError,
        match=r"observation\[0\]: angle, time and z0 must have the same type",
    ):
        pointcloud.build(
            [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0], z0=0,
        )


def test_field_finite_errors_in_order():
    with pytest.raises(ValueError, match=r"observation\[0\]: angle must be finite"):
        pointcloud.build(
            [(math.nan, 0.1, 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(ValueError, match=r"observation\[0\]: time must be finite"):
        pointcloud.build(
            [(0.0, math.inf, 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(ValueError, match=r"observation\[0\]: roll must be finite"):
        pointcloud.build(
            [(0.0, 0.1, 0.0, math.inf, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )


def test_angle_range_and_time_positive():
    with pytest.raises(ValueError, match=r"observation\[0\]: angle must satisfy"):
        pointcloud.build(
            [(89.0, 0.1, 0.0, 0.0, 0.0, 0.0)],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )
    with pytest.raises(ValueError, match=r"observation\[1\]: time must be positive"):
        pointcloud.build(
            [
                (0.0, 0.1, 0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ],
            [0], [1500.0], [0, 1], [0.0, 0.0],
        )


def test_observations_validated_before_profile():
    with pytest.raises(TypeError, match="observations must be a list or tuple"):
        pointcloud.build("nope", "z", "c", [0, 1], [0.0, 0.0])


def test_profile_errors():
    good = [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0)]
    with pytest.raises(TypeError, match="z must be a list or tuple"):
        pointcloud.build(good, "z", [1500.0], [0, 1], [0.0, 0.0])
    with pytest.raises(ValueError, match="z must be non-empty"):
        pointcloud.build(good, [], [1500.0], [0, 1], [0.0, 0.0])
    with pytest.raises(ValueError, match="z and c must have equal length"):
        pointcloud.build(good, [0, 1], [1500.0], [0, 1], [0.0, 0.0])
    with pytest.raises(ValueError, match="z\[0\] must be 0"):
        pointcloud.build(good, [1], [1500.0], [0, 1], [0.0, 0.0])
    with pytest.raises(ValueError, match="z must be strictly increasing"):
        pointcloud.build(good, [0, 0], [1500.0, 1500.0], [0, 1], [0.0, 0.0])
    with pytest.raises(ValueError, match="c elements must be positive"):
        pointcloud.build(good, [0, 1], [1500.0, 0.0], [0, 1], [0.0, 0.0])


def test_z0_validated_after_profile():
    good = [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0)]
    # A wrong-typed z0 is reported by the per-item same-type check first,
    # exactly as in singlebeam.correct.
    with pytest.raises(
        TypeError,
        match=r"observation\[0\]: angle, time and z0 must have the same type",
    ):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, 0.0], z0="x")
    with pytest.raises(ValueError, match="z0 must be finite"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, 0.0], z0=math.nan)
    with pytest.raises(ValueError, match="z0 must be >= 0"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, 0.0], z0=-1.0)


def test_tide_node_errors():
    good = [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0)]
    with pytest.raises(TypeError, match="tide_times must be a list or tuple"):
        pointcloud.build(good, [0], [1500.0], 1, [0.0, 0.0])
    with pytest.raises(TypeError, match="levels must be a list or tuple"):
        pointcloud.build(good, [0], [1500.0], [0, 1], 1)
    with pytest.raises(ValueError, match="tide_times must be non-empty"):
        pointcloud.build(good, [0], [1500.0], [], [])
    with pytest.raises(ValueError, match="tide_times and levels must have equal length"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0])
    with pytest.raises(ValueError, match="tide_times must have at least 2 nodes"):
        pointcloud.build(good, [0], [1500.0], [0], [0.0])
    with pytest.raises(ValueError, match="tide_times must be strictly increasing"):
        pointcloud.build(good, [0], [1500.0], [1, 0], [0.0, 0.0])
    with pytest.raises(TypeError, match="levels elements must be non-bool"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, True])
    with pytest.raises(ValueError, match="levels elements must be finite"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, math.nan])


def test_datum_validated_last():
    good = [(0.0, 0.1, 0.0, 0.0, 0.0, 0.0)]
    with pytest.raises(TypeError, match="datum must be a non-bool int or float"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, 0.0], datum="x")
    with pytest.raises(ValueError, match="datum must be finite"):
        pointcloud.build(good, [0], [1500.0], [0, 1], [0.0, 0.0], datum=math.inf)
