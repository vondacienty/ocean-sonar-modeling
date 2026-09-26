"""Tide reduction of single-beam soundings.

Observed depths are reduced to chart datum by subtracting the tide
level interpolated linearly between the surrounding tide nodes:
``reduced = depth - h + datum``.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left

from .svp import _is_real_number

__all__ = ["reduce", "batch"]


def reduce(times, depths, tide_times, levels, datum=0.0):
    """Reduce observed depths with a linear tide interpolation.

    ``times``/``depths`` are equal-length non-empty lists/tuples and
    ``tide_times``/``levels`` are equal-length lists/tuples with at
    least two nodes. Every element and ``datum`` must be a finite
    non-bool int/float; ``depths`` elements must be ``>= 0`` and
    ``tide_times`` strictly increasing. Each observation time must lie
    within the tide time range; a time exactly on a node takes that
    node's level, otherwise the level is linearly interpolated between
    the surrounding nodes ``(t0, h0)`` and ``(t1, h1)``::

        h = h0 + (h1 - h0) * (t - t0) / (t1 - t0)
        reduced = depths[i] - h + datum

    Validation order (first error wins): the four containers, their
    non-emptiness, the equal lengths and the minimum node count, the
    tide elements and their strict increase, then ``datum``, then each
    observation in order (time, depth, time range). Observation errors
    are prefixed with ``"observation[i]: "``.

    Returns a tuple of floats in observation order, each rounded to 6
    decimals (negative zero normalized to ``0.0``). Inputs are not
    modified.
    """
    for name, values in (
        ("times", times),
        ("depths", depths),
        ("tide_times", tide_times),
        ("levels", levels),
    ):
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"{name} must be a list or tuple")

    for name, values in (
        ("times", times),
        ("depths", depths),
        ("tide_times", tide_times),
        ("levels", levels),
    ):
        if len(values) == 0:
            raise ValueError(f"{name} must be non-empty")

    if len(times) != len(depths):
        raise ValueError("times and depths must have equal length")
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

    start = tide_times[0]
    end = tide_times[-1]
    results = []
    for i in range(len(times)):
        t = times[i]
        depth = depths[i]
        prefix = f"observation[{i}]: "
        if not _is_real_number(t):
            raise TypeError(prefix + "times elements must be non-bool int or float")
        if not math.isfinite(t):
            raise ValueError(prefix + "time must be finite")
        if not _is_real_number(depth):
            raise TypeError(prefix + "depths elements must be non-bool int or float")
        if not math.isfinite(depth):
            raise ValueError(prefix + "depth must be finite")
        if not depth >= 0:
            raise ValueError(prefix + "depth must be >= 0")
        if not start <= t <= end:
            raise ValueError(prefix + "time must be within the tide time range")

        k = bisect_left(tide_times, t)
        if k < len(tide_times) and tide_times[k] == t:
            h = levels[k]
        else:
            t0, t1 = tide_times[k - 1], tide_times[k]
            h0, h1 = levels[k - 1], levels[k]
            h = h0 + (h1 - h0) * (t - t0) / (t1 - t0)

        v = round(depth - h + datum, 6)
        results.append(0.0 if v == 0 else float(v))
    return tuple(results)


def batch(times, depths, tide_times, levels, datum=0.0, limit=1.0) -> bytes:
    """Reduce a batch of soundings and serialize the results as JSON bytes.

    Calls :func:`reduce` exactly once with ``(times, depths, tide_times,
    levels, datum)`` — its validation and exceptions apply unchanged and
    the inputs are not modified. ``limit`` is then validated: it must be
    a finite non-bool int/float with ``limit >= 0`` — a bool or
    non-number raises ``TypeError`` and a non-finite or negative value
    raises ``ValueError``.

    With ``R`` the :func:`reduce` result, each observation ``i`` yields
    the adjustment ``a = round(float(R[i] - depths[i]), 6)`` (negative
    zero normalized to ``0.0``) and the bool ``w = abs(a) <= limit``.

    The returned document has top-level keys exactly in the order
    ``results, summary``: ``results`` is an array of ``[R[i], a, w]``
    triples in input order; ``summary`` has keys exactly in the order
    ``count, pass_count, max_abs_adjustment, quality`` where ``count``
    and ``pass_count`` are ints, ``max_abs_adjustment`` is
    ``round(float(max(abs(a))), 6)`` and ``quality`` is ``"pass"`` only
    when every ``w`` is true, otherwise ``"fail"``.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``serialize_trend``. Floats are
    first rounded with ``round(float(v), 6)`` and negative zero is
    normalized to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    reduced = reduce(times, depths, tide_times, levels, datum)

    if not _is_real_number(limit):
        raise TypeError("limit must be a non-bool int or float")
    if not math.isfinite(limit):
        raise ValueError("limit must be finite")
    if not limit >= 0:
        raise ValueError("limit must be >= 0")

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    adjustments = [rounded_float(reduced[i] - depths[i]) for i in range(len(reduced))]
    withins = [abs(a) <= limit for a in adjustments]

    count = int(len(adjustments))
    pass_count = int(sum(1 for w in withins if w))
    max_abs_adjustment = rounded_float(max(abs(a) for a in adjustments))
    document = {
        "results": [
            [rounded_float(reduced[i]), adjustments[i], withins[i]]
            for i in range(len(adjustments))
        ],
        "summary": {
            "count": count,
            "pass_count": pass_count,
            "max_abs_adjustment": max_abs_adjustment,
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
