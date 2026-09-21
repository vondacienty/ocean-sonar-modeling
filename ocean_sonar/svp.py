"""Sound velocity profile (SVP) and ray tracing utilities."""

from __future__ import annotations

import math
from bisect import bisect_right


def _check_number(value: object, name: str) -> None:
    """Validate a scalar: non-bool int/float and finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a non-bool int or float")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def trace(z, c, a, t, z0=0.0):
    """Trace a sonar ray through a layered sound velocity profile.

    Layer ``i`` covers ``[z[i], z[i+1])`` with sound speed ``c[i]``; the last
    layer extends downward indefinitely. A boundary depth belongs to the
    layer below it.

    :param z: non-empty list/tuple of layer boundary depths, strictly
        increasing, with ``z[0] == 0``; elements are non-bool int/float.
    :param c: list/tuple of sound speeds, same length as ``z``, all positive.
    :param a: launch angle in degrees, ``0 <= a < 89`` (from vertical).
    :param t: two-way travel time in seconds, strictly positive.
    :param z0: initial depth, non-negative (default 0.0).
    :return: ``(horizontal_distance, final_depth)`` rounded to 6 decimals.
    :raises TypeError: container or scalar has the wrong type.
    :raises ValueError: length, ordering, range, finiteness constraints are
        violated, or the ray suffers total internal reflection.
    """
    if not isinstance(z, (list, tuple)):
        raise TypeError("z must be a list or tuple")
    if not isinstance(c, (list, tuple)):
        raise TypeError("c must be a list or tuple")
    if len(z) != len(c):
        raise ValueError("z and c must have equal length")
    if len(z) == 0:
        raise ValueError("z and c must be non-empty")

    for index, boundary in enumerate(z):
        _check_number(boundary, f"z[{index}]")
    for index, speed in enumerate(c):
        _check_number(speed, f"c[{index}]")
    _check_number(a, "a")
    _check_number(t, "t")
    _check_number(z0, "z0")

    if z[0] != 0:
        raise ValueError("z[0] must equal 0")
    for index in range(1, len(z)):
        if z[index] <= z[index - 1]:
            raise ValueError("z must be strictly increasing")
    for speed in c:
        if speed <= 0:
            raise ValueError("all sound speeds in c must be positive")
    if not 0 <= a < 89:
        raise ValueError("a must satisfy 0 <= a < 89 degrees")
    if t <= 0:
        raise ValueError("t must be positive (two-way seconds)")
    if z0 < 0:
        raise ValueError("z0 must be non-negative")

    d = float(z0)
    x = 0.0
    r = t / 2.0
    # Largest index with z[i] <= d; a boundary depth belongs to the lower layer.
    i = bisect_right(z, d) - 1
    p = math.sin(math.radians(a)) / c[i]
    n = len(z)

    while True:
        q = p * c[i]
        if q >= 1.0:
            raise ValueError(
                "total internal reflection: ray parameter exceeds the critical value"
            )
        vx = c[i] * q
        vz = c[i] * math.sqrt(1.0 - q * q)
        # Time needed to reach the bottom of the current layer; the last
        # layer extends downward forever.
        s = (z[i + 1] - d) / vz if i + 1 < n else math.inf

        u = min(r, s)
        x += vx * u
        d += vz * u

        if r <= s:
            break
        r -= s
        i += 1

    horizontal = round(x, 6)
    depth = round(d, 6)
    if horizontal == 0.0:
        horizontal = 0.0
    if depth == 0.0:
        depth = 0.0
    return horizontal, depth
