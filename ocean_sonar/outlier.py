"""Outlier detection for corrected single-beam depths.

A robust Z-score is built from the median and the median absolute
deviation (MAD); depths whose scaled deviation exceeds the threshold
are flagged as gross errors.
"""

from __future__ import annotations

import json
import math

from .svp import _is_real_number

__all__ = ["detect", "batch"]

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


def batch(depths, threshold=3.5, max_outlier_ratio=0.1) -> bytes:
    """Detect outliers in a batch of depths and serialize the results as JSON bytes.

    Calls :func:`detect` exactly once with ``(depths, threshold)`` — its
    validation and exceptions apply unchanged and the input is not
    modified. ``max_outlier_ratio`` is validated after the detection: it
    must be a non-bool int/float in ``[0, 1]``; finiteness is checked
    only for a float. A bool or non-number raises ``TypeError`` and a
    non-finite float or a value outside ``[0, 1]`` raises ``ValueError``.

    With ``R`` the tuple returned by :func:`detect`, ``n = len(R)`` and
    ``k`` the number of flagged items, the returned document has
    top-level keys exactly in the order ``results, summary``:
    ``results`` is an array in ``R`` order of ``[is_outlier, score,
    depth]`` arrays taken directly from ``R[i]``; ``summary`` has keys
    exactly in the order ``count, outlier_count, outlier_ratio,
    max_score, quality`` where ``count`` is ``n`` and ``outlier_count``
    is ``k`` (both ints), ``outlier_ratio`` is
    ``round(float(k / n), 6)``, ``max_score`` is
    ``round(float(max(score)), 6)`` (both floats with negative zero
    normalized to ``0.0``) and ``quality`` is ``"pass"`` only when
    ``k / n <= max_outlier_ratio``, otherwise ``"fail"``.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``attitude.batch``. Any JSON or
    UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    detected = detect(depths, threshold)

    if not _is_real_number(max_outlier_ratio):
        raise TypeError("max_outlier_ratio must be a non-bool int or float")
    if isinstance(max_outlier_ratio, float) and not math.isfinite(
        max_outlier_ratio
    ):
        raise ValueError("max_outlier_ratio must be finite")
    if not 0 <= max_outlier_ratio <= 1:
        raise ValueError("max_outlier_ratio must be in [0, 1]")

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    n = int(len(detected))
    k = int(sum(1 for item in detected if item[0]))
    outlier_ratio = rounded_float(k / n)
    max_score = rounded_float(max(item[1] for item in detected))
    document = {
        "results": [
            [is_outlier, score, depth] for is_outlier, score, depth in detected
        ],
        "summary": {
            "count": n,
            "outlier_count": k,
            "outlier_ratio": outlier_ratio,
            "max_score": max_score,
            "quality": "pass" if k / n <= max_outlier_ratio else "fail",
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
