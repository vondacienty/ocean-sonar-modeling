"""Outlier detection for corrected single-beam depths.

A robust Z-score is built from the median and the median absolute
deviation (MAD); depths whose scaled deviation exceeds the threshold
are flagged as gross errors.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["detect"]

_SCALE = 0.67448975


def _median(sorted_values):
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2


def detect(depths, threshold=3.5):
    """Detect gross errors in corrected depths with a MAD Z-score.

    ``depths`` is a list/tuple of at least three finite non-bool
    int/float values, each ``>= 0``; ``threshold`` must be a finite
    non-bool int/float ``> 0``. The depths are sorted ascending and
    their median ``m`` is taken (for an even count, the mean of the two
    middle values); the MAD is the median of ``abs(d - m)``.

    When ``MAD == 0`` only the values not equal to ``m`` are flagged.
    Otherwise a value is flagged when

        0.67448975 * abs(d - m) / MAD > threshold

    (strict inequality: an equal score is not flagged).

    Validation order (first error wins): the ``depths`` container, its
    length, each element in order (type, finiteness, non-negativity),
    then ``threshold`` (type, finiteness, positivity).

    Returns a tuple in input order; each item is strictly
    ``(is_outlier, score, depth)`` where ``is_outlier`` is a bool and
    both ``score`` and ``depth`` are floats rounded to 6 decimals
    (negative zero normalized to ``0.0``). The score is the left-hand
    side of the inequality above; with ``MAD == 0`` unflagged items
    score ``0.0`` and flagged items score
    ``round(float(threshold + 1), 6)``. Inputs are not modified.
    """
    if not isinstance(depths, (list, tuple)):
        raise TypeError("depths must be a list or tuple")
    if len(depths) < 3:
        raise ValueError("depths must have at least 3 elements")

    for i, depth in enumerate(depths):
        if not _is_real_number(depth):
            raise TypeError(f"depths[{i}] must be a non-bool int or float")
        if not math.isfinite(depth):
            raise ValueError(f"depths[{i}] must be finite")
        if not depth >= 0:
            raise ValueError(f"depths[{i}] must be >= 0")

    if not _is_real_number(threshold):
        raise TypeError("threshold must be a non-bool int or float")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if not threshold > 0:
        raise ValueError("threshold must be > 0")

    ordered = sorted(depths)
    m = _median(ordered)
    mad = _median(sorted(abs(depth - m) for depth in ordered))
    fallback = round(float(threshold + 1), 6)

    results = []
    for depth in depths:
        if mad == 0:
            is_outlier = depth != m
            score = fallback if is_outlier else 0.0
        else:
            raw = _SCALE * abs(depth - m) / mad
            is_outlier = raw > threshold
            score = round(float(raw), 6)
        if score == 0:
            score = 0.0
        rounded_depth = round(float(depth), 6)
        if rounded_depth == 0:
            rounded_depth = 0.0
        results.append((bool(is_outlier), score, rounded_depth))
    return tuple(results)
