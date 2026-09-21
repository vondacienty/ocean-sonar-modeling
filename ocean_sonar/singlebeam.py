"""Batch correction of single-beam observations.

Each observation ``(angle, time)`` is ray-traced through the same
layered sound velocity profile via :func:`ocean_sonar.svp.trace`.
"""

from __future__ import annotations

import math

from .svp import _checked_profile, _is_real_number, trace

__all__ = ["correct"]


def correct(z, c, angles, times, z0=0.0):
    """Correct a batch of single-beam observations.

    ``z``/``c`` are equal-length non-empty lists/tuples of non-bool
    int/float: ``z[0] == 0``, strictly increasing, ``c`` all positive.
    ``angles``/``times`` are equal-length non-empty lists/tuples; for
    every ``i`` the pair must be finite non-bool int/float sharing one
    type with ``z0`` (``z0 >= 0``), with ``0 <= angles[i] < 89`` and
    ``times[i] > 0``.

    Validation order (first error wins): the ``angles``/``times``
    containers, their non-emptiness and equal length, then ``z``/``c``,
    then ``z0``, then each observation in order. Observation errors —
    including total internal reflection raised by
    :func:`~ocean_sonar.svp.trace` — are prefixed with
    ``"observation[i]: "``.

    Returns a tuple of ``(x, d)`` pairs in input order, each value a
    float rounded to 6 decimals (negative zero normalized to ``0.0``).
    Inputs are not modified.
    """
    if not isinstance(angles, (list, tuple)):
        raise TypeError("angles must be a list or tuple")
    if not isinstance(times, (list, tuple)):
        raise TypeError("times must be a list or tuple")
    if len(angles) == 0:
        raise ValueError("angles must be non-empty")
    if len(times) == 0:
        raise ValueError("times must be non-empty")
    if len(angles) != len(times):
        raise ValueError("angles and times must have equal length")

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

    results = []
    for i in range(len(angles)):
        a = angles[i]
        t = times[i]
        prefix = f"observation[{i}]: "
        if not _is_real_number(a):
            raise TypeError(prefix + "angles elements must be non-bool int or float")
        if not _is_real_number(t):
            raise TypeError(prefix + "times elements must be non-bool int or float")
        if not (type(a) is type(t) is type(z0)):
            raise TypeError(prefix + "angle, time and z0 must have the same type")
        if not math.isfinite(a):
            raise ValueError(prefix + "angle must be finite")
        if not math.isfinite(t):
            raise ValueError(prefix + "time must be finite")
        if not 0 <= a < 89:
            raise ValueError(prefix + "angle must satisfy 0 <= a < 89")
        if not t > 0:
            raise ValueError(prefix + "time must be positive")
        try:
            results.append(trace(z, c, a, t, z0))
        except ValueError as exc:
            raise ValueError(prefix + str(exc)) from exc
    return tuple(results)
