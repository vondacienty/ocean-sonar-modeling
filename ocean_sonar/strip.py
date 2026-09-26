"""Merging of overlapping bathymetric strips.

Adjacent survey strips overlap spatially. The strips are fused one by
one: every point of a new strip is matched against the points already
accumulated, and the strip's depth offset is estimated as the median
of the matched ``new depth - old depth`` differences. All depths of the
strip are shifted by that offset before the strip is accumulated.
"""

from __future__ import annotations

import json
import math

from .svp import _is_real_number

__all__ = ["merge", "batch"]

_FIELDS = ("x", "y", "d")


def _median(sorted_values):
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2


def merge(strips, tolerance=1.0):
    """Merge overlapping strips with a median depth-offset correction.

    ``strips`` is a list/tuple of at least two items; each item is a
    non-empty list/tuple of points and every point is a three-element
    list/tuple ``(x, y, d)``. Each value must be a finite non-bool
    int/float and ``d >= 0``. ``tolerance`` must be a finite non-bool
    int/float ``> 0``.

    The first strip is accumulated unchanged. Each later strip is
    processed in turn: for each of its points the previously
    accumulated points within two-dimensional Euclidean distance
    ``tolerance`` (boundary included) are considered, the nearest one is
    chosen and on a distance tie the earliest point in accumulation
    order wins; an accumulated point may be reused by several new
    points. At least two points of the strip must match, otherwise
    ``ValueError`` is raised. The matched ``new d - old d`` differences
    are sorted and their median ``b`` taken (for an even count the mean
    of the two middle values); every depth of the strip is reduced by
    ``b`` and the strip is then accumulated. Corrected depths are never
    rounded between strips.

    Validation order (first error wins): the ``strips`` container, its
    minimum length, then each strip in index order (item container,
    non-emptiness, points in index order with ``x``, ``y``, ``d``
    checked in that order), then ``tolerance`` (type, finiteness,
    positivity). Strip errors are prefixed with ``"strip[i]: "`` and
    point errors with ``"strip[i]: point[j]: "``.

    Returns a flat tuple in strip/point input order; each item is a
    strictly-float ``(x, y, d)`` triple rounded to 6 decimals (negative
    zero normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(strips, (list, tuple)):
        raise TypeError("strips must be a list or tuple")
    if len(strips) < 2:
        raise ValueError("strips must have at least 2 elements")

    for i in range(len(strips)):
        strip = strips[i]
        strip_prefix = f"strip[{i}]: "
        if not isinstance(strip, (list, tuple)):
            raise TypeError(strip_prefix + "must be a list or tuple")
        if len(strip) == 0:
            raise ValueError(strip_prefix + "must be non-empty")
        for j in range(len(strip)):
            point = strip[j]
            prefix = strip_prefix + f"point[{j}]: "
            if not isinstance(point, (list, tuple)):
                raise TypeError(prefix + "must be a list or tuple")
            if len(point) != 3:
                raise ValueError(prefix + "must have 3 elements")
            for name, value in zip(_FIELDS, point):
                if not _is_real_number(value):
                    raise TypeError(prefix + f"{name} must be a non-bool int or float")
                if not math.isfinite(value):
                    raise ValueError(prefix + f"{name} must be finite")
            if not point[2] >= 0:
                raise ValueError(prefix + "d must be >= 0")

    if not _is_real_number(tolerance):
        raise TypeError("tolerance must be a non-bool int or float")
    if not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite")
    if not tolerance > 0:
        raise ValueError("tolerance must be > 0")

    cloud = [(x, y, d) for x, y, d in strips[0]]
    merged = list(cloud)

    for i in range(1, len(strips)):
        strip = strips[i]
        differences = []
        for x, y, d in strip:
            best_depth = None
            best_distance = tolerance
            for ax, ay, old_d in cloud:
                distance = math.hypot(x - ax, y - ay)
                if distance <= tolerance and (
                    best_depth is None or distance < best_distance
                ):
                    best_depth = old_d
                    best_distance = distance
            if best_depth is not None:
                differences.append(d - best_depth)

        if len(differences) < 2:
            raise ValueError(f"strip[{i}]: at least 2 matches required")

        b = _median(sorted(differences))
        corrected = [(x, y, d - b) for x, y, d in strip]
        cloud.extend(corrected)
        merged.extend(corrected)

    results = []
    for x, y, d in merged:
        values = []
        for value in (x, y, d):
            value = round(float(value), 6)
            values.append(0.0 if value == 0 else value)
        results.append(tuple(values))
    return tuple(results)


def batch(strips, tolerance=1.0, max_adjustment=1.0) -> bytes:
    """Merge a batch of strips and serialize the results as JSON bytes.

    Calls :func:`merge` exactly once with ``(strips, tolerance)`` — its
    validation and exceptions apply unchanged and the input is not
    modified. ``max_adjustment`` is validated after the merge: it must
    be a non-bool int/float, finite when it is a float, and ``>= 0``. A
    bool or non-number raises ``TypeError`` and a non-finite float or a
    negative value raises ``ValueError``.

    With ``M`` the tuple returned by :func:`merge`, ``M`` is split back
    into strips using the original strip lengths. For each strip the
    mean adjustment is

        a = round(float(fsum(original d - merged d) / point count), 6)

    (negative zero normalized to ``0.0``) and the strip passes when
    ``abs(a) <= max_adjustment``.

    The returned document has top-level keys exactly in the order
    ``results, summary``: ``results`` is an array in the order of ``M``
    of the ``[x, y, d]`` arrays taken unchanged from each ``M[i]``;
    ``summary`` has keys exactly in the order ``strip_count,
    point_count, pass_count, max_abs_adjustment, quality`` where
    ``strip_count``, ``point_count`` and ``pass_count`` are the ints
    ``len(strips)``, ``len(M)`` and the number of passing strips,
    ``max_abs_adjustment`` is the float ``max(abs(a))`` and ``quality``
    is ``"pass"`` only when every strip passes, otherwise ``"fail"``.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``outlier.batch``. Any JSON or
    UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    merged = merge(strips, tolerance)

    if not _is_real_number(max_adjustment):
        raise TypeError("max_adjustment must be a non-bool int or float")
    if isinstance(max_adjustment, float) and not math.isfinite(max_adjustment):
        raise ValueError("max_adjustment must be finite")
    if not max_adjustment >= 0:
        raise ValueError("max_adjustment must be >= 0")

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    adjustments = []
    offset = 0
    for strip in strips:
        count = len(strip)
        segment = merged[offset : offset + count]
        offset += count
        a = rounded_float(
            math.fsum(point[2] - merged_point[2]
                      for point, merged_point in zip(strip, segment)) / count
        )
        adjustments.append(a)

    pass_count = int(
        sum(1 for a in adjustments if abs(a) <= max_adjustment)
    )
    document = {
        "results": [[x, y, d] for x, y, d in merged],
        "summary": {
            "strip_count": int(len(strips)),
            "point_count": int(len(merged)),
            "pass_count": pass_count,
            "max_abs_adjustment": rounded_float(
                max(abs(a) for a in adjustments)
            ),
            "quality": "pass" if pass_count == len(strips) else "fail",
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
