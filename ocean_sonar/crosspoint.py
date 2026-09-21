"""Cross-point accuracy assessment of overlapping survey lines.

Each crossing ``(x, y, d1, d2)`` gives the plan position ``x``/``y`` and
the two independently observed depths ``d1``/``d2`` (metres, both
``>= 0``) at the intersection. The depth discrepancy ``r = d1 - d2``
summarizes the agreement at that cross point; its mean bias, RMSE and
maximum absolute value describe the survey's internal consistency.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["evaluate"]

_FIELDS = ("x", "y", "d1", "d2")


def evaluate(crossings, tolerance=0.5):
    """Evaluate depth agreement at survey cross points.

    ``crossings`` is a non-empty list/tuple whose items are four-element
    lists/tuples ``(x, y, d1, d2)``. Every field must be a finite
    non-bool int/float and ``d1``/``d2`` must be ``>= 0``.
    ``tolerance`` must be a finite non-bool int/float ``> 0``.

    With ``r = d1 - d2`` for each crossing and ``n`` their count, the
    metrics are computed in this order: the mean bias
    ``math.fsum(r) / n``, the RMSE ``sqrt(math.fsum(r*r) / n)``, the
    maximum ``abs(r)``, and the number of crossings with
    ``abs(r) <= tolerance``.

    Validation order (first error wins): the ``crossings`` container,
    its non-emptiness, then per crossing the item container, its length
    and the fields ``x``, ``y``, ``d1``, ``d2`` in that order, then
    ``tolerance`` (type, finiteness, positivity). Container and value
    type errors (including ``bool``) raise ``TypeError``; an empty
    container, a non-four-element item, a non-finite value, a negative
    depth or ``tolerance <= 0`` raise ``ValueError``. Item error
    messages are prefixed with ``"crossings[i]: "``.

    Returns a dict with keys in the order ``count``, ``bias``,
    ``rmse``, ``max_abs``, ``within_tolerance``, ``quality``.
    ``count`` and ``within_tolerance`` are ints; ``bias``, ``rmse`` and
    ``max_abs`` are floats rounded to 6 decimals (negative zero
    normalized to ``0.0``). ``quality`` is ``"pass"`` when every
    crossing satisfies ``abs(r) <= tolerance`` and ``"fail"``
    otherwise. Inputs are not modified.
    """
    if not isinstance(crossings, (list, tuple)):
        raise TypeError("crossings must be a list or tuple")
    if len(crossings) == 0:
        raise ValueError("crossings must be non-empty")

    for i in range(len(crossings)):
        crossing = crossings[i]
        prefix = f"crossings[{i}]: "
        if not isinstance(crossing, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(crossing) != 4:
            raise ValueError(prefix + "must have 4 elements")
        for name, value in zip(_FIELDS, crossing):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
            if name in ("d1", "d2") and not value >= 0:
                raise ValueError(prefix + f"{name} must be >= 0")

    if not _is_real_number(tolerance):
        raise TypeError("tolerance must be a non-bool int or float")
    if not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite")
    if not tolerance > 0:
        raise ValueError("tolerance must be > 0")

    residuals = [d1 - d2 for _x, _y, d1, d2 in crossings]
    n = len(residuals)

    bias = math.fsum(residuals) / n
    rmse = math.sqrt(math.fsum(r * r for r in residuals) / n)
    max_abs = max(abs(r) for r in residuals)
    within_tolerance = sum(1 for r in residuals if abs(r) <= tolerance)

    rounded = []
    for value in (bias, rmse, max_abs):
        value = round(float(value), 6)
        rounded.append(0.0 if value == 0 else value)

    return {
        "count": n,
        "bias": rounded[0],
        "rmse": rounded[1],
        "max_abs": rounded[2],
        "within_tolerance": within_tolerance,
        "quality": "pass" if within_tolerance == n else "fail",
    }
