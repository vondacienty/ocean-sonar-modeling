"""Crosspoint accuracy evaluation for overlapping survey lines.

Each crosspoint pairs the two depths observed at the same location;
the depth difference ``r = d1 - d2`` is summarized by its mean bias,
RMSE and maximum absolute value, and the differences within the
tolerance are counted.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["evaluate"]

_FIELDS = ("x", "y", "d1", "d2")


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
