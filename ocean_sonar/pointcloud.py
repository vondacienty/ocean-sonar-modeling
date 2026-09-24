"""Point cloud construction from single-beam survey observations.

Each observation ``(angle, time, y, roll, pitch, heave)`` is corrected
for sound velocity (:func:`ocean_sonar.singlebeam.correct`), vessel
attitude (:func:`ocean_sonar.attitude.correct`) and tide
(:func:`ocean_sonar.tide.reduce`), yielding one ``(X, Y, D)`` point per
observation.
"""

from __future__ import annotations

import math

from . import attitude, singlebeam, tide
from .svp import _checked_profile, _is_real_number

__all__ = ["build"]

_FIELDS = ("angle", "time", "y", "roll", "pitch", "heave")


def build(observations, z, c, tide_times, levels, z0=0.0, datum=0.0):
    """Build a corrected point cloud from survey observations.

    ``observations`` is a non-empty list/tuple whose items are
    six-element lists/tuples ``(angle, time, y, roll, pitch, heave)``.
    Every value must be a finite non-bool int/float; ``angle`` must
    satisfy ``0 <= angle < 89``, ``time`` must be positive and
    ``angle``, ``time`` and ``z0`` must share one type. ``z``/``c`` are
    equal-length non-empty lists/tuples of non-bool int/float:
    ``z[0] == 0``, strictly increasing, ``c`` all positive. ``z0`` must
    be ``>= 0``. ``tide_times``/``levels`` are equal-length lists/tuples
    with at least two nodes, ``tide_times`` strictly increasing.
    ``datum`` must be a finite non-bool int/float.

    Validation order (first error wins): the ``observations`` container,
    its non-emptiness, then per observation the item container, its
    length and the fields ``angle``, ``time``, ``y``, ``roll``,
    ``pitch``, ``heave`` in that order, then ``z``/``c``, then ``z0``,
    then the tide nodes, then ``datum``. Type errors raise
    ``TypeError``; all other validation errors raise ``ValueError``.
    Item error messages are prefixed with ``"observation[i]: "``.

    The validated inputs are passed once to
    :func:`~ocean_sonar.singlebeam.correct`,
    :func:`~ocean_sonar.attitude.correct` and
    :func:`~ocean_sonar.tide.reduce` in that order; any exception they
    raise propagates unchanged.

    Returns a tuple in observation order of ``(X, Y, D)`` triples of
    floats, ``X``/``Y`` from the attitude correction and ``D`` from the
    tide reduction, each rounded to 6 decimals (negative zero
    normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(observations, (list, tuple)):
        raise TypeError("observations must be a list or tuple")
    if len(observations) == 0:
        raise ValueError("observations must be non-empty")

    for i in range(len(observations)):
        obs = observations[i]
        prefix = f"observation[{i}]: "
        if not isinstance(obs, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(obs) != 6:
            raise ValueError(prefix + "must have 6 elements")
        for name, value in zip(_FIELDS, obs):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
        angle, time = obs[0], obs[1]
        if not (type(angle) is type(time) is type(z0)):
            raise TypeError(prefix + "angle, time and z0 must have the same type")
        if not 0 <= angle < 89:
            raise ValueError(prefix + "angle must satisfy 0 <= angle < 89")
        if not time > 0:
            raise ValueError(prefix + "time must be positive")

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
    if len(tide_times) != len(levels):
        raise ValueError("tide_times and levels must have equal length")
    if len(tide_times) < 2:
        raise ValueError("tide_times must have at least 2 nodes")
    for name, values in (("tide_times", tide_times), ("levels", levels)):
        for item in values:
            if not _is_real_number(item):
                raise TypeError(f"{name} elements must be non-bool int or float")
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

    angles = [obs[0] for obs in observations]
    times = [obs[1] for obs in observations]

    single = singlebeam.correct(z, c, angles, times, z0)
    attitude_obs = [
        (single[i][0], obs[2], single[i][1], obs[3], obs[4], obs[5])
        for i, obs in enumerate(observations)
    ]
    corrected = attitude.correct(attitude_obs)
    reduced = tide.reduce(
        times, [item[2] for item in corrected], tide_times, levels, datum
    )

    points = []
    for i in range(len(observations)):
        point = []
        for v in (corrected[i][0], corrected[i][1], reduced[i]):
            v = round(float(v), 6)
            point.append(0.0 if v == 0 else v)
        points.append(tuple(point))
    return tuple(points)
