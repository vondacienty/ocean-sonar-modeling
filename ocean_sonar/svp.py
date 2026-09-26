"""Sound velocity profile (SVP) ray tracing.

Layered sound-speed model: layer ``i`` covers ``[z[i], z[i+1])`` with
sound speed ``c[i]``; the last layer extends downward without bound and
a boundary depth belongs to the deeper layer.
"""

from __future__ import annotations

import json
import math

__all__ = ["trace", "batch"]


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


def batch(z, c, rays, z0=0.0, limit=1000.0) -> bytes:
    """Trace a batch of rays and serialize the results as JSON bytes.

    ``rays`` must be a non-empty list/tuple of two-item lists/tuples
    ``(a, t)``; a non-list/tuple ``rays`` or item raises ``TypeError``
    and an empty ``rays`` or a wrong-length item raises ``ValueError``.
    ``limit`` must be a finite non-bool int/float with ``limit >= 0``:
    a bool or non-number raises ``TypeError`` and a non-finite or
    negative value raises ``ValueError``. The ``rays`` container, its
    non-emptiness, the item containers/lengths and ``limit`` are
    validated in this order before any ray is traced.

    Each item is then traced in order with exactly one call to
    ``trace(z, c, a, t, z0)`` — its parameter validation and exceptions
    apply unchanged and the inputs are not modified.

    The returned document has top-level keys exactly in the order
    ``results, summary``: ``results`` is an array of ``[x, depth,
    within]`` triples with ``x``/``depth`` taken from the ``trace``
    result and ``within`` the bool ``x <= limit``; ``summary`` has keys
    exactly in the order ``count, pass_count, max_x, quality`` where
    ``count`` and ``pass_count`` are ints, ``max_x`` is the float
    ``max(x)`` and ``quality`` is ``"pass"`` only when
    ``pass_count == count``, otherwise ``"fail"``.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``serialize_trend``. Floats are
    first rounded with ``round(float(v), 6)`` and negative zero is
    normalized to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(rays, (list, tuple)):
        raise TypeError("rays must be a list or tuple")
    if len(rays) == 0:
        raise ValueError("rays must be non-empty")
    for ray in rays:
        if not isinstance(ray, (list, tuple)):
            raise TypeError("rays items must be lists or tuples")
        if len(ray) != 2:
            raise ValueError("rays items must have length 2")
    if not _is_real_number(limit):
        raise TypeError("limit must be a non-bool int or float")
    if not math.isfinite(limit):
        raise ValueError("limit must be finite")
    if not limit >= 0:
        raise ValueError("limit must be >= 0")

    results = []
    for ray in rays:
        a, t = ray
        x, depth = trace(z, c, a, t, z0)
        results.append((x, depth, x <= limit))

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    count = int(len(results))
    pass_count = int(sum(1 for _, _, within in results if within))
    max_x = rounded_float(max(x for x, _, _ in results))
    document = {
        "results": [
            [rounded_float(x), rounded_float(depth), within]
            for x, depth, within in results
        ],
        "summary": {
            "count": count,
            "pass_count": pass_count,
            "max_x": max_x,
            "quality": "pass" if pass_count == count else "fail",
        },
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"batch: could not be serialized to JSON: {exc}") from exc
