"""Strip merging by median depth-offset alignment.

Survey strips are aligned vertically one after another: each strip
after the first is matched point-wise against the already accumulated
points, and the median matched depth difference is subtracted from the
whole strip before it is appended.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["merge"]


def _median(sorted_values):
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2


def _rounded(value):
    result = round(float(value), 6)
    return 0.0 if result == 0 else result


def merge(strips, tolerance=1.0):
    """Merge survey strips by aligning their median depth offsets.

    ``strips`` is a list/tuple of at least two strips; each strip is a
    non-empty list/tuple of points and each point is a 3-element
    list/tuple ``(x, y, d)`` of finite non-bool int/float values with
    ``d >= 0``. ``tolerance`` must be a finite non-bool int/float
    ``> 0``.

    The first strip is accumulated unchanged. For each later strip,
    every point is matched against the points accumulated so far:
    candidates are those within 2D Euclidean distance ``<= tolerance``,
    the nearest wins, ties go to the earliest accumulated point, and an
    accumulated point may be matched more than once. Fewer than two
    matched pairs raises ``ValueError``. The matched ``new d - old d``
    differences are sorted and their median ``b`` (for an even count,
    the mean of the two middle values) is subtracted from every depth
    of the strip before it is accumulated. Corrected depths are kept
    unrounded throughout.

    Validation order (first error wins): the ``strips`` container, its
    length, then each strip in order (container, non-emptiness, each
    point in order: container, length, each value's type, finiteness
    and ``d >= 0``), then ``tolerance`` (type, finiteness, positivity).
    Strip errors carry a ``strip[i]: `` prefix and point errors a
    ``strip[i]: point[j]: `` prefix.

    Returns a tuple flattened in strip/point input order; each item is
    strictly an ``(x, y, d)`` triple of floats rounded to 6 decimals
    (negative zero normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(strips, (list, tuple)):
        raise TypeError("strips must be a list or tuple")
    if len(strips) < 2:
        raise ValueError("strips must have at least 2 elements")

    for i, strip in enumerate(strips):
        if not isinstance(strip, (list, tuple)):
            raise TypeError(f"strip[{i}]: must be a list or tuple")
        if len(strip) == 0:
            raise ValueError(f"strip[{i}]: must be non-empty")
        for j, point in enumerate(strip):
            prefix = f"strip[{i}]: point[{j}]: "
            if not isinstance(point, (list, tuple)):
                raise TypeError(prefix + "must be a list or tuple")
            if len(point) != 3:
                raise ValueError(prefix + "must have exactly 3 elements")
            for k, value in enumerate(point):
                if not _is_real_number(value):
                    raise TypeError(prefix + "values must be non-bool int or float")
                if not math.isfinite(value):
                    raise ValueError(prefix + "values must be finite")
                if k == 2 and not value >= 0:
                    raise ValueError(prefix + "d must be >= 0")

    if not _is_real_number(tolerance):
        raise TypeError("tolerance must be a non-bool int or float")
    if not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite")
    if not tolerance > 0:
        raise ValueError("tolerance must be > 0")

    accumulated = []
    for i, strip in enumerate(strips):
        points = [(float(x), float(y), float(d)) for x, y, d in strip]
        if i == 0:
            corrected = points
        else:
            diffs = []
            for x, y, d in points:
                best_distance = None
                best_depth = None
                for ax, ay, ad in accumulated:
                    distance = math.hypot(x - ax, y - ay)
                    if distance <= tolerance and (
                        best_distance is None or distance < best_distance
                    ):
                        best_distance = distance
                        best_depth = ad
                if best_distance is not None:
                    diffs.append(d - best_depth)
            if len(diffs) < 2:
                raise ValueError(
                    f"strip[{i}]: fewer than 2 points matched within tolerance"
                )
            offset = _median(sorted(diffs))
            corrected = [(x, y, d - offset) for x, y, d in points]
        accumulated.extend(corrected)

    return tuple(
        (_rounded(x), _rounded(y), _rounded(d)) for x, y, d in accumulated
    )
