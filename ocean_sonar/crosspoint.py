"""Crosspoint accuracy evaluation for overlapping survey lines.

Each crosspoint pairs the two depths observed at the same location;
the depth difference ``r = d1 - d2`` is summarized by its mean bias,
RMSE and maximum absolute value, and the differences within the
tolerance are counted.
"""

from __future__ import annotations

import json
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
    "dashboard_report",
    "gate",
    "gate_report",
    "pair_gate",
    "pair_gate_report",
    "pair_gate_score",
    "pair_gate_score_report",
    "pair_gate_score_summary",
    "pair_gate_quality",
    "pair_gate_quality_report",
    "render_quality_batch",
    "serialize_quality_batch",
    "load_quality_batch",
    "aggregate_quality_batches",
    "dump_aggregate",
    "load_aggregate",
    "render_aggregate",
    "serialize_pair_gate_score_summary",
    "render_pair_gate_score_summary",
    "load_pair_gate_score_summary",
    "trend",
    "serialize_trend",
    "render_trend",
    "load_trend",
    "aggregate_trends",
    "dump_trends",
]

_FIELDS = ("x", "y", "d1", "d2")
_POINT_FIELDS = ("x", "y", "d")


def _is_finite_number(value):
    """Finite non-bool int/float without raising on oversized ints.

    Every non-bool int is finite; checking it via ``math.isfinite``
    would convert to float and raise ``OverflowError`` for values like
    ``10 ** 400``, which must surface as ``ValueError`` instead.
    """
    if not _is_real_number(value):
        return False
    if isinstance(value, int):
        return True
    return math.isfinite(value)


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


def dashboard_report(crossings, tolerances):
    """Bundle :func:`dashboard` with a cross-tolerance summary.

    Calls :func:`dashboard` exactly once with ``crossings`` and
    ``tolerances``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs and the :func:`dashboard` result are not modified.

    With ``D`` the four-tuple returned by :func:`dashboard`, ``R`` its
    first item (the per-tolerance reports) and ``m = len(R)``, the
    summary is ``count = m``, ``pass_count`` the number of reports with
    ``quality == "pass"``, ``fail_count = m - pass_count``,
    ``total_count = sum(x["count"])``,
    ``mean_bias = fsum(x["bias"]) / m``,
    ``max_rmse = max(x["rmse"])`` and
    ``mean_ratio = fsum(x["within_ratio"]) / m``.
    ``best_tolerance`` is the smallest tolerance whose report passed,
    or ``None`` when no report passed, and ``quality_score`` is
    ``100 * (pass_count / m) * mean_ratio``.

    Returns a dict with keys in the order ``dashboard, summary,
    quality``; ``dashboard`` is ``D`` itself and ``quality`` is
    ``D[3]``. ``summary`` is a dict with keys in the order ``count,
    pass_count, fail_count, total_count, mean_bias, max_rmse,
    mean_ratio, best_tolerance, quality_score``; the counts are ints,
    ``best_tolerance`` is a float or ``None`` and the remaining
    statistics are floats rounded to 6 decimals (negative zero
    normalized to ``0.0``).
    """
    result = dashboard(crossings, tolerances)
    reports = result[0]
    m = len(reports)

    pass_count = sum(x["quality"] == "pass" for x in reports)
    fail_count = m - pass_count
    total_count = sum(x["count"] for x in reports)
    mean_bias = math.fsum(x["bias"] for x in reports) / m
    max_rmse = max(x["rmse"] for x in reports)
    mean_ratio = math.fsum(x["within_ratio"] for x in reports) / m

    passed = [t for t, x in zip(tolerances, reports) if x["quality"] == "pass"]
    best_tolerance = min(passed) if passed else None

    quality_score = 100 * (pass_count / m) * mean_ratio

    summary = {
        "count": int(m),
        "pass_count": int(pass_count),
        "fail_count": int(fail_count),
        "total_count": int(total_count),
    }
    for name, value in (
        ("mean_bias", mean_bias),
        ("max_rmse", max_rmse),
        ("mean_ratio", mean_ratio),
    ):
        value = round(float(value), 6)
        summary[name] = 0.0 if value == 0 else value
    if best_tolerance is None:
        summary["best_tolerance"] = None
    else:
        best_tolerance = round(float(best_tolerance), 6)
        summary["best_tolerance"] = 0.0 if best_tolerance == 0 else best_tolerance
    quality_score = round(float(quality_score), 6)
    summary["quality_score"] = 0.0 if quality_score == 0 else quality_score

    return {
        "dashboard": result,
        "summary": summary,
        "quality": result[3],
    }


def gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
    """Gate a :func:`dashboard_report` against summary thresholds.

    Calls :func:`dashboard_report` exactly once with ``crossings`` and
    ``tolerances``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs and the :func:`dashboard_report` result are not modified.

    The thresholds are then validated in order: first
    ``min_mean_ratio``, then ``max_rmse_limit``. Each must be a finite
    non-bool int/float; ``min_mean_ratio`` must lie in ``[0, 1]`` and
    ``max_rmse_limit`` must be ``>= 0``. Type mismatches raise
    ``TypeError``; non-finite or out-of-range values raise
    ``ValueError``.

    With ``D`` the dict returned by :func:`dashboard_report` and
    ``S = D["summary"]``, returns a dict with keys in the order
    ``report, checks, quality``. ``report`` is ``D`` itself.
    ``checks`` is a dict with keys in the order ``mean_ratio, max_rmse,
    within_ok, rmse_ok``; the first two are the floats
    ``S["mean_ratio"]`` and ``S["max_rmse"]``, and the last two are the
    bools ``S["mean_ratio"] >= min_mean_ratio`` and
    ``S["max_rmse"] <= max_rmse_limit``. ``quality`` is ``"pass"`` only
    when ``D["quality"]`` is ``"pass"`` and both checks are true, and
    ``"fail"`` otherwise.
    """
    result = dashboard_report(crossings, tolerances)

    if not _is_real_number(min_mean_ratio):
        raise TypeError("min_mean_ratio must be a non-bool int or float")
    if not math.isfinite(min_mean_ratio):
        raise ValueError("min_mean_ratio must be finite")
    if not 0 <= min_mean_ratio <= 1:
        raise ValueError("min_mean_ratio must be in [0, 1]")
    if not _is_real_number(max_rmse_limit):
        raise TypeError("max_rmse_limit must be a non-bool int or float")
    if not math.isfinite(max_rmse_limit):
        raise ValueError("max_rmse_limit must be finite")
    if not max_rmse_limit >= 0:
        raise ValueError("max_rmse_limit must be >= 0")

    summary = result["summary"]
    within_ok = bool(summary["mean_ratio"] >= min_mean_ratio)
    rmse_ok = bool(summary["max_rmse"] <= max_rmse_limit)

    checks = {
        "mean_ratio": summary["mean_ratio"],
        "max_rmse": summary["max_rmse"],
        "within_ok": within_ok,
        "rmse_ok": rmse_ok,
    }
    quality = (
        "pass" if result["quality"] == "pass" and within_ok and rmse_ok else "fail"
    )
    return {
        "report": result,
        "checks": checks,
        "quality": quality,
    }


