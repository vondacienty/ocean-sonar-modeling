"""Tide reduction of single-beam soundings.

Observed depths are reduced to a chart datum by subtracting the tide
level linearly interpolated between the surrounding tide nodes at the
observation time.
"""

from __future__ import annotations

import math
from bisect import bisect_left

from .svp import _checked_profile, _is_real_number

__all__ = ["reduce"]


def reduce(times, depths, tide_times, levels, datum=0.0):
    """Reduce observed depths for tide.

    ``times``/``depths`` are equal-length non-empty lists/tuples;
    ``tide_times``/``levels`` are equal-length lists/tuples with at
    least two nodes. Every element and ``datum`` must be a finite
    non-bool int/float; ``depths`` elements must be ``>= 0`` and
    ``tide_times`` must be strictly increasing. Each ``times[i]`` must
    fall within the tide period ``[tide_times[0], tide_times[-1]]``.

    If an observation time hits a node exactly, that node's level is
    used; otherwise the level is linearly interpolated between the
    enclosing nodes ``(t0, h0)`` and ``(t1, h1)``::

        h = h0 + (h1 - h0) * (t - t0) / (t1 - t0)

    Validation order (first error wins): the four containers, their
    non-emptiness, the two equal-length checks and the node count, the
    tide elements and strict increase of ``tide_times``, ``datum``,
    then each observation in order. Observation errors are prefixed
    with ``"observation[i]: "``.

    Returns a tuple of floats in observation order, each value
    ``depths[i] - h + datum`` rounded to 6 decimals (negative zero
    normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(times, (list, tuple)):
        raise TypeError("times must be a list or tuple")
    if not isinstance(depths, (list, tuple)):
        raise TypeError("depths must be a list or tuple")
    if not isinstance(tide_times, (list, tuple)):
        raise TypeError("tide_times must be a list or tuple")
    if not isinstance(levels, (list, tuple)):
        raise TypeError("levels must be a list or tuple")

    if len(times) == 0:
        raise ValueError("times must be non-empty")
    if len(depths) == 0:
        raise ValueError("depths must be non-empty")
    if len(tide_times) == 0:
        raise ValueError("tide_times must be non-empty")
    if len(levels) == 0:
        raise ValueError("levels must be non-empty")

    if len(times) != len(depths):
        raise ValueError("times and depths must have equal length")
    if len(tide_times) != len(levels):
        raise ValueError("tide_times and levels must have equal length")
    if len(tide_times) < 2:
        raise ValueError("tide_times must contain at least 2 nodes")

    tt = _checked_profile("tide_times", tide_times)
    hs = _checked_profile("levels", levels)
    for k in range(len(tt) - 1):
        if not tt[k] < tt[k + 1]:
            raise ValueError("tide_times must be strictly increasing")

    if not _is_real_number(datum):
        raise TypeError("datum must be a non-bool int or float")
    if not math.isfinite(datum):
        raise ValueError("datum must be finite")

    period_start = tt[0]
    period_end = tt[-1]
    n = len(tt)

    results = []
    for i in range(len(times)):
        t = times[i]
        depth = depths[i]
        prefix = f"observation[{i}]: "
        if not _is_real_number(t):
            raise TypeError(prefix + "times elements must be non-bool int or float")
        if not _is_real_number(depth):
            raise TypeError(prefix + "depths elements must be non-bool int or float")
        if not math.isfinite(t):
            raise ValueError(prefix + "times elements must be finite")
        if not math.isfinite(depth):
            raise ValueError(prefix + "depths elements must be finite")
        if not depth >= 0:
            raise ValueError(prefix + "depths elements must be >= 0")
        if not period_start <= t <= period_end:
            raise ValueError(prefix + "times elements must be within the tide period")

        k = bisect_left(tt, t)
        if k < n and tt[k] == t:
            h = hs[k]
        else:
            t0, t1 = tt[k - 1], tt[k]
            h0, h1 = hs[k - 1], hs[k]
            h = h0 + (h1 - h0) * (t - t0) / (t1 - t0)

        value = round(depth - h + datum, 6)
        results.append(0.0 if value == 0 else value)
    return tuple(results)
