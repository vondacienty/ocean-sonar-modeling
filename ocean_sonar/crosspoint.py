"""Crosspoint accuracy evaluation for overlapping survey lines.

Each crosspoint pairs the two depths observed at the same location;
the depth difference ``r = d1 - d2`` is summarized by its mean bias,
RMSE and maximum absolute value, and the differences within the
tolerance are counted.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["audit", "evaluate", "pair", "report"]

_FIELDS = ("x", "y", "d1", "d2")
_POINT_FIELDS = ("x", "y", "d")


def _validate_crossings(crossings):
    """Validate the ``crossings`` argument per :func:`evaluate`'s contract."""
    if not isinstance(crossings, (list, tuple)):
        raise TypeError("crossings must be a list or tuple")
    if len(crossings) == 0:
        raise ValueError("crossings must be non-empty")

    for i in range(len(crossings)):
        point = crossings[i]
        prefix = f"crossings[{i}]: "
        if not isinstance(point, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(point) != 4:
            raise ValueError(prefix + "must have 4 elements")
        for name, value in zip(_FIELDS, point):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
        if not point[2] >= 0:
            raise ValueError(prefix + "d1 must be >= 0")
        if not point[3] >= 0:
            raise ValueError(prefix + "d2 must be >= 0")


def evaluate(crossings, tolerance=0.5):
    """Evaluate crosspoint depth differences.

    ``crossings`` is a non-empty list/tuple; each item is a
    four-element list/tuple ``(x, y, d1, d2)`` whose fields are finite
    non-bool int/float values, with ``d1, d2 >= 0``. ``tolerance`` must
    be a finite non-bool int/float ``> 0``.

    With ``r = d1 - d2`` and ``n`` the number of crosspoints, the
    statistics are, in order, ``bias = fsum(r) / n``,
    ``rmse = sqrt(fsum(r**2) / n)`` and ``max_abs = max(abs(r))``; a
    crosspoint is within tolerance when ``abs(r) <= tolerance``.

    Validation order (first error wins): the ``crossings`` container,
    its non-emptiness, each item in index order (item container,
    length, fields), then ``tolerance`` (type, finiteness, positivity).
    Item errors are prefixed with ``"crossings[i]: "``.

    Returns a dict with keys in the order
    ``count, bias, rmse, max_abs, within_tolerance, quality``; ``count``
    and ``within_tolerance`` are ints and ``bias``/``rmse``/``max_abs``
    are floats rounded to 6 decimals (negative zero normalized to
    ``0.0``). ``quality`` is ``"pass"`` when every crosspoint is within
    the tolerance and ``"fail"`` otherwise. Inputs are not modified.
    """
    _validate_crossings(crossings)

    if not _is_real_number(tolerance):
        raise TypeError("tolerance must be a non-bool int or float")
    if not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite")
    if not tolerance > 0:
        raise ValueError("tolerance must be > 0")

    differences = [d1 - d2 for x, y, d1, d2 in crossings]
    n = len(differences)

    bias = math.fsum(differences) / n
    rmse = math.sqrt(math.fsum(r * r for r in differences) / n)
    max_abs = max(abs(r) for r in differences)
    within_tolerance = 0
    for r in differences:
        if abs(r) <= tolerance:
            within_tolerance += 1

    values = {
        "count": n,
        "bias": bias,
        "rmse": rmse,
        "max_abs": max_abs,
        "within_tolerance": within_tolerance,
    }
    result = {"count": int(n)}
    for name in ("bias", "rmse", "max_abs"):
        value = round(float(values[name]), 6)
        result[name] = 0.0 if value == 0 else value
    result["within_tolerance"] = int(within_tolerance)
    result["quality"] = "pass" if within_tolerance == n else "fail"
    return result


def report(crossings, tolerance=0.5):
    """Build a crosspoint report extending :func:`evaluate` with ratios.

    Calls :func:`evaluate` exactly once with ``crossings`` and
    ``tolerance``, so its validation, exceptions (propagated
    unchanged) and ``"crossings[i]: "`` index prefixes/order all apply
    here as well. Inputs are not modified.

    With ``r = d1 - d2`` and ``n`` the number of crosspoints, the
    population standard deviation is
    ``sigma = sqrt(fsum((r - mu)**2) / n)`` where
    ``mu = fsum(r) / n``, and the within-tolerance ratio is
    ``within_tolerance / n``; both use unrounded values.

    Returns a dict with keys in the order
    ``count, bias, rmse, max_abs, within_tolerance, within_ratio,
    stdev, quality``. The first five keys and ``quality`` are taken
    from the :func:`evaluate` result unchanged (``count`` and
    ``within_tolerance`` ints, the statistics rounded floats).
    ``within_ratio`` is ``round(float(ratio), 6)`` and ``stdev`` is
    ``round(float(sigma), 6)``, both floats with negative zero
    normalized to ``0.0``; ``ratio`` lies in ``[0, 1]``.
    """
    evaluated = evaluate(crossings, tolerance)

    differences = [d1 - d2 for x, y, d1, d2 in crossings]
    n = len(differences)
    mean = math.fsum(differences) / n
    stdev = math.sqrt(math.fsum((r - mean) ** 2 for r in differences) / n)
    ratio = evaluated["within_tolerance"] / n

    stdev = round(float(stdev), 6)
    ratio = round(float(ratio), 6)
    if stdev == 0:
        stdev = 0.0
    if ratio == 0:
        ratio = 0.0

    return {
        "count": evaluated["count"],
        "bias": evaluated["bias"],
        "rmse": evaluated["rmse"],
        "max_abs": evaluated["max_abs"],
        "within_tolerance": evaluated["within_tolerance"],
        "within_ratio": ratio,
        "stdev": stdev,
        "quality": evaluated["quality"],
    }


def audit(crossings, tolerances):
    """Run :func:`report` for several tolerances over one crossing set.

    ``crossings`` is validated with the full contract of
    :func:`evaluate` first (container, non-emptiness and every item in
    index order); ``tolerances`` must then be a non-empty list/tuple
    whose items, checked in input order, are finite non-bool
    int/float values ``> 0``. Container or element type errors raise
    ``TypeError``; an empty container, non-finite or non-positive
    element raises ``ValueError``. Tolerance element errors are
    prefixed with ``"tolerances[i]: "`` and validation stops at the
    first error.

    For every tolerance, :func:`report` is called exactly once as
    ``report(crossings, tolerance)`` in input order — tolerances are
    not sorted or de-duplicated and the inputs are not modified; any
    exception raised by :func:`report` propagates unchanged.

    Returns a tuple with the same length as ``tolerances``; each item
    is directly the dict returned by the corresponding :func:`report`
    call, with keys in the order
    ``count, bias, rmse, max_abs, within_tolerance, within_ratio,
    stdev, quality`` and the same rounding (6 decimals, negative zero
    normalized to ``0.0``) as :func:`report`.
    """
    _validate_crossings(crossings)

    if not isinstance(tolerances, (list, tuple)):
        raise TypeError("tolerances must be a list or tuple")
    if len(tolerances) == 0:
        raise ValueError("tolerances must be non-empty")

    for i in range(len(tolerances)):
        tolerance = tolerances[i]
        prefix = f"tolerances[{i}]: "
        if not _is_real_number(tolerance):
            raise TypeError(prefix + "must be a non-bool int or float")
        if not math.isfinite(tolerance):
            raise ValueError(prefix + "must be finite")
        if not tolerance > 0:
            raise ValueError(prefix + "must be > 0")

    return tuple(report(crossings, tolerance) for tolerance in tolerances)


def pair(first, second, tolerance=1.0):
    """Pair points from two surveys at coincident locations.

    ``first`` and ``second`` are non-empty lists/tuples of points; each
    point is a three-element list/tuple ``(x, y, d)`` whose fields are
    finite non-bool int/float values, with ``d >= 0``. ``tolerance``
    must be a finite non-bool int/float ``> 0``.

    Each ``first`` point is processed in input order and matched to the
    still-unused ``second`` point minimizing the unrounded 2-D distance
    ``sqrt((x1 - x2)**2 + (y1 - y2)**2)``, provided it does not exceed
    ``tolerance``; equal distances resolve to the earliest ``second``
    point in input order. A ``first`` point with no admissible match is
    skipped, and a ``second`` point can be used at most once. If fewer
    than one pair is formed, a ``ValueError`` is raised.

    Validation order (first error wins): the ``first`` container, its
    non-emptiness, the ``second`` container, its non-emptiness, each
    point in index order (first ``first`` points then ``second`` points:
    point container, length, fields), then ``tolerance`` (type,
    finiteness, positivity). Point errors are prefixed with
    ``"first[i]: "`` or ``"second[j]: "``.

    Returns a tuple, in ``first`` input order, of four-element tuples
    ``(x, y, d1, d2)`` whose items are all floats; ``x``/``y`` and
    ``d1`` come from the ``first`` point and ``d2`` from the matched
    ``second`` point. Values are rounded to 6 decimals (negative zero
    normalized to ``0.0``). Inputs are not modified.
    """
    if not isinstance(first, (list, tuple)):
        raise TypeError("first must be a list or tuple")
    if len(first) == 0:
        raise ValueError("first must be non-empty")
    if not isinstance(second, (list, tuple)):
        raise TypeError("second must be a list or tuple")
    if len(second) == 0:
        raise ValueError("second must be non-empty")

    for label, points in (("first", first), ("second", second)):
        for i in range(len(points)):
            point = points[i]
            prefix = f"{label}[{i}]: "
            if not isinstance(point, (list, tuple)):
                raise TypeError(prefix + "must be a list or tuple")
            if len(point) != 3:
                raise ValueError(prefix + "must have 3 elements")
            for name, value in zip(_POINT_FIELDS, point):
                if not _is_real_number(value):
                    raise TypeError(prefix + f"{name} must be a non-bool int or float")
            for name, value in zip(_POINT_FIELDS, point):
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

    used = [False] * len(second)
    pairs = []
    for x1, y1, d1 in first:
        best_index = None
        best_distance = None
        for j in range(len(second)):
            if used[j]:
                continue
            x2, y2, d2 = second[j]
            distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
            if distance <= tolerance and (
                best_distance is None or distance < best_distance
            ):
                best_index = j
                best_distance = distance
        if best_index is None:
            continue
        used[best_index] = True
        x2, y2, d2 = second[best_index]
        pairs.append((x1, y1, d1, d2))

    if len(pairs) == 0:
        raise ValueError("no points matched within tolerance")

    result = []
    for x, y, d1, d2 in pairs:
        item = []
        for value in (x, y, d1, d2):
            rounded = round(float(value), 6)
            item.append(0.0 if rounded == 0 else rounded)
        result.append(tuple(item))
    return tuple(result)
