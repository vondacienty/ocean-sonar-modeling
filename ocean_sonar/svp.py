"""Sound velocity profile (SVP) ray tracing.

Layered sound-speed model: layer ``i`` covers ``[z[i], z[i+1])`` with
sound speed ``c[i]``; the last layer extends downward without bound and
a boundary depth belongs to the deeper layer.
"""

from __future__ import annotations

import json
import math

__all__ = ["trace", "batch", "load_batch_request"]


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


def batch(z, c, rays, z0=0.0, limit=1000.0):
    """Trace a batch of rays and serialize the results as UTF-8 JSON bytes.

    ``rays`` must be a non-empty list/tuple whose items are two-item
    lists/tuples ``(a, t)``. Validation stops at the first error in the
    order: the ``rays`` container, its non-emptiness, each item's
    container type and length, and finally ``limit``. A non-list/tuple
    ``rays`` or item (or a non-bool int/float ``limit``) raises
    ``TypeError``; an empty ``rays``, an item whose length is not ``2``,
    or a non-finite or negative ``limit`` raises ``ValueError``.

    Afterwards :func:`trace` is called exactly once per item as
    ``trace(z, c, a, t, z0)`` in item order, so all of ``z``, ``c``,
    ``a``, ``t`` and ``z0`` validation and every trace exception apply
    here unchanged and propagated as-is. The inputs are not modified.

    With ``(x, depth)`` the values returned by :func:`trace`, the encoded
    object has top-level keys exactly in the order ``results, summary``:
    ``results`` is one ``[x, depth, within]`` array per ray, where
    ``within`` is ``x <= limit``; ``summary`` has keys exactly in the
    order ``count, pass_count, max_x, quality`` — the first two are ints,
    ``max_x`` is the float ``max(x)`` and ``quality`` is ``"pass"`` only
    when ``pass_count == count`` and ``"fail"`` otherwise.

    The JSON conventions follow :func:`ocean_sonar.crosspoint.serialize_trend`:
    UTF-8, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing newline;
    floats are rounded with ``round(float(v), 6)`` and negative zero is
    normalized to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(rays, (list, tuple)):
        raise TypeError("rays must be a list or tuple")
    if len(rays) == 0:
        raise ValueError("rays must be non-empty")
    for item in rays:
        if not isinstance(item, (list, tuple)):
            raise TypeError("rays elements must be a list or tuple")
        if len(item) != 2:
            raise ValueError("rays elements must have length 2")
    if not _is_real_number(limit):
        raise TypeError("limit must be a non-bool int or float")
    if not math.isfinite(limit) or not limit >= 0:
        raise ValueError("limit must be finite and >= 0")

    traced = [trace(z, c, a, t, z0) for a, t in rays]

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    results = [
        [rounded_float(x), rounded_float(depth), x <= limit]
        for x, depth in traced
    ]
    count = len(results)
    pass_count = sum(1 for _, _, within in results if within)
    max_x = rounded_float(max(x for x, _ in traced))
    document = {
        "results": results,
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


_BATCH_REQUEST_KEYS = ("z", "c", "rays", "z0", "limit")


def _reject_duplicate_json_pairs(pairs):
    """``object_pairs_hook`` that rejects duplicate JSON object keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(name):
    raise ValueError(f"invalid JSON constant {name!r}")


def load_batch_request(path) -> dict:
    """Load a ``svp-batch`` REQUEST JSON file.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The content must be a UTF-8 JSON object whose keys are exactly
    ``z, c, rays, z0, limit`` in that (signature) order with no missing,
    extra, duplicated or reordered keys; the ``NaN``/``Infinity``
    constants are rejected. Any decoding, parsing or structure violation
    raises ``ValueError``. The values are returned unchanged as a dict
    for :func:`batch`, whose own argument validation applies when it is
    called.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict) or list(parsed.keys()) != list(
        _BATCH_REQUEST_KEYS
    ):
        raise ValueError(
            "file must contain a JSON object with keys exactly "
            "z, c, rays, z0, limit in that order and no others"
        )
    return parsed
