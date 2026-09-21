"""Sound velocity profile (SVP) ray tracing.

Layered sound-speed model: layer ``i`` covers ``[z[i], z[i+1])`` with
sound speed ``c[i]``; the last layer extends downward without bound and
a boundary depth belongs to the deeper layer.
"""

from __future__ import annotations

import math

__all__ = ["trace"]


def _is_real_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _checked_profile(name: str, values: object) -> list[float]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{name} must be a list or tuple")
    if len(values) == 0:
        raise ValueError(f"{name} must be non-empty")
    for item in values:
        if not _is_real_number(item):
            raise TypeError(f"{name} elements must be non-bool int or float")
    result = list(values)
    for item in result:
        if not math.isfinite(item):
            raise ValueError(f"{name} elements must be finite")
    return result


def trace(z, c, a, t, z0=0.0):
    """Trace a ray through a layered sound velocity profile.

    ``z``/``c`` are equal-length non-empty lists/tuples of non-bool
    int/float: ``z[0] == 0``, strictly increasing, ``c`` all positive.
    ``a`` (degrees, ``0 <= a < 89``), ``t`` (two-way seconds, ``t > 0``)
    and ``z0`` (``z0 >= 0``) must share one type and all be finite.

    Returns ``(x, d)``: horizontal offset and depth after a one-way
    travel time of ``t / 2``, each rounded to 6 decimals.
    """
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

    for name, value in (("a", a), ("t", t), ("z0", z0)):
        if not _is_real_number(value):
            raise TypeError(f"{name} must be a non-bool int or float")
    if not (type(a) is type(t) is type(z0)):
        raise TypeError("a, t and z0 must have the same type")
    for name, value in (("a", a), ("t", t), ("z0", z0)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if not 0 <= a < 89:
        raise ValueError("a must satisfy 0 <= a < 89")
    if not t > 0:
        raise ValueError("t must be positive")
    if not z0 >= 0:
        raise ValueError("z0 must be >= 0")

    d = float(z0)
    x = 0.0
    r = t / 2
    n = len(zs)

    i = 0
    for k in range(n):
        if zs[k] <= d:
            i = k
        else:
            break
    p = math.sin(math.radians(a)) / cs[i]

    while True:
        speed = cs[i]
        q = p * speed
        if q >= 1:
            raise ValueError("total internal reflection")
        vx = speed * q
        vz = speed * math.sqrt(1 - q * q)
        s = math.inf if i == n - 1 else (zs[i + 1] - d) / vz
        u = r if r <= s else s
        x += vx * u
        d += vz * u
        if r <= s:
            break
        r -= s
        i += 1

    xr = round(x, 6)
    dr = round(d, 6)
    return (0.0 if xr == 0 else xr, 0.0 if dr == 0 else dr)
