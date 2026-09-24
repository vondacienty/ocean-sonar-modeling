"""Point-cloud building from raw single-beam observations.

Each observation ``(angle, time, y, roll, pitch, heave)`` is ray-traced
through the layered sound velocity profile with
:func:`ocean_sonar.singlebeam.correct`, corrected for vessel attitude
with :func:`ocean_sonar.attitude.correct` and reduced to chart datum
with :func:`ocean_sonar.tide.reduce`. The three stages run once each,
in that order, over the whole batch.
"""

from __future__ import annotations

import math

from . import attitude, singlebeam, tide
from .svp import _checked_profile, _is_real_number

__all__ = ["build"]

_FIELDS = ("angle", "time", "y", "roll", "pitch", "heave")


def _round6(value):
    value = round(float(value), 6)
    return 0.0 if value == 0 else value


def build(observations, z, c, tide_times, levels, z0=0.0, datum=0.0):
    """Build a georeferenced point cloud from single-beam observations.

    ``observations`` is a non-empty list/tuple whose items are
    six-element lists/tuples ``(angle, time, y, roll, pitch, heave)``.
    Every value must be a finite non-bool int/float; ``angle`` and
    ``time`` must share one type with ``z0`` (``z0 >= 0``), with
    ``0 <= angle < 89`` and ``time > 0``. ``y`` is the along-track
    beam offset; ``roll``/``pitch`` are in degrees and ``heave`` in
    metres (positive up).

    ``z``/``c`` are equal-length non-empty lists/tuples of non-bool
    int/float: ``z[0] == 0``, strictly increasing, ``c`` all positive.
    ``tide_times``/``levels`` are equal-length lists/tuples with at
    least two nodes, ``tide_times`` strictly increasing, and every
    element finite. ``datum`` must be a finite non-bool int/float.

    Validation order (first error wins): the ``observations``
    container, its non-emptiness, then per observation the item
    container, its length and the fields ``angle``, ``time``, ``y``,
    ``roll``, ``pitch``, ``heave`` in that order, then ``z``/``c``,
    ``z0``, the tide nodes and ``datum``. Container and value type
    errors raise ``TypeError``; every other violation raises
    ``ValueError``. Item error messages are prefixed with
    ``"observation[i]: "``.

    After validation the pipeline runs exactly once per stage:
    :func:`~ocean_sonar.singlebeam.correct` supplies the horizontal
    offset ``x`` and uncorrected depth ``d`` of each sounding, which
    are fed to :func:`~ocean_sonar.attitude.correct` as
    ``(x, y, d, roll, pitch, heave)``; the attitude-corrected depths
    are then passed to :func:`~ocean_sonar.tide.reduce`. Any exception
    raised by a stage propagates unchanged.

    Returns a tuple in observation order of ``(X, Y, D)`` triples of
    floats, ``X``/``Y`` taken from the attitude stage and ``D`` from
    the tide stage, each rounded to 6 decimals (negative zero
    normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(observations, (list, tuple)):
        raise TypeError("observations must be a list or tuple")
    if len(observations) == 0:
        raise ValueError("observations must be non-empty")

    angles = []
    times = []
    for i in range(len(observations)):
        obs = observations[i]
        prefix = f"observation[{i}]: "
        if not isinstance(obs, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(obs) != 6:
            raise ValueError(prefix + "must have 6 elements")

        for name, value in zip(_FIELDS, obs):
            if not _is_real_number(value):
                raise TypeError(
                    prefix + f"{name} must be a non-bool int or float"
                )

        angle, time_value, y, roll, pitch, heave = obs
        if not (type(angle) is type(time_value) is type(z0)):
            raise TypeError(
                prefix + "angle, time and z0 must have the same type"
            )

        for name, value in zip(_FIELDS, obs):
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")

        if not 0 <= angle < 89:
            raise ValueError(prefix + "angle must satisfy 0 <= a < 89")
        if not time_value > 0:
            raise ValueError(prefix + "time must be positive")

        angles.append(angle)
        times.append(time_value)

    zs = _checked_profile("z", z)
    cs = _checked_profile("c", c)
    if len(zs) != len(cs):
        raise ValueError("z and c must have equal length")
    if zs[0] != 0:
        raise ValueError("z[0] must be 0")
    for k in range(len(zs) - 1):
        if not zs[k] < zs[k + 1]:
            raise ValueError("z must be strictly increasing")
    for speed in cs:
        if not speed > 0:
            raise ValueError("c elements must be positive")

    if not _is_real_number(z0):
        raise TypeError("z0 must be a non-bool int or float")
    if not math.isfinite(z0):
        raise ValueError("z0 must be finite")
    if not z0 >= 0:
        raise ValueError("z0 must be >= 0")

    for name, values in (("tide_times", tide_times), ("levels", levels)):
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"{name} must be a list or tuple")
    for name, values in (("tide_times", tide_times), ("levels", levels)):
        if len(values) == 0:
            raise ValueError(f"{name} must be non-empty")
    if len(tide_times) != len(levels):
        raise ValueError("tide_times and levels must have equal length")
    if len(tide_times) < 2:
        raise ValueError("tide_times must have at least 2 nodes")

    for name, values in (("tide_times", tide_times), ("levels", levels)):
        for item in values:
            if not _is_real_number(item):
                raise TypeError(
                    f"{name} elements must be non-bool int or float"
                )
    for name, values in (("tide_times", tide_times), ("levels", levels)):
        for item in values:
            if not math.isfinite(item):
                raise ValueError(f"{name} elements must be finite")
    for k in range(len(tide_times) - 1):
        if not tide_times[k] < tide_times[k + 1]:
            raise ValueError("tide_times must be strictly increasing")

    if not _is_real_number(datum):
        raise TypeError("datum must be a non-bool int or float")
    if not math.isfinite(datum):
        raise ValueError("datum must be finite")

    beam = singlebeam.correct(z, c, angles, times, z0)
    attitude_observations = [
        (beam[i][0], observations[i][2], beam[i][1],
         observations[i][3], observations[i][4], observations[i][5])
        for i in range(len(observations))
    ]
    positioned = attitude.correct(attitude_observations)
    attitude_depths = [triple[2] for triple in positioned]
    reduced_depths = tide.reduce(
        times, attitude_depths, tide_times, levels, datum
    )

    return tuple(
        (
            _round6(positioned[i][0]),
            _round6(positioned[i][1]),
            _round6(reduced_depths[i]),
        )
        for i in range(len(observations))
    )
