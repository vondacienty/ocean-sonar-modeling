"""MAD-based outlier detection for corrected depth soundings.

Each depth is scored against the sample median with the median
absolute deviation (MAD): a depth is flagged as an outlier when its
robust score ``0.67448975 * abs(d - median) / MAD`` strictly exceeds
the threshold.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["detect"]

_CONSISTENCY_CONSTANT = 0.67448975


def _median(ordered):
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _rounded(value):
    result = round(float(value), 6)
    return 0.0 if result == 0 else result


def detect(depths, threshold=3.5):
    """Flag outlier depths with a MAD robust-score test.

    ``depths`` is a non-empty list/tuple with at least three elements,
    each a finite non-bool int/float ``>= 0``; ``threshold`` is a
    finite non-bool int/float ``> 0``. The depths are sorted to find
    the median ``m`` (for an even count, the mean of the two middle
    values) and the median absolute deviation ``MAD``. When
    ``MAD == 0`` exactly the depths unequal to ``m`` are flagged;
    otherwise a depth is flagged when
    ``0.67448975 * abs(d - m) / MAD > threshold`` (equality does not
    flag).

    Returns a tuple in input order of ``(is_outlier, score, depth)``
    triples: ``is_outlier`` is a bool; ``score`` and ``depth`` are
    ``round(float(v), 6)`` floats with negative zero normalized to
    ``0.0``. The score is the formula's left-hand side, except when
    ``MAD == 0`` where unflagged depths score ``0.0`` and flagged
    depths score ``round(float(threshold + 1), 6)``. The input is not
    modified.

    Validation order (first error wins): the ``depths`` container, its
    length, then per element its type, finiteness and non-negativity,
    then ``threshold``. A bad container, element or threshold type
    raises TypeError; fewer than three elements, a non-finite or
    negative depth, or a non-finite or non-positive threshold raises
    ValueError.
    """
    if not isinstance(depths, (list, tuple)):
        raise TypeError("depths must be a list or tuple")
    if len(depths) < 3:
        raise ValueError("depths must have at least 3 elements")
    for item in depths:
        if not _is_real_number(item):
            raise TypeError("depths elements must be non-bool int or float")
        if not math.isfinite(item):
            raise ValueError("depths elements must be finite")
        if not item >= 0:
            raise ValueError("depths elements must be >= 0")
    if not _is_real_number(threshold):
        raise TypeError("threshold must be a non-bool int or float")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if not threshold > 0:
        raise ValueError("threshold must be positive")

    ordered = sorted(float(d) for d in depths)
    m = _median(ordered)
    mad = _median(sorted(abs(d - m) for d in ordered))

    results = []
    if mad == 0:
        flagged_score = _rounded(threshold + 1)
        for d in depths:
            flagged = d != m
            results.append((flagged, flagged_score if flagged else 0.0, _rounded(d)))
    else:
        for d in depths:
            score = _CONSISTENCY_CONSTANT * abs(d - m) / mad
            results.append((score > threshold, _rounded(score), _rounded(d)))
    return tuple(results)
