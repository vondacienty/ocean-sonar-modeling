"""Crosspoint accuracy evaluation for overlapping survey lines.

Each crosspoint pairs the two depths observed at the same location;
the depth difference ``r = d1 - d2`` is summarized by its mean bias,
RMSE and maximum absolute value, and the differences within the
tolerance are counted.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = [
    "evaluate",
    "report",
    "pair",
    "audit",
    "profile",
    "aggregate",
    "dashboard",
    "dashboard_summary",
]

_FIELDS = ("x", "y", "d1", "d2")
_POINT_FIELDS = ("x", "y", "d")


def _validate_crossings(crossings):
    """Validate ``crossings`` exactly as :func:`evaluate` does."""
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


def _validate_tolerances(tolerances):
    """Validate ``tolerances`` exactly as :func:`audit` does."""
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


def audit(crossings, tolerances):
    """Run :func:`report` for several tolerances.

    ``crossings`` is validated with the full ``crossings`` contract of
    :func:`evaluate` (container, non-emptiness and every item);
    ``tolerances`` must then be a non-empty list/tuple whose items,
    checked in input order, are finite non-bool int/float values
    ``> 0``.

    Validation order (first error wins): the complete ``crossings``
    validation, then the ``tolerances`` container, its non-emptiness,
    then each tolerance in index order (type, finiteness, positivity).
    Item errors are prefixed with ``"tolerances[i]: "``.

    :func:`report` is called exactly once per tolerance, in input
    order, with no sorting, deduplication or mutation of the inputs;
    any exception it raises is propagated unchanged.

    Returns a tuple with the same length as ``tolerances`` whose items
    are the corresponding :func:`report` dicts, each with keys in the
    fixed order
    ``count, bias, rmse, max_abs, within_tolerance, within_ratio,
    stdev, quality`` and :func:`report`'s six-decimal rounding and
    negative-zero rules.
    """
    _validate_crossings(crossings)
    _validate_tolerances(tolerances)

    return tuple(report(crossings, tolerance) for tolerance in tolerances)


def _profile_from_reports(reports, tolerances):
    """Compute the :func:`profile` result from an :func:`audit` tuple."""
    ordered = sorted(
        ((tolerances[i], i, item) for i, item in enumerate(reports)),
        key=lambda entry: (entry[0], entry[1]),
    )

    curve_items = []
    counts = []
    first_pass_tolerance = None
    for tolerance, _index, item in ordered:
        rounded_tolerance = round(float(tolerance), 6)
        if rounded_tolerance == 0:
            rounded_tolerance = 0.0
        curve_items.append(
            {
                "tolerance": rounded_tolerance,
                "within_tolerance": item["within_tolerance"],
                "within_ratio": item["within_ratio"],
                "bias": item["bias"],
                "rmse": item["rmse"],
                "quality": item["quality"],
            }
        )
        counts.append(item["within_tolerance"])
        if first_pass_tolerance is None and item["quality"] == "pass":
            first_pass_tolerance = rounded_tolerance

    monotonic = all(b >= a for a, b in zip(counts, counts[1:]))

    m = len(ordered)
    if m < 2:
        area = 0.0
    else:
        area = round(
            float(
                math.fsum(
                    (ordered[i][0] - ordered[i - 1][0])
                    * (ordered[i][2]["within_ratio"] + ordered[i - 1][2]["within_ratio"])
                    / 2
                    for i in range(1, m)
                )
            ),
            6,
        )
        if area == 0:
            area = 0.0

    return {
        "curve": tuple(curve_items),
        "monotonic": monotonic,
        "first_pass_tolerance": first_pass_tolerance,
        "area": area,
    }


def profile(crossings, tolerances):
    """Build a tolerance profile from :func:`audit` results.

    Calls :func:`audit` exactly once with ``crossings`` and
    ``tolerances``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs are not modified.

    With ``R`` the tuple returned by :func:`audit`, one item per input
    tolerance, items are ordered ascending by
    ``(tolerances[i], i)``; equal tolerances therefore keep their input
    order. ``curve`` is a tuple of dicts, one per ordered item, each
    with keys in the order
    ``tolerance, within_tolerance, within_ratio, bias, rmse,
    quality``; ``tolerance`` is ``round(float(tolerances[i]), 6)``
    (negative zero normalized to ``0.0``) and the remaining fields are
    copied unchanged from the corresponding ``R`` item.

    ``monotonic`` is whether the ``within_tolerance`` counts are
    non-decreasing along the curve (``True`` for a single item).
    ``first_pass_tolerance`` is the rounded threshold of the first
    curve item whose ``quality`` is ``"pass"``, or ``None`` when no
    item passes.

    With ``t_i`` the *unrounded* tolerance and ``q_i`` the
    ``within_ratio`` of the item at ordered position ``i`` and
    ``m = len(R)``, ``area`` is ``0.0`` for ``m < 2`` and otherwise the
    trapezoidal integral
    ``round(float(fsum((t_i - t_{i-1}) * (q_i + q_{i-1}) / 2
    for i in range(1, m))), 6)`` with negative zero normalized to
    ``0.0``.

    Returns a dict with keys in the order
    ``curve, monotonic, first_pass_tolerance, area``; their types are
    tuple, bool, float or ``None`` and float.
    """
    reports = audit(crossings, tolerances)
    return _profile_from_reports(reports, tolerances)


def _aggregate_from_reports(reports, tolerances):
    """Compute the :func:`aggregate` result from an :func:`audit` tuple."""
    m = len(reports)

    count = sum(x["count"] for x in reports)
    pass_count = sum(x["quality"] == "pass" for x in reports)
    fail_count = m - pass_count
    mean_bias = math.fsum(x["bias"] for x in reports) / m
    max_rmse = max(x["rmse"] for x in reports)
    mean_ratio = math.fsum(x["within_ratio"] for x in reports) / m

    passed = [t for t, x in zip(tolerances, reports) if x["quality"] == "pass"]
    best_tolerance = min(passed) if passed else None

    result = {
        "count": int(count),
        "pass_count": int(pass_count),
        "fail_count": int(fail_count),
    }
    for name, value in (
        ("mean_bias", mean_bias),
        ("max_rmse", max_rmse),
        ("mean_ratio", mean_ratio),
    ):
        value = round(float(value), 6)
        result[name] = 0.0 if value == 0 else value
    if best_tolerance is None:
        result["best_tolerance"] = None
    else:
        best_tolerance = round(float(best_tolerance), 6)
        result["best_tolerance"] = 0.0 if best_tolerance == 0 else best_tolerance
    result["quality"] = "pass" if pass_count == m else "fail"
    return result


def aggregate(crossings, tolerances):
    """Aggregate :func:`audit` results across tolerances.

    Calls :func:`audit` exactly once with ``crossings`` and
    ``tolerances``, so its validation, exceptions (propagated
    unchanged) and per-tolerance reports all apply here as well.
    Inputs are not modified.

    With ``R`` the tuple returned by :func:`audit` and ``m = len(R)``,
    the summary is ``count = sum(x["count"])``,
    ``pass_count`` the number of reports with ``quality == "pass"``,
    ``fail_count = m - pass_count``,
    ``mean_bias = fsum(x["bias"]) / m``,
    ``max_rmse = max(x["rmse"])`` and
    ``mean_ratio = fsum(x["within_ratio"]) / m``. ``best_tolerance``
    is the smallest tolerance whose report passed, or ``None`` when no
    report passed; ``quality`` is ``"pass"`` only when every report
    passed and ``"fail"`` otherwise.

    Returns a dict with keys in the order
    ``count, pass_count, fail_count, mean_bias, max_rmse, mean_ratio,
    best_tolerance, quality``; ``count``/``pass_count``/``fail_count``
    are ints and the numeric statistics are floats rounded to 6
    decimals (negative zero normalized to ``0.0``).
    """
    reports = audit(crossings, tolerances)
    return _aggregate_from_reports(reports, tolerances)


def dashboard(crossings, tolerances):
    """Bundle :func:`audit`, :func:`profile` and :func:`aggregate` results.

    Calls :func:`audit` exactly once with ``crossings`` and
    ``tolerances``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs are not modified; :func:`profile` and :func:`aggregate` are
    not called (their values are derived directly from the single
    :func:`audit` result).

    Returns a tuple ``(reports, profile, aggregate, quality)`` where
    ``reports`` is the tuple returned by :func:`audit`; ``profile`` and
    ``aggregate`` are dicts with the keys, values, types and rounding
    rules of :func:`profile` and :func:`aggregate` respectively; and
    ``quality`` is ``"pass"`` only when the aggregate ``quality`` is
    ``"pass"``, the profile ``monotonic`` flag is true and
    ``first_pass_tolerance`` is not ``None``, and ``"fail"`` otherwise.
    """
    reports = audit(crossings, tolerances)
    profiled = _profile_from_reports(reports, tolerances)
    aggregated = _aggregate_from_reports(reports, tolerances)
    quality = (
        "pass"
        if aggregated["quality"] == "pass"
        and profiled["monotonic"] is True
        and profiled["first_pass_tolerance"] is not None
        else "fail"
    )
    return reports, profiled, aggregated, quality


def dashboard_summary(crossings, tolerances):
    """Summarize crosspoint depth differences across tolerances.

    ``crossings`` is a non-empty list/tuple; each item is a
    four-element list/tuple ``(x, y, d1, d2)`` whose fields are finite
    non-bool int/float values, with ``d1, d2 >= 0``. ``tolerances``
    must then be a non-empty list/tuple whose items, checked in input
    order, are finite non-bool int/float values ``> 0``.

    Validation order (first error wins): the ``crossings`` container,
    its non-emptiness, each crossing in index order (item container,
    length, fields), then the ``tolerances`` container, its
    non-emptiness, then each tolerance in index order (type,
    finiteness, positivity). Type mismatches raise ``TypeError``; every
    other violation raises ``ValueError``. Item errors are prefixed
    with ``"crossings[i]: "`` or ``"tolerances[i]: "``.

    With ``r = d1 - d2``, ``n`` the number of crosspoints and each
    tolerance ``t``, the per-tolerance statistics are
    ``b = fsum(r) / n`` (mean bias), ``e = sqrt(fsum(r**2) / n)``
    (RMSE), ``w`` the number of crosspoints with ``abs(r) <= t`` and
    ``q = w / n``; the tolerance passes (``p``) when ``w == n``.

    Returns a dict with keys in the order
    ``count, pass_count, fail_count, total_count, mean_bias, max_rmse,
    mean_ratio, quality``; ``count`` is the number of tolerances;
    ``pass_count``/``fail_count`` are the numbers of tolerances for
    which ``p`` is true/false; ``total_count`` is the sum of ``n`` over
    the tolerances; ``mean_bias`` is the mean of the ``b`` values,
    ``max_rmse`` the maximum of the ``e`` values and ``mean_ratio`` the
    mean of the ``q`` values; ``quality`` is ``"pass"`` only when every
    tolerance passes and ``"fail"`` otherwise. Counts are ints and the
    statistics are floats rounded to 6 decimals (negative zero
    normalized to ``0.0``). Inputs are not modified.
    """
    _validate_crossings(crossings)
    _validate_tolerances(tolerances)

    differences = [d1 - d2 for x, y, d1, d2 in crossings]
    n = len(differences)
    m = len(tolerances)

    biases = []
    rmses = []
    ratios = []
    pass_count = 0
    for tolerance in tolerances:
        bias = math.fsum(differences) / n
        rmse = math.sqrt(math.fsum(r * r for r in differences) / n)
        within = sum(1 for r in differences if abs(r) <= tolerance)
        biases.append(bias)
        rmses.append(rmse)
        ratios.append(within / n)
        if within == n:
            pass_count += 1

    fail_count = m - pass_count
    mean_bias = math.fsum(biases) / m
    max_rmse = max(rmses)
    mean_ratio = math.fsum(ratios) / m

    result = {
        "count": int(m),
        "pass_count": int(pass_count),
        "fail_count": int(fail_count),
        "total_count": int(n * m),
    }
    for name, value in (
        ("mean_bias", mean_bias),
        ("max_rmse", max_rmse),
        ("mean_ratio", mean_ratio),
    ):
        value = round(float(value), 6)
        result[name] = 0.0 if value == 0 else value
    result["quality"] = "pass" if pass_count == m else "fail"
    return result


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
