"""Single-beam echo sounding batch correction.

Each observation pairs a beam angle with a two-way travel time; every
ray is traced through the same layered sound-speed model (see
:mod:`ocean_sonar.svp`) and the per-observation results are returned
in input order.
"""

from __future__ import annotations

import math

from .svp import trace

__all__ = ["correct"]


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


def correct(z, c, angles, times, z0=0.0):
    """Batch-correct single-beam observations through an SVP.

    ``angles``/``times`` are equal-length non-empty lists/tuples whose
    elements are finite non-bool int/float. ``z``/``c`` follow the same
    rules as :func:`ocean_sonar.svp.trace`: equal-length non-empty
    lists/tuples of finite non-bool int/float, ``z[0] == 0``, strictly
    increasing, ``c`` all positive. ``z0`` is a finite non-bool
    int/float with ``z0 >= 0``. Each observation ``i`` must satisfy
    ``type(angles[i]) is type(times[i]) is type(z0)``,
    ``0 <= angles[i] < 89`` and ``times[i] > 0``.

    Returns a tuple of ``(x, d)`` pairs in input order, one per
    observation, each value a float rounded to 6 decimals with
    negative zero normalised to ``0.0``. Inputs are not modified.

    Observation errors (including total internal reflection reported
    by :func:`ocean_sonar.svp.trace`) are raised with messages
    prefixed ``observation[i]: ``.
    """
    for name, values in (("angles", angles), ("times", times)):
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"{name} must be a list or tuple")
    for name, values in (("angles", angles), ("times", times)):
        if len(values) == 0:
            raise ValueError(f"{name} must be non-empty")
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
        prefix = f"observation[{i}]: "
        a = angles[i]
        t = times[i]
        for name, value in (("angles[i]", a), ("times[i]", t)):
            if not _is_real_number(value):
                raise TypeError(f"{prefix}{name} must be a non-bool int or float")
        if not (type(a) is type(t) is type(z0)):
            raise TypeError(f"{prefix}angles[i], times[i] and z0 must have the same type")
        for name, value in (("angles[i]", a), ("times[i]", t)):
            if not math.isfinite(value):
                raise ValueError(f"{prefix}{name} must be finite")
        if not 0 <= a < 89:
            raise ValueError(f"{prefix}angles[i] must satisfy 0 <= angles[i] < 89")
        if not t > 0:
            raise ValueError(f"{prefix}times[i] must be positive")
        try:
            x, d = trace(z, c, a, t, z0)
        except ValueError as exc:
            raise ValueError(f"{prefix}{exc}") from exc
        xr = round(float(x), 6)
        dr = round(float(d), 6)
        results.append((0.0 if xr == 0 else xr, 0.0 if dr == 0 else dr))
    return tuple(results)