def gate_report(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
    """Report :func:`gate` results with threshold margins.

    Calls :func:`gate` exactly once with ``crossings``, ``tolerances``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the :func:`gate` result
    are not modified.

    With ``G`` the dict returned by :func:`gate` and
    ``S = G["report"]["summary"]``, returns a dict with keys in the
    order ``report, metrics, quality``. ``report`` is ``G`` itself and
    ``quality`` is ``G["quality"]``. ``metrics`` is a dict with keys in
    the order ``mean_ratio, max_rmse, within_margin, rmse_margin``; the
    first two are the floats ``S["mean_ratio"]`` and ``S["max_rmse"]``
    taken unchanged, and the last two are
    ``round(S["mean_ratio"] - min_mean_ratio, 6)`` and
    ``round(max_rmse_limit - S["max_rmse"], 6)``, both floats with
    negative zero normalized to ``0.0``.
    """
    result = gate(crossings, tolerances, min_mean_ratio, max_rmse_limit)
    summary = result["report"]["summary"]

    within_margin = round(float(summary["mean_ratio"] - min_mean_ratio), 6)
    if within_margin == 0:
        within_margin = 0.0
    rmse_margin = round(float(max_rmse_limit - summary["max_rmse"]), 6)
    if rmse_margin == 0:
        rmse_margin = 0.0

    metrics = {
        "mean_ratio": summary["mean_ratio"],
        "max_rmse": summary["max_rmse"],
        "within_margin": within_margin,
        "rmse_margin": rmse_margin,
    }
    return {
        "report": result,
        "metrics": metrics,
        "quality": result["quality"],
    }


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


def pair_gate(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
):
    """Pair points from two surveys and gate the resulting crosspoints.

    Calls :func:`pair` exactly once with ``first``, ``second`` and
    ``match_tolerance``; with ``P`` the tuple it returns, then calls
    :func:`gate` exactly once with ``P``, ``tolerances``,
    ``min_mean_ratio`` and ``max_rmse_limit``. Consequently the full
    :func:`pair` validation (including both point sequences and
    ``match_tolerance``) runs before any :func:`gate` validation, and
    every exception either function raises is propagated unchanged.
    Inputs are not modified.

    With ``G`` the dict returned by :func:`gate`, returns a dict with
    keys in the order ``pairs, report, quality``; ``pairs`` is the
    tuple ``P`` returned by :func:`pair`, ``report`` is ``G`` itself
    and ``quality`` is ``G["quality"]``.
    """
    pairs = pair(first, second, match_tolerance)
    gated = gate(pairs, tolerances, min_mean_ratio, max_rmse_limit)
    return {
        "pairs": pairs,
        "report": gated,
        "quality": gated["quality"],
    }


def pair_gate_report(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
):
    """Report :func:`pair_gate` results with matching coverage.

    Calls :func:`pair_gate` exactly once with ``first``, ``second``,
    ``tolerances``, ``match_tolerance``, ``min_mean_ratio`` and
    ``max_rmse_limit``, so its validation, first-error order,
    exceptions (propagated unchanged) and index prefixes all apply
    here as well. Inputs and the :func:`pair_gate` result are not
    modified.

    With ``G`` the dict returned by :func:`pair_gate`, ``P`` the tuple
    ``G["pairs"]``, ``m = len(P)``, ``f = len(first)`` and
    ``s = len(second)``, returns a dict with keys in the order
    ``pair_gate, matching, quality``. ``pair_gate`` is ``G`` itself.
    ``matching`` is a dict with keys in the order ``matched,
    first_total, second_total, first_coverage, second_coverage``; the
    first three are the ints ``m``, ``f`` and ``s``, and the last two
    are the floats ``round(m / f, 6)`` and ``round(m / s, 6)`` with
    negative zero normalized to ``0.0``. ``quality`` is ``"pass"``
    only when ``G["quality"]`` is ``"pass"`` and both coverages are
    ``1.0``, and ``"fail"`` otherwise.
    """
    result = pair_gate(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    pairs = result["pairs"]
    matched = len(pairs)
    first_total = len(first)
    second_total = len(second)

    first_coverage = round(float(matched / first_total), 6)
    if first_coverage == 0:
        first_coverage = 0.0
    second_coverage = round(float(matched / second_total), 6)
    if second_coverage == 0:
        second_coverage = 0.0

    matching = {
        "matched": int(matched),
        "first_total": int(first_total),
        "second_total": int(second_total),
        "first_coverage": first_coverage,
        "second_coverage": second_coverage,
    }
    quality = (
        "pass"
        if result["quality"] == "pass"
        and first_coverage == 1.0
        and second_coverage == 1.0
        else "fail"
    )
    return {
        "pair_gate": result,
        "matching": matching,
        "quality": quality,
    }


def pair_gate_score(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
):
    """Score :func:`pair_gate_report` results from coverage and mean ratio.

    Calls :func:`pair_gate_report` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the
    :func:`pair_gate_report` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_report`,
    ``G = R["pair_gate"]``, ``M = R["matching"]`` and
    ``S = G["report"]["report"]["summary"]`` (the dashboard-report
    summary nested inside the :func:`gate` result), the score is
    ``round(100 * M["first_coverage"] * M["second_coverage"]
    * S["mean_ratio"], 6)``, a float with negative zero normalized to
    ``0.0``.

    Returns a dict with keys in the order
    ``pair_gate, matching, score, quality``; ``pair_gate`` is ``G``
    itself and ``matching`` is ``M`` itself. ``quality`` is
    ``"pass"`` only when ``R["quality"]`` is ``"pass"`` and the
    score equals ``100.0``, and ``"fail"`` otherwise.
    """
    result = pair_gate_report(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    gated = result["pair_gate"]
    matching = result["matching"]
    summary = gated["report"]["report"]["summary"]

    score = round(
        float(
            100
            * matching["first_coverage"]
            * matching["second_coverage"]
            * summary["mean_ratio"]
        ),
        6,
    )
    if score == 0:
        score = 0.0

    quality = "pass" if result["quality"] == "pass" and score == 100.0 else "fail"
    return {
        "pair_gate": gated,
        "matching": matching,
        "score": score,
        "quality": quality,
    }


def pair_gate_score_report(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
) -> dict:
    """Report :func:`pair_gate_score` results with coverage and score margins.

    Calls :func:`pair_gate_score` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the
    :func:`pair_gate_score` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_score` and
    ``M = R["matching"]``, returns a dict with keys in the order
    ``score_report, metrics, quality``. ``score_report`` is ``R``
    itself. ``metrics`` is a dict with keys in the order
    ``coverage_product, score_margin``; ``coverage_product`` is
    ``round(float(M["first_coverage"] * M["second_coverage"]), 6)`` and
    ``score_margin`` is ``round(float(100 - R["score"]), 6)``, both
    floats with negative zero normalized to ``0.0``. ``quality`` is
    ``"pass"`` only when ``R["quality"]`` is ``"pass"`` and
    ``score_margin`` equals ``0.0``, and ``"fail"`` otherwise.
    """
    result = pair_gate_score(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    matching = result["matching"]

    coverage_product = round(
        float(matching["first_coverage"] * matching["second_coverage"]), 6
    )
    if coverage_product == 0:
        coverage_product = 0.0
    score_margin = round(float(100 - result["score"]), 6)
    if score_margin == 0:
        score_margin = 0.0

    metrics = {
        "coverage_product": coverage_product,
        "score_margin": score_margin,
    }
    quality = (
        "pass"
        if result["quality"] == "pass" and score_margin == 0.0
        else "fail"
    )
    return {
        "score_report": result,
        "metrics": metrics,
        "quality": quality,
    }


def pair_gate_score_summary(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
) -> dict:
    """Summarize :func:`pair_gate_score_report` results in one flat summary.

    Calls :func:`pair_gate_score_report` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the
    :func:`pair_gate_score_report` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_score_report`,
    returns a dict with keys in the order ``score_report, summary,
    quality``. ``score_report`` is ``R`` itself. ``summary`` is a dict
    with keys in the order ``coverage_product, score_margin, matched,
    pair_quality``: ``coverage_product`` and ``score_margin`` are the
    floats ``R["metrics"]["coverage_product"]`` and
    ``R["metrics"]["score_margin"]``, ``matched`` is the int
    ``R["score_report"]["matching"]["matched"]`` and ``pair_quality``
    is the string ``R["score_report"]["pair_gate"]["quality"]``, all
    copied as-is with no recomputation. ``quality`` is ``"pass"`` only
    when ``R["quality"]`` and ``pair_quality`` are both ``"pass"`` and
    ``score_margin`` equals ``0.0``, and ``"fail"`` otherwise.
    """
    result = pair_gate_score_report(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    metrics = result["metrics"]
    score_report = result["score_report"]

    coverage_product = metrics["coverage_product"]
    score_margin = metrics["score_margin"]
    matched = score_report["matching"]["matched"]
    pair_quality = score_report["pair_gate"]["quality"]

    summary = {
        "coverage_product": coverage_product,
        "score_margin": score_margin,
        "matched": matched,
        "pair_quality": pair_quality,
    }
    quality = (
        "pass"
        if result["quality"] == "pass"
        and pair_quality == "pass"
        and score_margin == 0.0
        else "fail"
    )
    return {
        "score_report": result,
        "summary": summary,
        "quality": quality,
    }


def pair_gate_quality(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_coverage=1.0,
    min_score=100.0,
) -> dict:
    """Gate :func:`pair_gate_score_summary` results against thresholds.

    Calls :func:`pair_gate_score_summary` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``, ``1.0`` and
    ``1.0``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs and the :func:`pair_gate_score_summary` result are not
    modified.

    The thresholds are then validated in order: first
    ``min_coverage``, then ``min_score``. Each must be a finite
    non-bool int/float; ``min_coverage`` must lie in ``[0, 1]`` and
    ``min_score`` must lie in ``[0, 100]``. Type mismatches raise
    ``TypeError``; non-finite or out-of-range values raise
    ``ValueError``.

    With ``R`` the dict returned by :func:`pair_gate_score_summary`,
    returns a dict with keys in the order ``report, checks, quality``.
    ``report`` is ``R`` itself. ``checks`` is a dict with keys in the
    order ``coverage_ok, score_ok``; the bools
    ``R["summary"]["coverage_product"] >= min_coverage`` and
    ``R["score_report"]["score_report"]["score"] >= min_score``.
    ``quality`` is ``"pass"`` only when
    ``R["summary"]["pair_quality"]`` is ``"pass"`` and both checks are
    true, and ``"fail"`` otherwise.
    """
    result = pair_gate_score_summary(
        first, second, tolerances, match_tolerance, 1.0, 1.0
    )

    if not _is_real_number(min_coverage):
        raise TypeError("min_coverage must be a non-bool int or float")
    if not _is_finite_number(min_coverage):
        raise ValueError("min_coverage must be finite")
    if not 0 <= min_coverage <= 1:
        raise ValueError("min_coverage must be in [0, 1]")
    if not _is_real_number(min_score):
        raise TypeError("min_score must be a non-bool int or float")
    if not _is_finite_number(min_score):
        raise ValueError("min_score must be finite")
    if not 0 <= min_score <= 100:
        raise ValueError("min_score must be in [0, 100]")

    coverage_ok = bool(result["summary"]["coverage_product"] >= min_coverage)
    score_ok = bool(result["score_report"]["score_report"]["score"] >= min_score)

    checks = {
        "coverage_ok": coverage_ok,
        "score_ok": score_ok,
    }
    quality = (
        "pass"
        if result["summary"]["pair_quality"] == "pass" and coverage_ok and score_ok
        else "fail"
    )
    return {
        "report": result,
        "checks": checks,
        "quality": quality,
    }


def pair_gate_quality_report(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_coverage=1.0,
    min_score=100.0,
) -> dict:
    """Report :func:`pair_gate_quality` results with thresholds and margins.

    Calls :func:`pair_gate_quality` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``, ``min_coverage``
    and ``min_score``, so its validation, first-error order, exceptions
    (propagated unchanged) and index prefixes all apply here as well.
    Inputs and the :func:`pair_gate_quality` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_quality`, returns
    a dict with keys in the order ``report, thresholds, margins,
    quality``. ``report`` is ``R`` itself and ``quality`` is
    ``R["quality"]``. ``thresholds`` is a dict with keys in the order
    ``min_coverage, min_score``; the floats
    ``round(float(min_coverage), 6)`` and ``round(float(min_score),
    6)`` with negative zero normalized to ``0.0``. ``margins`` is a
    dict with keys in the order
    ``coverage_margin, score_margin``; the floats
    ``round(R["report"]["summary"]["coverage_product"] - min_coverage,
    6)`` and ``round(R["report"]["score_report"]["score_report"]
    ["score"] - min_score, 6)``, both with negative zero normalized to
    ``0.0``.
    """
    result = pair_gate_quality(
        first, second, tolerances, match_tolerance, min_coverage, min_score
    )

    min_coverage_threshold = round(float(min_coverage), 6)
    if min_coverage_threshold == 0:
        min_coverage_threshold = 0.0
    min_score_threshold = round(float(min_score), 6)
    if min_score_threshold == 0:
        min_score_threshold = 0.0
    thresholds = {
        "min_coverage": min_coverage_threshold,
        "min_score": min_score_threshold,
    }

    coverage_margin = round(
        float(result["report"]["summary"]["coverage_product"] - min_coverage), 6
    )
    if coverage_margin == 0:
        coverage_margin = 0.0
    score_margin = round(
        float(result["report"]["score_report"]["score_report"]["score"] - min_score),
        6,
    )
    if score_margin == 0:
        score_margin = 0.0

    margins = {
        "coverage_margin": coverage_margin,
        "score_margin": score_margin,
    }
    return {
        "report": result,
        "thresholds": thresholds,
        "margins": margins,
        "quality": result["quality"],
    }


def render_quality_batch(
    records,
    tolerances,
    min_coverage=1.0,
    min_score=100.0,
) -> str:
    """Render one line summarizing a batch of :func:`pair_gate_quality_report` runs.

    ``records`` is a non-empty list/tuple; each item is a two-element
    list/tuple ``(first, second)``. Validation order (first error
    wins): the ``records`` container, its non-emptiness, then each
    record in index order (item container, then length). A non-list/
    tuple container raises ``TypeError``; emptiness or a wrong length
    raises ``ValueError``. Item errors are prefixed with
    ``"records[i]: "``.

    :func:`pair_gate_quality_report` is then called exactly once per
    record, in input order, with ``first``, ``second``, ``tolerances``,
    ``1.0``, ``min_coverage`` and ``min_score``; any exception it raises
    is propagated unchanged. Inputs are not modified.

    With ``R_i`` the dict returned for record ``i``, ``n`` the number
    of records, ``C_i = R_i.report.report.summary.coverage_product``,
    ``S_i = R_i.report.report.score_report.score_report.score``,
    ``p`` the number of records whose ``R_i.quality`` is ``"pass"`` and
    ``w`` the smallest index minimizing ``(S_i, C_i, i)`` lexicographically,
    returns one line with no trailing newline::

        count=n;mean_score=s;worst_index=w;quality=q

    where ``s = format(round(math.fsum(S_i) / n, 6), ".6f")`` with
    negative zero normalized to ``0.0``, ``n`` and ``w`` are rendered in
    decimal and ``q`` is ``"pass"`` only when ``p == n`` and ``"fail"``
    otherwise.
    """
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list or tuple")
    if len(records) == 0:
        raise ValueError("records must be non-empty")
    for i in range(len(records)):
        record = records[i]
        prefix = f"records[{i}]: "
        if not isinstance(record, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(record) != 2:
            raise ValueError(prefix + "must have 2 elements")

    scores = []
    coverages = []
    pass_count = 0
    for first, second in records:
        result = pair_gate_quality_report(
            first, second, tolerances, 1.0, min_coverage, min_score
        )
        inner = result["report"]["report"]
        coverages.append(inner["summary"]["coverage_product"])
        scores.append(inner["score_report"]["score_report"]["score"])
        if result["quality"] == "pass":
            pass_count += 1

    n = len(records)
    mean_score = round(float(math.fsum(scores) / n), 6)
    if mean_score == 0:
        mean_score = 0.0
    worst_index = min(
        range(n), key=lambda i: (scores[i], coverages[i], i)
    )
    quality = "pass" if pass_count == n else "fail"

    return (
        f"count={n};"
        f"mean_score={format(mean_score, '.6f')};"
        f"worst_index={worst_index};"
        f"quality={quality}"
    )


def serialize_quality_batch(
    records,
    tolerances,
    min_coverage=1.0,
    min_score=100.0,
) -> bytes:
    """Serialize a batch of :func:`pair_gate_quality_report` runs as JSON bytes.

    ``records`` is validated exactly as in :func:`render_quality_batch`:
    a non-empty list/tuple whose items, checked in index order, are
    two-element lists/tuples. A non-list/tuple container raises
    ``TypeError``; emptiness or a wrong length raises ``ValueError``.
    Item errors are prefixed with ``"records[i]: "``.

    :func:`pair_gate_quality_report` is then called exactly once per
    record, in input order, with ``first``, ``second``, ``tolerances``,
    ``1.0``, ``min_coverage`` and ``min_score``; any exception it raises
    is propagated unchanged. Inputs are not modified.

    With ``R`` the dict returned for record ``i``,
    ``P = R["report"]["report"]``,
    ``C = P["summary"]["coverage_product"]``,
    ``S = P["score_report"]["score_report"]["score"]`` and
    ``Q = R["quality"]``, the worst index ``w`` minimizes the
    *unrounded* tuple ``(S, C, i)`` lexicographically, the mean score is
    ``round(math.fsum(S_i) / n, 6)`` over the *unrounded* scores with
    negative zero normalized to ``0.0`` and the batch quality is
    ``"pass"`` only when every ``Q`` is ``"pass"``. The written
    ``coverage`` and ``score`` values are ``round(float(v), 6)`` with
    negative zero normalized to ``0.0``; the summary is never computed
    from those rounded values.

    The encoded object is compact UTF-8 JSON with top-level keys in the
    order ``records, summary``. ``records`` is an array whose items have
    keys in the order ``index, coverage, score, quality`` with values
    ``i``, the rounded ``C``, the rounded ``S`` and ``Q``; ``summary``
    has keys in the order ``count, mean_score, worst_index, quality``
    with values ``n``, the mean score, ``w`` and the batch quality.
    Encoding parameters (``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``), six-decimal float
    rounding with negative zero normalized to ``0.0``, the absence of a
    trailing newline and the ``ValueError`` raised on any JSON or UTF-8
    encoding failure all follow
    :func:`serialize_pair_gate_score_summary`.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list or tuple")
    if len(records) == 0:
        raise ValueError("records must be non-empty")
    for i in range(len(records)):
        record = records[i]
        prefix = f"records[{i}]: "
        if not isinstance(record, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(record) != 2:
            raise ValueError(prefix + "must have 2 elements")

    raw_coverages = []
    raw_scores = []
    qualities = []
    for first, second in records:
        result = pair_gate_quality_report(
            first, second, tolerances, 1.0, min_coverage, min_score
        )
        inner = result["report"]["report"]
        raw_coverages.append(inner["summary"]["coverage_product"])
        raw_scores.append(inner["score_report"]["score_report"]["score"])
        qualities.append(result["quality"])

    n = len(records)
    mean_score = round(float(math.fsum(raw_scores) / n), 6)
    if mean_score == 0:
        mean_score = 0.0
    worst_index = min(
        range(n), key=lambda i: (raw_scores[i], raw_coverages[i], i)
    )

    items = []
    for i in range(n):
        coverage = round(float(raw_coverages[i]), 6)
        if coverage == 0:
            coverage = 0.0
        score = round(float(raw_scores[i]), 6)
        if score == 0:
            score = 0.0
        items.append(
            {
                "index": int(i),
                "coverage": coverage,
                "score": score,
                "quality": qualities[i],
            }
        )

    document = {
        "records": items,
        "summary": {
            "count": int(n),
            "mean_score": mean_score,
            "worst_index": int(worst_index),
            "quality": "pass" if all(q == "pass" for q in qualities) else "fail",
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
        raise ValueError(
            f"quality batch: could not be serialized to JSON: {exc}"
        ) from exc


_QUALITY_BATCH_KEYS = ("records", "summary")
_QUALITY_BATCH_RECORD_KEYS = ("index", "coverage", "score", "quality")
_QUALITY_BATCH_SUMMARY_KEYS = (
    "count",
    "mean_score",
    "worst_index",
    "quality",
)


def _dump_quality_batch(batch):
    try:
        text = json.dumps(
            batch,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"quality batch: could not be serialized to JSON: {exc}"
        ) from exc


def _check_quality_batch_unit_float(value, name, low, high, prefix):
    if type(value) is not float:
        raise TypeError(prefix + f"{name} must be a float")
    if not math.isfinite(value):
        raise ValueError(prefix + f"{name} must be finite")
    if not low <= value <= high:
        raise ValueError(prefix + f"{name} must be in [{low}, {high}]")
    if value != round(float(value), 6):
        raise ValueError(
            prefix + f"{name} must equal round(float({name}), 6)"
        )


def _normalize_quality_batch_jsonable(value):
    """Round floats like the writer while preserving JSON arrays as lists."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(float(value), 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, list):
        return [_normalize_quality_batch_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_quality_batch_jsonable(item)
            for key, item in value.items()
        }
    return value


def _check_quality_batch(batch):
    prefix = "quality batch: "
    if not isinstance(batch, dict):
        raise TypeError("quality batch must be a dict")
    if list(batch.keys()) != list(_QUALITY_BATCH_KEYS):
        raise TypeError(
            "quality batch keys must be in the order records, summary"
        )

    records = batch["records"]
    if not isinstance(records, list):
        raise TypeError(prefix + "records must be a list")
    if len(records) == 0:
        raise ValueError(prefix + "records must be non-empty")

    all_pass = True
    for i in range(len(records)):
        record = records[i]
        record_prefix = f"{prefix}records[{i}]: "
        if not isinstance(record, dict):
            raise TypeError(record_prefix + "must be an object")
        if list(record.keys()) != list(_QUALITY_BATCH_RECORD_KEYS):
            raise TypeError(
                record_prefix
                + "keys must be in the order index, coverage, score, quality"
            )

        index = record["index"]
        if type(index) is not int:
            raise TypeError(record_prefix + "index must be a non-bool int")
        if index != i:
            raise ValueError(
                record_prefix + f"index must be {i} (consecutive from 0)"
            )

        _check_quality_batch_unit_float(
            record["coverage"], "coverage", 0, 1, record_prefix
        )
        _check_quality_batch_unit_float(
            record["score"], "score", 0, 100, record_prefix
        )

        quality = record["quality"]
        if type(quality) is not str:
            raise TypeError(record_prefix + "quality must be a str")
        if quality not in ("pass", "fail"):
            raise ValueError(
                record_prefix + "quality must be 'pass' or 'fail'"
            )
        if quality != "pass":
            all_pass = False

    n = len(records)
    summary = batch["summary"]
    summary_prefix = prefix + "summary: "
    if not isinstance(summary, dict):
        raise TypeError(summary_prefix + "must be an object")
    if list(summary.keys()) != list(_QUALITY_BATCH_SUMMARY_KEYS):
        raise TypeError(
            summary_prefix
            + "keys must be in the order "
            "count, mean_score, worst_index, quality"
        )

    count = summary["count"]
    if type(count) is not int:
        raise TypeError(summary_prefix + "count must be a non-bool int")
    if count != n:
        raise ValueError(summary_prefix + "count must equal the record count")

    _check_quality_batch_unit_float(
        summary["mean_score"], "mean_score", 0, 100, summary_prefix
    )

    worst_index = summary["worst_index"]
    if type(worst_index) is not int:
        raise TypeError(summary_prefix + "worst_index must be a non-bool int")
    if not 0 <= worst_index < n:
        raise ValueError(summary_prefix + f"worst_index must be in [0, {n})")

    quality = summary["quality"]
    if type(quality) is not str:
        raise TypeError(summary_prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(summary_prefix + "quality must be 'pass' or 'fail'")
    expected_quality = "pass" if all_pass else "fail"
    if quality != expected_quality:
        raise ValueError(
            summary_prefix
            + "quality must be 'pass' if and only if every record quality "
            "is 'pass'"
        )


def load_quality_batch(path) -> dict:
    """Load a :func:`serialize_quality_batch`-produced JSON batch.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_quality_batch` for the same value: compact UTF-8
    JSON (``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``) with no BOM and no trailing newline. A BOM, a
    trailing newline, a UTF-8 decoding failure or a JSON parsing
    failure raises ``ValueError``; the ``NaN``/``Infinity`` constants
    and any other non-finite token are rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``records, summary``. ``records`` must be a non-empty
    array of objects whose keys are exactly in the order
    ``index, coverage, score, quality``: ``index`` must be a non-bool
    int equal to the array position (consecutive from ``0``);
    ``coverage`` and ``score`` must be finite non-bool floats in
    ``[0, 1]`` and ``[0, 100]`` respectively, each equal to
    ``round(float(v), 6)`` with negative zero normalized to ``0.0``;
    and ``quality`` must be ``"pass"`` or ``"fail"``. Writing ``n`` for
    the record count, ``summary`` must have keys exactly in the order
    ``count, mean_score, worst_index, quality``: ``count`` must equal
    ``n``; ``mean_score`` must be a finite non-bool float in
    ``[0, 100]`` equal to ``round(float(v), 6)``; ``worst_index`` must
    be a non-bool int in ``[0, n)``; and ``quality`` must be
    ``"pass"`` if and only if every record quality is ``"pass"``. The
    file bytes must also equal the canonical re-serialization of the
    decoded value byte for byte; any key-order, type, range, relation,
    parse or canonical-byte mismatch raises ``ValueError``.

    Returns the batch as a dict with the keys in the order above; the
    file is never modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    batch = _normalize_quality_batch_jsonable(parsed)
    try:
        _check_quality_batch(batch)
        canonical = _dump_quality_batch(batch)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid quality batch: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize_quality_batch output"
        )

    return batch


def aggregate_quality_batches(paths) -> dict:
    """Aggregate several :func:`serialize_quality_batch` JSON files.

    ``paths`` must be a non-empty list/tuple whose items, checked in
    index order, are non-empty ``str`` paths. Validation order (first
    error wins): the ``paths`` container, its non-emptiness, then each
    item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; an empty container
    or an empty ``str`` raises ``ValueError``. Item errors are prefixed
    with ``"paths[i]: "``.

    :func:`load_quality_batch` is then called exactly once per path, in
    input order; any exception it raises is propagated unchanged.
    Inputs and the loaded files are not modified.

    With ``B_i`` the loaded batch for path ``i``, its ``records`` are
    expanded in batch order and in their original record order; for
    each record ``C``, ``S`` and ``Q`` are its ``coverage``, ``score``
    and ``quality``, and ``N`` is the total number of records. All
    statistics are recomputed from the records (never from the batch
    ``summary``); records are not sorted, copied or augmented.

    Returns a dict with keys in the order ``batches, summary,
    quality``. ``batches`` is a tuple of dicts with keys in the order
    ``index, path, batch``, whose values are the int ``i``, the
    original path ``str`` and the original ``B_i`` object. ``summary``
    has keys in the order
    ``batch_count, record_count, mean_coverage, mean_score,
    worst_batch_index, worst_record_index, quality``:
    ``batch_count`` and ``record_count`` are ints;
    ``mean_coverage`` and ``mean_score`` are
    ``round(float(fsum(C) / N), 6)`` and
    ``round(float(fsum(S) / N), 6)`` respectively, with negative zero
    normalized to ``0.0``; ``worst_batch_index`` and
    ``worst_record_index`` are the ints ``i`` and the record index of
    the record minimizing the tuple ``(S, C, i, index)``
    lexicographically. Both the summary and top-level ``quality`` are
    ``"pass"`` only when every ``Q`` is ``"pass"`` and ``"fail"``
    otherwise.
    """
    if not isinstance(paths, (list, tuple)):
        raise TypeError("paths must be a list or tuple")
    if len(paths) == 0:
        raise ValueError("paths must be non-empty")
    for i in range(len(paths)):
        prefix = f"paths[{i}]: "
        if not isinstance(paths[i], str):
            raise TypeError(prefix + "must be a str")
        if paths[i] == "":
            raise ValueError(prefix + "must not be empty")

    batch_items = []
    coverages = []
    scores = []
    all_pass = True
    for i in range(len(paths)):
        path = paths[i]
        batch = load_quality_batch(path)
        batch_items.append({"index": int(i), "path": path, "batch": batch})
        for record in batch["records"]:
            coverages.append(record["coverage"])
            scores.append(record["score"])
            if record["quality"] != "pass":
                all_pass = False

    n_batches = len(paths)
    n_records = len(coverages)

    mean_coverage = round(float(math.fsum(coverages) / n_records), 6)
    if mean_coverage == 0:
        mean_coverage = 0.0
    mean_score = round(float(math.fsum(scores) / n_records), 6)
    if mean_score == 0:
        mean_score = 0.0

    worst_position = None
    for i in range(n_batches):
        records = batch_items[i]["batch"]["records"]
        for record in records:
            position = (
                record["score"],
                record["coverage"],
                i,
                record["index"],
            )
            if worst_position is None or position < worst_position:
                worst_position = position

    quality = "pass" if all_pass else "fail"
    summary = {
        "batch_count": int(n_batches),
        "record_count": int(n_records),
        "mean_coverage": mean_coverage,
        "mean_score": mean_score,
        "worst_batch_index": int(worst_position[2]),
        "worst_record_index": int(worst_position[3]),
        "quality": quality,
    }
    return {
        "batches": tuple(batch_items),
        "summary": summary,
        "quality": quality,
    }


_AGGREGATE_KEYS = ("batches", "summary", "quality")
_AGGREGATE_BATCH_KEYS = ("index", "path", "batch")
_AGGREGATE_SUMMARY_KEYS = (
    "batch_count",
    "record_count",
    "mean_coverage",
    "mean_score",
    "worst_batch_index",
    "worst_record_index",
    "quality",
)


def _aggregate_to_jsonable(value):
    """Recursively convert tuples to JSON arrays, preserving everything else."""
    if isinstance(value, (list, tuple)):
        return [_aggregate_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _aggregate_to_jsonable(item) for key, item in value.items()}
    return value


def _dump_aggregate(aggregate):
    try:
        text = json.dumps(
            _aggregate_to_jsonable(aggregate),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"aggregate: could not be serialized to JSON: {exc}"
        ) from exc


def dump_aggregate(paths) -> bytes:
    """Serialize an :func:`aggregate_quality_batches` result as JSON bytes.

    Calls :func:`aggregate_quality_batches` exactly once with ``paths``
    — and no other combining function — so its validation, first-error
    order, exception messages and index prefixes all apply unchanged;
    every exception from that call is propagated unchanged and the
    input is neither modified nor reordered.

    With ``A`` the dict returned by :func:`aggregate_quality_batches`,
    the encoded object is ``A`` itself: keys stay in the order
    ``batches, summary, quality`` and every value is kept unchanged;
    the only structural conversion is that tuples (the top-level
    ``batches`` tuple) are recursively encoded as JSON arrays, while
    each ``batch["records"]`` remains an array and every other
    container remains an object or array.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation and
    no trailing newline, exactly as in
    :func:`serialize_quality_batch`; all floats produced by
    :func:`aggregate_quality_batches` are already rounded with
    ``round(float(v), 6)`` with negative zero normalized to ``0.0``.
    Any JSON or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    aggregate = aggregate_quality_batches(paths)
    return _dump_aggregate(aggregate)


def _check_aggregate(aggregate):
    prefix = "aggregate: "
    if not isinstance(aggregate, dict):
        raise TypeError("aggregate must be a dict")
    if list(aggregate.keys()) != list(_AGGREGATE_KEYS):
        raise TypeError(
            "aggregate keys must be in the order batches, summary, quality"
        )

    batches = aggregate["batches"]
    if not isinstance(batches, list):
        raise TypeError(prefix + "batches must be a list")
    if len(batches) == 0:
        raise ValueError(prefix + "batches must be non-empty")

    coverages = []
    scores = []
    all_pass = True
    worst_position = None
    for i in range(len(batches)):
        item = batches[i]
        item_prefix = f"{prefix}batches[{i}]: "
        if not isinstance(item, dict):
            raise TypeError(item_prefix + "must be an object")
        if list(item.keys()) != list(_AGGREGATE_BATCH_KEYS):
            raise TypeError(
                item_prefix + "keys must be in the order index, path, batch"
            )

        index = item["index"]
        if type(index) is not int:
            raise TypeError(item_prefix + "index must be a non-bool int")
        if index != i:
            raise ValueError(
                item_prefix + f"index must be {i} (consecutive from 0)"
            )

        path = item["path"]
        if not isinstance(path, str):
            raise TypeError(item_prefix + "path must be a str")
        if path == "":
            raise ValueError(item_prefix + "path must not be empty")

        try:
            _check_quality_batch(item["batch"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                item_prefix + f"batch is not a valid quality batch: {exc}"
            ) from exc

        for record in item["batch"]["records"]:
            coverages.append(record["coverage"])
            scores.append(record["score"])
            if record["quality"] != "pass":
                all_pass = False
            position = (
                record["score"],
                record["coverage"],
                i,
                record["index"],
            )
            if worst_position is None or position < worst_position:
                worst_position = position

    n_batches = len(batches)
    n_records = len(coverages)

    mean_coverage = round(float(math.fsum(coverages) / n_records), 6)
    if mean_coverage == 0:
        mean_coverage = 0.0
    mean_score = round(float(math.fsum(scores) / n_records), 6)
    if mean_score == 0:
        mean_score = 0.0
    expected_quality = "pass" if all_pass else "fail"

    summary = aggregate["summary"]
    summary_prefix = prefix + "summary: "
    if not isinstance(summary, dict):
        raise TypeError(summary_prefix + "must be an object")
    if list(summary.keys()) != list(_AGGREGATE_SUMMARY_KEYS):
        raise TypeError(
            summary_prefix
            + "keys must be in the order batch_count, record_count, "
            "mean_coverage, mean_score, worst_batch_index, "
            "worst_record_index, quality"
        )

    batch_count = summary["batch_count"]
    if type(batch_count) is not int:
        raise TypeError(summary_prefix + "batch_count must be a non-bool int")
    if batch_count != n_batches:
        raise ValueError(
            summary_prefix + "batch_count must equal the number of batches"
        )

    record_count = summary["record_count"]
    if type(record_count) is not int:
        raise TypeError(summary_prefix + "record_count must be a non-bool int")
    if record_count != n_records:
        raise ValueError(
            summary_prefix + "record_count must equal the total record count"
        )

    _check_quality_batch_unit_float(
        summary["mean_coverage"], "mean_coverage", 0, 1, summary_prefix
    )
    if summary["mean_coverage"] != mean_coverage:
        raise ValueError(
            summary_prefix
            + "mean_coverage must equal the mean of the record coverages"
        )
    _check_quality_batch_unit_float(
        summary["mean_score"], "mean_score", 0, 100, summary_prefix
    )
    if summary["mean_score"] != mean_score:
        raise ValueError(
            summary_prefix + "mean_score must equal the mean of the record scores"
        )

    worst_batch_index = summary["worst_batch_index"]
    if type(worst_batch_index) is not int:
        raise TypeError(summary_prefix + "worst_batch_index must be a non-bool int")
    if not 0 <= worst_batch_index < n_batches:
        raise ValueError(
            summary_prefix + f"worst_batch_index must be in [0, {n_batches})"
        )
    if worst_batch_index != worst_position[2]:
        raise ValueError(
            summary_prefix
            + "worst_batch_index must be the batch index of the worst record"
        )

    worst_record_index = summary["worst_record_index"]
    if type(worst_record_index) is not int:
        raise TypeError(
            summary_prefix + "worst_record_index must be a non-bool int"
        )
    if worst_record_index != worst_position[3]:
        raise ValueError(
            summary_prefix
            + "worst_record_index must be the record index of the worst record"
        )

    quality = summary["quality"]
    if type(quality) is not str:
        raise TypeError(summary_prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(summary_prefix + "quality must be 'pass' or 'fail'")
    if quality != expected_quality:
        raise ValueError(
            summary_prefix
            + "quality must be 'pass' if and only if every record quality "
            "is 'pass'"
        )

    top_quality = aggregate["quality"]
    if type(top_quality) is not str:
        raise TypeError(prefix + "quality must be a str")
    if top_quality not in ("pass", "fail"):
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    if top_quality != expected_quality:
        raise ValueError(prefix + "quality must equal the summary quality")


def load_aggregate(path) -> dict:
    """Load a :func:`dump_aggregate`-produced JSON aggregate.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by :func:`dump_aggregate`
    for the same value: compact UTF-8 JSON (``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``) with no BOM and no
    trailing newline. A BOM, a trailing newline, a UTF-8 decoding
    failure or a JSON parsing failure raises ``ValueError``; the
    ``NaN``/``Infinity`` constants and any other non-finite token are
    rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``batches, summary, quality``. ``batches`` must be a
    non-empty array of objects whose keys are exactly in the order
    ``index, path, batch``: ``index`` must be a non-bool int equal to
    the array position (consecutive from ``0``); ``path`` must be a
    non-empty ``str``; and ``batch`` must satisfy the full
    :func:`load_quality_batch` return structure (keys ``records,
    summary`` with all of its per-record and per-summary rules).
    ``summary`` must have keys exactly in the order ``batch_count,
    record_count, mean_coverage, mean_score, worst_batch_index,
    worst_record_index, quality`` and, recomputed from the batches'
    ``records`` in their original order, ``batch_count`` must equal the
    number of batches, ``record_count`` the total number of records,
    ``mean_coverage``/``mean_score`` the floats
    ``round(float(fsum(C) / N), 6)`` and
    ``round(float(fsum(S) / N), 6)`` (negative zero normalized to
    ``0.0``), ``worst_batch_index``/``worst_record_index`` the ints
    locating the record minimizing ``(score, coverage, batch index,
    record index)`` lexicographically, and ``quality`` — like the
    top-level ``quality`` — ``"pass"`` if and only if every record
    quality is ``"pass"``. The file bytes must also equal the canonical
    re-serialization of the decoded value byte for byte; any key-order,
    type, range, relation, parse or canonical-byte mismatch raises
    ``ValueError``.

    Returns the aggregate as a dict with the keys in the order above;
    only the top-level ``batches`` array is restored to a tuple, each
    ``batch["records"]`` stays a list and every other container stays a
    dict or list. The file is never modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    normalized = _normalize_quality_batch_jsonable(parsed)
    try:
        _check_aggregate(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid aggregate: {exc}"
        ) from exc

    aggregate = {
        "batches": tuple(normalized["batches"]),
        "summary": normalized["summary"],
        "quality": normalized["quality"],
    }
    canonical = _dump_aggregate(aggregate)
    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical dump_aggregate output"
        )

    return aggregate


def render_aggregate(path) -> str:
    """Render a :func:`load_aggregate`-loaded aggregate as three text lines.

    Calls :func:`load_aggregate` exactly once with ``path`` — and no
    other loader — so its path validation, file reading, canonical-byte
    checks and every exception (propagated unchanged) all apply here as
    well. Neither the file nor the loaded aggregate is modified.

    With ``A`` the dict returned by :func:`load_aggregate`,
    ``S = A["summary"]``, ``b = S["worst_batch_index"]``,
    ``r = S["worst_record_index"]``, ``I = A["batches"][b]`` and
    ``W = I["batch"]["records"][r]``, returns three lines joined by
    ``"\\n"`` with no trailing newline::

        QUALITY=<A["quality"]>
        SUMMARY=<seven key=value pairs from S, in S's existing key order>
        WORST=path=<...>;batch_index=<b>;record_index=<r>;coverage=<...>;score=<...>;quality=<...>

    The SUMMARY pairs are written in ``S``'s existing key order (no
    sorting, recomputation, copying or added/removed keys) and joined by
    ``";"``. The WORST values are ``I["path"]`` (rendered as the JSON
    string produced by
    ``json.dumps(v, ensure_ascii=False, separators=(",", ":"))``), the
    ints ``b`` and ``r`` in decimal, and ``W["coverage"]``,
    ``W["score"]`` and ``W["quality"]`` taken unchanged. Other ints are
    formatted in decimal, floats use ``format(v, ".6f")`` (negative
    zero rendered as ``"0.000000"``) and strings are copied as-is.
    """
    aggregate = load_aggregate(path)
    summary = aggregate["summary"]
    worst_batch_index = summary["worst_batch_index"]
    worst_record_index = summary["worst_record_index"]
    batch_item = aggregate["batches"][worst_batch_index]
    worst_record = batch_item["batch"]["records"][worst_record_index]

    quality_line = "QUALITY=" + _format_rendered_value(aggregate["quality"])
    summary_line = "SUMMARY=" + ";".join(
        f"{key}={_format_rendered_value(value)}" for key, value in summary.items()
    )
    worst_line = (
        "WORST="
        "path="
        + json.dumps(
            batch_item["path"], ensure_ascii=False, separators=(",", ":")
        )
        + f";batch_index={_format_rendered_value(worst_batch_index)}"
        + f";record_index={_format_rendered_value(worst_record_index)}"
        + f";coverage={_format_rendered_value(worst_record['coverage'])}"
        + f";score={_format_rendered_value(worst_record['score'])}"
        + f";quality={_format_rendered_value(worst_record['quality'])}"
    )
    return "\n".join((quality_line, summary_line, worst_line))


def trend(paths) -> dict:
    """Compare successive :func:`load_aggregate` snapshots along one path set.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_aggregate` is then called exactly once per path, in
    input order; any exception it raises is propagated unchanged.
    Inputs and the loaded files are not modified.

    Every loaded aggregate must have the same number of batches as the
    first one and, for each corresponding batch ``b``, the same
    ``path`` and the same number of ``records``; otherwise a
    ``ValueError`` is raised.

    For each snapshot pair ``i = 1..n-1``, batch ``b`` and record ``r``,
    the unrounded deltas are ``dc = coverage_i - coverage_(i-1)`` and
    ``ds = score_i - score_(i-1)``; a comparison is degraded when
    ``dc < 0``, ``ds < 0`` or its quality changes from ``"pass"`` to
    ``"fail"``. With ``K`` the total number of comparisons, the worst
    comparison ``w`` minimizes the *unrounded* tuple
    ``(ds, dc, i, b, r)`` lexicographically, and
    ``coverage_delta``/``score_delta`` are the ``math.fsum`` of all
    ``dc``/``ds`` values divided by ``K``. Comparisons are not sorted,
    deduplicated or augmented.

    Returns a dict with keys in the order
    ``count, changes, degraded, coverage_delta, score_delta, worst,
    quality``: ``count`` is the snapshot count ``n`` and
    ``changes``/``degraded`` are ``K`` and the number of degraded
    comparisons, all ints; the two deltas are
    ``round(float(fsum / K), 6)`` floats and ``worst`` is the tuple
    ``(i, b, r, dc, ds)`` whose first three items are ints and last two
    the rounded delta floats; every float is
    ``round(float(v), 6)`` with negative zero normalized to ``0.0``.
    ``quality`` is ``"pass"`` only when no comparison is degraded and
    ``"fail"`` otherwise.
    """
    if not isinstance(paths, (list, tuple)):
        raise TypeError("paths must be a list or tuple")
    if len(paths) < 2:
        raise ValueError("paths must contain at least 2 items")
    for i in range(len(paths)):
        prefix = f"paths[{i}]: "
        if not isinstance(paths[i], str):
            raise TypeError(prefix + "must be a str")
        if paths[i] == "":
            raise ValueError(prefix + "must not be empty")

    aggregates = [load_aggregate(path) for path in paths]

    first_batches = aggregates[0]["batches"]
    batch_count = len(first_batches)
    for i in range(1, len(aggregates)):
        batches = aggregates[i]["batches"]
        if len(batches) != batch_count:
            raise ValueError(
                f"aggregate at paths[{i}] has {len(batches)} batches, "
                f"expected {batch_count}"
            )
        for b in range(batch_count):
            if batches[b]["path"] != first_batches[b]["path"]:
                raise ValueError(
                    f"aggregate at paths[{i}] batch {b} path "
                    f"{batches[b]['path']!r} does not match "
                    f"{first_batches[b]['path']!r}"
                )
            first_records = first_batches[b]["batch"]["records"]
            records = batches[b]["batch"]["records"]
            if len(records) != len(first_records):
                raise ValueError(
                    f"aggregate at paths[{i}] batch {b} has "
                    f"{len(records)} records, expected "
                    f"{len(first_records)}"
                )

    coverage_deltas = []
    score_deltas = []
    worst_position = None
    worst_dc = None
    worst_ds = None
    degraded = 0
    for i in range(1, len(aggregates)):
        previous = aggregates[i - 1]["batches"]
        current = aggregates[i]["batches"]
        for b in range(batch_count):
            previous_records = previous[b]["batch"]["records"]
            current_records = current[b]["batch"]["records"]
            for r in range(len(current_records)):
                dc = (
                    current_records[r]["coverage"]
                    - previous_records[r]["coverage"]
                )
                ds = current_records[r]["score"] - previous_records[r]["score"]
                coverage_deltas.append(dc)
                score_deltas.append(ds)
                if (
                    dc < 0
                    or ds < 0
                    or (
                        previous_records[r]["quality"] == "pass"
                        and current_records[r]["quality"] == "fail"
                    )
                ):
                    degraded += 1
                position = (ds, dc, i, b, r)
                if worst_position is None or position < worst_position:
                    worst_position = position
                    worst_dc = dc
                    worst_ds = ds

    changes = len(coverage_deltas)
    coverage_delta = round(float(math.fsum(coverage_deltas) / changes), 6)
    if coverage_delta == 0:
        coverage_delta = 0.0
    score_delta = round(float(math.fsum(score_deltas) / changes), 6)
    if score_delta == 0:
        score_delta = 0.0

    worst_dc = round(float(worst_dc), 6)
    if worst_dc == 0:
        worst_dc = 0.0
    worst_ds = round(float(worst_ds), 6)
    if worst_ds == 0:
        worst_ds = 0.0
    worst = (
        int(worst_position[2]),
        int(worst_position[3]),
        int(worst_position[4]),
        worst_dc,
        worst_ds,
    )

    return {
        "count": int(len(aggregates)),
        "changes": int(changes),
        "degraded": int(degraded),
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "worst": worst,
        "quality": "pass" if degraded == 0 else "fail",
    }


def serialize_trend(paths) -> bytes:
    """Serialize a :func:`trend` result as UTF-8 JSON bytes.

    Calls :func:`trend` exactly once with ``paths`` — and no other
    combining function — so its validation, first-error order,
    exceptions (propagated unchanged) and ``"paths[i]: "`` index
    prefixes all apply here as well. Inputs and the loaded files are not
    modified.

    With ``T`` the dict returned by :func:`trend`, the encoded object
    has keys exactly in the order
    ``count, changes, degraded, coverage_delta, score_delta, worst,
    quality``: the first three values are the ints ``T["count"]``,
    ``T["changes"]`` and ``T["degraded"]``, the next two are the floats
    ``T["coverage_delta"]`` and ``T["score_delta"]``, ``worst`` is the
    five-item JSON array ``[i, b, r, dc, ds]`` derived from
    ``T["worst"]`` and ``quality`` is ``T["quality"]``, all taken
    directly from ``T`` with no recomputation, sorting or additional
    keys.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline. Floats are first rounded with
    ``round(float(v), 6)`` and negative zero is normalized to ``0.0``;
    ints are written in decimal and strings are copied as-is. Any JSON
    or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    result = trend(paths)
    worst = result["worst"]

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    document = {
        "count": int(result["count"]),
        "changes": int(result["changes"]),
        "degraded": int(result["degraded"]),
        "coverage_delta": rounded_float(result["coverage_delta"]),
        "score_delta": rounded_float(result["score_delta"]),
        "worst": [
            int(worst[0]),
            int(worst[1]),
            int(worst[2]),
            rounded_float(worst[3]),
            rounded_float(worst[4]),
        ],
        "quality": result["quality"],
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
        raise ValueError(f"trend: could not be serialized to JSON: {exc}") from exc


def render_trend(paths) -> str:
    """Render a :func:`trend` result as two text lines.

    Calls :func:`trend` exactly once with ``paths`` — and no other
    combining function — so its validation, first-error order,
    exceptions (propagated unchanged) and ``"paths[i]: "`` index
    prefixes all apply here as well. Inputs and the loaded files are not
    modified.

    With ``T`` the dict returned by :func:`trend` and
    ``(i, b, r, dc, ds) = T["worst"]``, returns two lines joined by
    ``"\\n"`` with no trailing newline::

        TREND=<count>,<changes>,<degraded>,<coverage_delta>,<score_delta>,<quality>
        WORST=<i>,<b>,<r>,<dc>,<ds>

    The values are taken directly from ``T`` and ``T["worst"]`` with no
    recomputation or sorting: ``count``, ``changes`` and ``degraded``
    (and ``i``, ``b``, ``r``) are ints formatted in decimal,
    ``coverage_delta``, ``score_delta``, ``dc`` and ``ds`` are floats
    formatted with ``format(v, ".6f")`` (negative zero rendered as
    ``"0.000000"``) and ``quality`` is copied as-is.
    """
    result = trend(paths)
    worst = result["worst"]

    trend_line = ",".join(
        (
            _format_rendered_value(result["count"]),
            _format_rendered_value(result["changes"]),
            _format_rendered_value(result["degraded"]),
            _format_rendered_value(result["coverage_delta"]),
            _format_rendered_value(result["score_delta"]),
            _format_rendered_value(result["quality"]),
        )
    )
    worst_line = "WORST=" + ",".join(
        _format_rendered_value(value) for value in worst
    )
    return "\n".join(("TREND=" + trend_line, worst_line))


_TREND_KEYS = (
    "count",
    "changes",
    "degraded",
    "coverage_delta",
    "score_delta",
    "worst",
    "quality",
)


def _reject_duplicate_json_pairs(pairs):
    """``object_pairs_hook`` that rejects duplicate JSON object keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _check_trend_float(value, name, low, high, prefix):
    """Validate a trend float: non-bool, finite, in range, 6-rounded, no -0.0."""
    _check_quality_batch_unit_float(value, name, low, high, prefix)
    if value == 0.0 and math.copysign(1.0, value) < 0.0:
        raise ValueError(prefix + f"{name} must not be negative zero")


def _check_trend_int(value, name, predicate, range_text, prefix):
    """Validate one non-bool trend int against ``predicate``."""
    if type(value) is not int:
        raise TypeError(prefix + f"{name} must be a non-bool int")
    if not predicate(value):
        raise ValueError(prefix + f"{name} must be {range_text}")


def _check_trend(result):
    prefix = "trend: "
    if not isinstance(result, dict):
        raise TypeError("trend must be a dict")
    if list(result.keys()) != list(_TREND_KEYS):
        raise TypeError(
            "trend keys must be in the order "
            "count, changes, degraded, coverage_delta, score_delta, "
            "worst, quality"
        )

    count = result["count"]
    _check_trend_int(count, "count", lambda v: v >= 2, ">= 2", prefix)

    changes = result["changes"]
    _check_trend_int(changes, "changes", lambda v: v > 0, "> 0", prefix)

    degraded = result["degraded"]
    _check_trend_int(
        degraded,
        "degraded",
        lambda v: 0 <= v <= changes,
        "in [0, changes]",
        prefix,
    )

    _check_trend_float(
        result["coverage_delta"], "coverage_delta", -1, 1, prefix
    )
    _check_trend_float(
        result["score_delta"], "score_delta", -100, 100, prefix
    )

    worst = result["worst"]
    worst_prefix = prefix + "worst: "
    if not isinstance(worst, list):
        raise TypeError(worst_prefix + "must be a list")
    if len(worst) != 5:
        raise ValueError(worst_prefix + "must have 5 elements")

    _check_trend_int(
        worst[0],
        "i",
        lambda v: 1 <= v < count,
        "in [1, count)",
        worst_prefix,
    )
    _check_trend_int(worst[1], "b", lambda v: v >= 0, ">= 0", worst_prefix)
    _check_trend_int(worst[2], "r", lambda v: v >= 0, ">= 0", worst_prefix)
    _check_trend_float(worst[3], "dc", -1, 1, worst_prefix)
    _check_trend_float(worst[4], "ds", -100, 100, worst_prefix)

    quality = result["quality"]
    if type(quality) is not str:
        raise TypeError(prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    if (quality == "pass") != (degraded == 0):
        raise ValueError(
            prefix
            + "quality must be 'pass' if and only if degraded is 0"
        )


def _dump_trend(result):
    document = {
        "count": int(result["count"]),
        "changes": int(result["changes"]),
        "degraded": int(result["degraded"]),
        "coverage_delta": result["coverage_delta"],
        "score_delta": result["score_delta"],
        "worst": [
            int(result["worst"][0]),
            int(result["worst"][1]),
            int(result["worst"][2]),
            result["worst"][3],
            result["worst"][4],
        ],
        "quality": result["quality"],
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
        raise ValueError(f"trend: could not be serialized to JSON: {exc}") from exc


def load_trend(path) -> dict:
    """Load a :func:`serialize_trend`-produced JSON trend document.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_trend` for the same value: compact UTF-8 JSON
    (``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``) with no BOM and no trailing newline. A BOM, a
    trailing newline, a UTF-8 decoding failure or a JSON parsing
    failure raises ``ValueError``; the ``NaN``/``Infinity`` constants,
    any other non-finite token and duplicate object keys are rejected.

    The decoded value must be a JSON object with keys exactly in the
    order ``count, changes, degraded, coverage_delta, score_delta,
    worst, quality`` — duplicated, missing or extra keys are rejected.
    The first three values must be non-bool ints with ``count >= 2``,
    ``changes > 0`` and ``degraded`` in ``[0, changes]``.
    ``coverage_delta`` must be a finite non-bool float in ``[-1, 1]``
    and ``score_delta`` a finite non-bool float in ``[-100, 100]``.
    ``worst`` must be the five-item array ``[i, b, r, dc, ds]``:
    ``i``, ``b`` and ``r`` non-bool ints with ``1 <= i < count`` and
    ``b``/``r >= 0``; ``dc`` a finite non-bool float in ``[-1, 1]``;
    and ``ds`` a finite non-bool float in ``[-100, 100]``. Every float
    must equal ``round(float(v), 6)`` and negative zero is forbidden.
    ``quality`` must be ``"pass"`` or ``"fail"``, and must be
    ``"pass"`` if and only if ``degraded`` is ``0``. The file bytes
    must also equal the canonical re-serialization of the decoded
    value byte for byte; any key-order, type, range, relation, parse or
    canonical-byte mismatch raises ``ValueError``.

    Returns the trend as a dict with the keys in the order above; only
    the ``worst`` array is restored to a tuple and every other value is
    returned unchanged. The file is never modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

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

    try:
        _check_trend(parsed)
        result = {
            "count": parsed["count"],
            "changes": parsed["changes"],
            "degraded": parsed["degraded"],
            "coverage_delta": parsed["coverage_delta"],
            "score_delta": parsed["score_delta"],
            "worst": tuple(parsed["worst"]),
            "quality": parsed["quality"],
        }
        canonical = _dump_trend(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize_trend output"
        )

    return result


def aggregate_trends(paths) -> dict:
    """Aggregate several :func:`load_trend` trend files into one summary.

    ``paths`` is validated exactly as in :func:`trend`: a list/tuple of
    at least two items whose items, checked in index order, are
    non-empty ``str`` paths. Validation order (first error wins): the
    ``paths`` container, its length, then each item in index order
    (type, then emptiness). A non-list/tuple container or a non-str
    item raises ``TypeError``; fewer than two items or an empty ``str``
    raises ``ValueError``. Item errors are prefixed with
    ``"paths[i]: "``.

    :func:`load_trend` is then called exactly once per path, in input
    order; any exception it raises is propagated unchanged. Inputs and
    the loaded files are not modified.

    With ``T_j`` the trend loaded from ``paths[j]``, ``K`` the sum of
    all ``T_j["changes"]`` and ``D`` the sum of all
    ``T_j["degraded"]``, the two deltas are the change-weighted means
    ``round(float(fsum(T_j["coverage_delta"] * T_j["changes"]) / K),
    6)`` and ``round(float(fsum(T_j["score_delta"] * T_j["changes"]) /
    K), 6)``, each with negative zero normalized to ``0.0``. Writing
    ``(i, b, r, dc, ds) = T_j["worst"]``, the worst item minimizes the
    tuple ``(ds, dc, j, i, b, r)`` lexicographically over all ``j``,
    using the values from ``T_j["worst"]`` unchanged.

    Returns a dict with keys in the order ``file_count, changes,
    degraded, coverage_delta, score_delta, worst, quality``:
    ``file_count`` is the int ``len(T_j)`` (the number of paths) and
    ``changes``/``degraded`` are the ints ``K`` and ``D``; the two
    deltas are floats; ``worst`` is the tuple ``(j, i, b, r, dc, ds)``
    whose first four items are ints and last two the floats from the
    winning ``T_j["worst"]``; ``quality`` is ``"pass"`` only when
    ``D == 0`` and ``"fail"`` otherwise.
    """
    if not isinstance(paths, (list, tuple)):
        raise TypeError("paths must be a list or tuple")
    if len(paths) < 2:
        raise ValueError("paths must contain at least 2 items")
    for i in range(len(paths)):
        prefix = f"paths[{i}]: "
        if not isinstance(paths[i], str):
            raise TypeError(prefix + "must be a str")
        if paths[i] == "":
            raise ValueError(prefix + "must not be empty")

    trends = [load_trend(path) for path in paths]

    changes = sum(item["changes"] for item in trends)
    degraded = sum(item["degraded"] for item in trends)

    coverage_delta = round(
        float(
            math.fsum(item["coverage_delta"] * item["changes"] for item in trends)
            / changes
        ),
        6,
    )
    if coverage_delta == 0:
        coverage_delta = 0.0
    score_delta = round(
        float(
            math.fsum(item["score_delta"] * item["changes"] for item in trends)
            / changes
        ),
        6,
    )
    if score_delta == 0:
        score_delta = 0.0

    worst_position = None
    for j in range(len(trends)):
        i, b, r, dc, ds = trends[j]["worst"]
        position = (ds, dc, j, i, b, r)
        if worst_position is None or position < worst_position:
            worst_position = position

    worst = (
        int(worst_position[2]),
        int(worst_position[3]),
        int(worst_position[4]),
        int(worst_position[5]),
        worst_position[1],
        worst_position[0],
    )

    return {
        "file_count": int(len(trends)),
        "changes": int(changes),
        "degraded": int(degraded),
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "worst": worst,
        "quality": "pass" if degraded == 0 else "fail",
    }


def dump_trends(paths) -> bytes:
    """Serialize an :func:`aggregate_trends` result as UTF-8 JSON bytes.

    Calls :func:`aggregate_trends` exactly once with ``paths`` — and no
    other combining function — so its validation, first-error order,
    exceptions (propagated unchanged) and ``"paths[i]: "`` index
    prefixes all apply here as well. Inputs and the loaded files are
    not modified.

    With ``A`` the dict returned by :func:`aggregate_trends`, the
    encoded object has keys exactly in the order ``file_count, changes,
    degraded, coverage_delta, score_delta, worst, quality``: the first
    three values are the ints ``A["file_count"]``, ``A["changes"]`` and
    ``A["degraded"]``, the next two are the floats
    ``A["coverage_delta"]`` and ``A["score_delta"]``, ``worst`` is the
    six-item JSON array ``[j, i, b, r, dc, ds]`` derived from
    ``A["worst"]`` and ``quality`` is ``A["quality"]``, all taken
    directly from ``A`` with no recomputation, sorting or additional
    keys.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, exactly as in :func:`serialize_trend`.
    Floats are first rounded with ``round(float(v), 6)`` and negative
    zero is normalized to ``0.0``; ints are written in decimal and
    strings are copied as-is. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    result = aggregate_trends(paths)
    worst = result["worst"]

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    document = {
        "file_count": int(result["file_count"]),
        "changes": int(result["changes"]),
        "degraded": int(result["degraded"]),
        "coverage_delta": rounded_float(result["coverage_delta"]),
        "score_delta": rounded_float(result["score_delta"]),
        "worst": [
            int(worst[0]),
            int(worst[1]),
            int(worst[2]),
            int(worst[3]),
            rounded_float(worst[4]),
            rounded_float(worst[5]),
        ],
        "quality": result["quality"],
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
        raise ValueError(f"trends: could not be serialized to JSON: {exc}") from exc


def serialize_pair_gate_score_summary(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
) -> bytes:
    """Serialize :func:`pair_gate_score_summary` results as UTF-8 JSON bytes.

    Calls :func:`pair_gate_score_summary` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the
    :func:`pair_gate_score_summary` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_score_summary`,
    the encoded object has keys exactly in the order
    ``coverage_product, score_margin, matched, pair_quality,
    quality``: the first four values are taken as-is from
    ``R["summary"]`` (``coverage_product`` and ``score_margin`` are
    floats, ``matched`` is an int and ``pair_quality`` is a string)
    and ``quality`` is ``R["quality"]``, with no recomputation,
    reordering or additional keys.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation and
    no trailing newline. Floats are first rounded with
    ``round(float(v), 6)`` and negative zero is normalized to ``0.0``;
    ints are written in decimal and strings are copied as-is. Any JSON
    or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    result = pair_gate_score_summary(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    summary = result["summary"]

    coverage_product = round(float(summary["coverage_product"]), 6)
    if coverage_product == 0:
        coverage_product = 0.0
    score_margin = round(float(summary["score_margin"]), 6)
    if score_margin == 0:
        score_margin = 0.0

    document = {
        "coverage_product": coverage_product,
        "score_margin": score_margin,
        "matched": int(summary["matched"]),
        "pair_quality": summary["pair_quality"],
        "quality": result["quality"],
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
        raise ValueError(
            f"pair gate score summary: could not be serialized to JSON: {exc}"
        ) from exc


def _format_rendered_value(value):
    """Format one value for :func:`render_pair_gate_score_summary`."""
    if isinstance(value, float):
        return format(0.0 if value == 0 else value, ".6f")
    if isinstance(value, int):
        return str(value)
    return value


def render_pair_gate_score_summary(
    first,
    second,
    tolerances,
    match_tolerance=1.0,
    min_mean_ratio=1.0,
    max_rmse_limit=1.0,
) -> str:
    """Render :func:`pair_gate_score_summary` results as three text lines.

    Calls :func:`pair_gate_score_summary` exactly once with ``first``,
    ``second``, ``tolerances``, ``match_tolerance``,
    ``min_mean_ratio`` and ``max_rmse_limit``, so its validation,
    first-error order, exceptions (propagated unchanged) and index
    prefixes all apply here as well. Inputs and the
    :func:`pair_gate_score_summary` result are not modified.

    With ``R`` the dict returned by :func:`pair_gate_score_summary`,
    returns three lines joined by ``"\\n"`` with no trailing newline::

        QUALITY=<R.quality>
        SUMMARY=coverage_product=<...>;score_margin=<...>;matched=<...>;pair_quality=<...>
        REPORT=first_coverage=<...>;second_coverage=<...>;score=<...>

    where the SUMMARY values are ``R["summary"]["coverage_product"]``,
    ``R["summary"]["score_margin"]``, ``R["summary"]["matched"]`` and
    ``R["summary"]["pair_quality"]``, and the REPORT values are
    ``R["score_report"]["score_report"]["matching"]["first_coverage"]``,
    ``R["score_report"]["score_report"]["matching"]["second_coverage"]``
    and ``R["score_report"]["score_report"]["score"]`` (the inner
    ``score_report`` is the :func:`pair_gate_score` dict). Floats use
    ``format(v, ".6f")`` (negative zero rendered as ``"0.000000"``),
    ints are formatted in decimal and strings are copied as-is.
    """
    result = pair_gate_score_summary(
        first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit
    )
    summary = result["summary"]
    score_report = result["score_report"]["score_report"]
    matching = score_report["matching"]

    quality_line = "QUALITY=" + _format_rendered_value(result["quality"])
    summary_line = "SUMMARY=" + ";".join(
        (
            "coverage_product="
            + _format_rendered_value(summary["coverage_product"]),
            "score_margin=" + _format_rendered_value(summary["score_margin"]),
            "matched=" + _format_rendered_value(summary["matched"]),
            "pair_quality=" + _format_rendered_value(summary["pair_quality"]),
        )
    )
    report_line = "REPORT=" + ";".join(
        (
            "first_coverage="
            + _format_rendered_value(matching["first_coverage"]),
            "second_coverage="
            + _format_rendered_value(matching["second_coverage"]),
            "score=" + _format_rendered_value(score_report["score"]),
        )
    )
    return "\n".join((quality_line, summary_line, report_line))


_PAIR_GATE_SCORE_SUMMARY_KEYS = (
    "coverage_product",
    "score_margin",
    "matched",
    "pair_quality",
    "quality",
)


def _reject_json_constant(name):
    raise ValueError(f"invalid JSON constant {name!r}")


def _from_jsonable(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(float(value), 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, list):
        return tuple(_from_jsonable(item) for item in value)
    if isinstance(value, dict):
        return {key: _from_jsonable(item) for key, item in value.items()}
    return value


def _dump_pair_gate_score_summary(summary):
    try:
        text = json.dumps(
            summary,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"pair gate score summary: could not be serialized to JSON: {exc}"
        ) from exc


def _check_pair_gate_score_summary(summary):
    prefix = "pair gate score summary: "
    if not isinstance(summary, dict):
        raise TypeError("pair gate score summary must be a dict")
    if list(summary.keys()) != list(_PAIR_GATE_SCORE_SUMMARY_KEYS):
        raise TypeError(
            "pair gate score summary keys must be in the order "
            "coverage_product, score_margin, matched, pair_quality, quality"
        )

    coverage_product = summary["coverage_product"]
    if type(coverage_product) is not float:
        raise TypeError(prefix + "coverage_product must be a float")
    if not math.isfinite(coverage_product):
        raise ValueError(prefix + "coverage_product must be finite")
    if not 0 <= coverage_product <= 1:
        raise ValueError(prefix + "coverage_product must be in [0, 1]")
    if coverage_product != round(float(coverage_product), 6):
        raise ValueError(
            prefix + "coverage_product must equal "
            "round(float(coverage_product), 6)"
        )

    score_margin = summary["score_margin"]
    if type(score_margin) is not float:
        raise TypeError(prefix + "score_margin must be a float")
    if not math.isfinite(score_margin):
        raise ValueError(prefix + "score_margin must be finite")
    if not 0 <= score_margin <= 100:
        raise ValueError(prefix + "score_margin must be in [0, 100]")
    if score_margin != round(float(score_margin), 6):
        raise ValueError(
            prefix + "score_margin must equal round(float(score_margin), 6)"
        )

    matched = summary["matched"]
    if type(matched) is not int:
        raise TypeError(prefix + "matched must be a non-bool int")
    if not matched > 0:
        raise ValueError(prefix + "matched must be > 0")

    pair_quality = summary["pair_quality"]
    if type(pair_quality) is not str:
        raise TypeError(prefix + "pair_quality must be a str")
    if pair_quality not in ("pass", "fail"):
        raise ValueError(prefix + "pair_quality must be 'pass' or 'fail'")

    quality = summary["quality"]
    if type(quality) is not str:
        raise TypeError(prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")

    expected_quality = (
        "pass" if pair_quality == "pass" and score_margin == 0.0 else "fail"
    )
    if quality != expected_quality:
        raise ValueError(
            prefix + "quality must be 'pass' only when pair_quality is "
            "'pass' and score_margin is 0.0, and 'fail' otherwise"
        )


def load_pair_gate_score_summary(path) -> dict:
    """Load a :func:`serialize_pair_gate_score_summary`-produced JSON summary.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_pair_gate_score_summary` for the same value:
    compact UTF-8 JSON (``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``) with no BOM and no
    trailing newline. A BOM, a trailing newline, a UTF-8 decoding
    failure or a JSON parsing failure raises ``ValueError``; the
    ``NaN``/``Infinity`` constants and any other non-finite token are
    rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``coverage_product, score_margin, matched,
    pair_quality, quality`` — duplicated, missing or extra keys are
    rejected. ``coverage_product`` and ``score_margin`` must be finite
    non-bool floats in ``[0, 1]`` and ``[0, 100]`` respectively, each
    equal to ``round(float(v), 6)`` with negative zero normalized to
    ``0.0``; ``matched`` must be a non-bool int ``> 0``; ``pair_quality``
    and ``quality`` must be ``"pass"`` or ``"fail"``; and ``quality``
    must be ``"pass"`` only when ``pair_quality`` is ``"pass"`` and
    ``score_margin`` is ``0.0``, and ``"fail"`` otherwise. The file
    bytes must also equal the canonical re-serialization of the decoded
    value byte for byte; any key-order, type, range, relation, parse or
    canonical-byte mismatch raises ``ValueError``.

    Returns the summary as a dict with the keys in the order above;
    the file is never modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    summary = _from_jsonable(parsed)
    try:
        _check_pair_gate_score_summary(summary)
        canonical = _dump_pair_gate_score_summary(summary)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid pair gate score summary: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_pair_gate_score_summary output"
        )

    return summary
