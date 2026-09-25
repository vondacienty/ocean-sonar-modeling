"""Terrain analysis of a gridded bathymetric surface.

Given a regular grid of cell mean depths (as produced by
:func:`ocean_sonar.grid.build`), derive per-cell slope and roughness.
Slope is the gradient angle in degrees from the four direct neighbours;
roughness is the ``max - min`` spread of the non-empty means in the
boundary-clipped 3x3 neighbourhood.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = [
    "analyze",
    "analyze_layers",
    "breakdown",
    "compare_layers",
    "cross_scale",
    "dashboard",
    "metrics",
    "quality",
    "scale_dashboard",
    "scale_profile",
    "scale_report",
    "stats",
    "trend",
]


def _round6(value):
    result = round(float(value), 6)
    if result == 0:
        result = 0.0
    return result


def _validated_means(r, nx, ny, cells):
    """Validate a depth grid exactly as :func:`analyze` does.

    Returns a list with one entry per cell: the cell mean for
    non-empty cells (``count > 0``) and ``None`` for empty ones.
    """
    if not _is_real_number(r):
        raise TypeError("r must be a non-bool int or float")
    if not math.isfinite(r):
        raise ValueError("r must be finite")
    if not r > 0:
        raise ValueError("r must be > 0")

    for name, value in (("nx", nx), ("ny", ny)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be a non-bool int")
        if not value > 0:
            raise ValueError(f"{name} must be > 0")

    if not isinstance(cells, (list, tuple)):
        raise TypeError("cells must be a list or tuple")
    if len(cells) != nx * ny:
        raise ValueError("cells must have nx * ny elements")

    for i in range(len(cells)):
        prefix = f"cells[{i}]: "
        cell = cells[i]
        if not isinstance(cell, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        count, mean = cell
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError(prefix + "count must be a non-bool int")
        if not count >= 0:
            raise ValueError(prefix + "count must be >= 0")
        if count == 0:
            if mean is not None:
                raise ValueError(prefix + "mean must be None when count is 0")
        else:
            if not _is_real_number(mean):
                raise TypeError(prefix + "mean must be a non-bool int or float")
            if not math.isfinite(mean):
                raise ValueError(prefix + "mean must be finite")
            if not mean >= 0:
                raise ValueError(prefix + "mean must be >= 0")

    return [cell[1] if cell[0] > 0 else None for cell in cells]


def _validate_scale_grid(name, grid):
    """Validate a four-element ``(r, nx, ny, cells)`` grid.

    Cell errors are prefixed with ``"<name>.cells[j]: "``. Returns
    ``(r, nx, ny, means)`` where ``means`` has one entry per cell, the
    cell mean for non-empty cells and ``None`` for empty ones.
    """
    if not isinstance(grid, (list, tuple)):
        raise TypeError(f"{name} must be a list or tuple")
    if len(grid) != 4:
        raise ValueError(f"{name} must have 4 elements")
    r, nx, ny, cells = grid

    if not _is_real_number(r):
        raise TypeError(f"{name}.r must be a non-bool int or float")
    if not math.isfinite(r):
        raise ValueError(f"{name}.r must be finite")
    if not r > 0:
        raise ValueError(f"{name}.r must be > 0")

    for axis, value in (("nx", nx), ("ny", ny)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name}.{axis} must be a non-bool int")
        if not value > 0:
            raise ValueError(f"{name}.{axis} must be > 0")

    if not isinstance(cells, (list, tuple)):
        raise TypeError(f"{name}.cells must be a list or tuple")
    if len(cells) != nx * ny:
        raise ValueError(f"{name}.cells must have nx * ny elements")

    means = []
    for j in range(len(cells)):
        prefix = f"{name}.cells[{j}]: "
        cell = cells[j]
        if not isinstance(cell, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        count, mean = cell
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError(prefix + "count must be a non-bool int")
        if not count >= 0:
            raise ValueError(prefix + "count must be >= 0")
        if count == 0:
            if mean is not None:
                raise ValueError(prefix + "mean must be None when count is 0")
            means.append(None)
        else:
            if not _is_real_number(mean):
                raise TypeError(prefix + "mean must be a non-bool int or float")
            if not math.isfinite(mean):
                raise ValueError(prefix + "mean must be finite")
            if not mean >= 0:
                raise ValueError(prefix + "mean must be >= 0")
            means.append(mean)

    return r, nx, ny, means


def analyze(r, nx, ny, cells):
    """Compute per-cell slope and roughness for a regular depth grid.

    ``r`` is the cell size, a finite non-bool int/float with ``r > 0``.
    ``nx``/``ny`` are non-bool positive ints. ``cells`` is a list/tuple
    of length ``nx * ny`` ordered by ``y`` then ``x``; each item is a
    two-element list/tuple ``(count, mean)`` where ``count`` is a
    non-bool non-negative int, ``mean`` is exactly ``None`` when
    ``count == 0`` and a finite non-bool int/float ``>= 0`` otherwise.

    For a non-empty cell, roughness is ``max - min`` over the non-empty
    means of the 3x3 neighbourhood clipped to the grid bounds. With
    left/right/down/up neighbour means ``L``/``R``/``D``/``U`` all
    present and non-empty, slope is
    ``degrees(atan(hypot((R - L) / (2 * r), (U - D) / (2 * r))))``;
    otherwise slope is ``None``. Empty cells are fixed as
    ``(None, None)``.

    Validation follows the signature parameter order and then grid
    order, stopping at the first error: type mismatches (including
    bool) raise ``TypeError``, all other constraint errors raise
    ``ValueError``. Cell errors are prefixed with ``"cells[i]: "``.

    Returns a tuple in the same order and length as ``cells`` of
    ``(slope, roughness)`` pairs; non-``None`` values are rounded with
    ``round(float(v), 6)`` (negative zero normalized to ``0.0``). All
    computation uses the unrounded means; inputs are not modified.
    """
    means = _validated_means(r, nx, ny, cells)

    def mean_at(ix, iy):
        if 0 <= ix < nx and 0 <= iy < ny:
            return means[iy * nx + ix]
        return None

    result = []
    for iy in range(ny):
        for ix in range(nx):
            center = means[iy * nx + ix]
            if center is None:
                result.append((None, None))
                continue

            low = high = center
            for jy in range(max(0, iy - 1), min(ny, iy + 2)):
                for jx in range(max(0, ix - 1), min(nx, ix + 2)):
                    value = means[jy * nx + jx]
                    if value is None:
                        continue
                    if value < low:
                        low = value
                    if value > high:
                        high = value
            roughness = _round6(high - low)

            left = mean_at(ix - 1, iy)
            right = mean_at(ix + 1, iy)
            down = mean_at(ix, iy - 1)
            up = mean_at(ix, iy + 1)
            if None in (left, right, down, up):
                slope = None
            else:
                slope = _round6(
                    math.degrees(
                        math.atan(
                            math.hypot(
                                (right - left) / (2 * r),
                                (up - down) / (2 * r),
                            )
                        )
                    )
                )
            result.append((slope, roughness))
    return tuple(result)


def cross_scale(fine, coarse, tolerance=0.5):
    """Compare a fine depth grid against a coarser one block by block.

    ``fine`` and ``coarse`` are each a four-element list/tuple
    ``(r, nx, ny, cells)`` with the same constraints as the parameters
    of :func:`analyze`; cell errors are prefixed with
    ``"fine.cells[i]: "`` and ``"coarse.cells[i]: "``.

    Validation follows the order ``fine``, ``coarse``, ``tolerance``
    and then the scale relations, stopping at the first error: the
    fine resolution must be strictly less than the coarse one,
    ``q = coarse.r / fine.r`` must be positive with ``q.is_integer()``,
    and the fine dimensions must be exactly ``int(q)`` times the coarse
    dimensions (``fine.nx == int(q) * coarse.nx`` and likewise for
    ``ny``). ``tolerance`` is a finite non-bool int/float ``> 0``.
    Type mismatches (including bool) raise ``TypeError`` and all other
    constraint errors raise ``ValueError``.

    Each non-empty coarse cell is compared with the ``q`` x ``q`` block
    of fine cells that maps onto it; the block mean is
    ``math.fsum`` of the non-empty fine means divided by their number.
    A coarse cell with a mean and at least one non-empty fine cell is
    ``matched``; a non-empty coarse cell whose block has no fine means
    is ``missing``; empty coarse cells are ignored.

    For each matched block, ``R = coarse_mean - block_mean`` and
    ``k = len(R)``. When ``k > 0``, ``bias = fsum(R) / k``,
    ``rmse = sqrt(fsum(r * r for r in R) / k)`` and
    ``max_abs = max(abs(r) for r in R)``; when ``k == 0`` all three are
    ``0.0``. ``within_tolerance`` counts the residuals with
    ``abs(R) <= tolerance``.

    Returns a dict with keys in the order ``matched, missing, bias,
    rmse, max_abs, within_tolerance, quality``: the counts are ints and
    every float is rounded with ``round(float(v), 6)`` (negative zero
    normalized to ``0.0``). ``quality`` is ``"pass"`` only when
    ``missing == 0``, ``matched > 0`` and every residual is within
    tolerance, and ``"fail"`` otherwise. Computation uses the unrounded
    means; inputs are not modified.
    """
    fine_r, fine_nx, fine_ny, fine_means = _validate_scale_grid("fine", fine)
    coarse_r, coarse_nx, coarse_ny, coarse_means = _validate_scale_grid(
        "coarse", coarse
    )

    if not _is_real_number(tolerance):
        raise TypeError("tolerance must be a non-bool int or float")
    if not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite")
    if not tolerance > 0:
        raise ValueError("tolerance must be > 0")

    if not fine_r < coarse_r:
        raise ValueError("coarse.r must be strictly greater than fine.r")

    q = coarse_r / fine_r
    if not q > 0 or not float(q).is_integer():
        raise ValueError("coarse.r / fine.r must be a positive integer")
    q = int(q)

    if fine_nx != q * coarse_nx or fine_ny != q * coarse_ny:
        raise ValueError(
            "fine dimensions must be q times the coarse dimensions"
        )

    matched = 0
    missing = 0
    residuals = []
    for cy in range(coarse_ny):
        for cx in range(coarse_nx):
            coarse_mean = coarse_means[cy * coarse_nx + cx]
            if coarse_mean is None:
                continue

            block_values = []
            for by in range(q):
                fy = cy * q + by
                for bx in range(q):
                    fx = cx * q + bx
                    value = fine_means[fy * fine_nx + fx]
                    if value is not None:
                        block_values.append(value)

            if not block_values:
                missing += 1
                continue

            block_mean = math.fsum(block_values) / len(block_values)
            matched += 1
            residuals.append(coarse_mean - block_mean)

    k = len(residuals)
    if k > 0:
        bias = _round6(math.fsum(residuals) / k)
        rmse = _round6(
            math.sqrt(math.fsum(r * r for r in residuals) / k)
        )
        max_abs = _round6(max(abs(r) for r in residuals))
        within = sum(1 for r in residuals if abs(r) <= tolerance)
    else:
        bias = rmse = max_abs = 0.0
        within = 0

    quality = (
        "pass"
        if missing == 0 and matched > 0 and within == matched
        else "fail"
    )

    return {
        "matched": int(matched),
        "missing": int(missing),
        "bias": bias,
        "rmse": rmse,
        "max_abs": max_abs,
        "within_tolerance": int(within),
        "quality": quality,
    }


def scale_profile(fine, coarse, tolerances):
    """Sweep :func:`cross_scale` over several tolerance values.

    ``fine`` and ``coarse`` have exactly the same constraints as in
    :func:`cross_scale`; they are validated first, in that order, with
    the same exception types and ``"fine.cells[i]: "`` /
    ``"coarse.cells[i]: "`` prefixes, and the scale relations are
    checked by :func:`cross_scale` as well.

    ``tolerances`` is a non-empty list/tuple validated after ``fine``
    and ``coarse``: first the container type and non-emptiness, then
    each item ``i`` in order. Every item must be a finite non-bool
    int/float ``> 0``; type mismatches (including bool) raise
    ``TypeError`` and all other constraint errors raise
    ``ValueError``, prefixed with ``"tolerances[i]: "``. The first
    error stops the call.

    :func:`cross_scale` is called once per tolerance as
    ``cross_scale(fine, coarse, t)`` in ascending ``(t, i)`` order,
    where the original index ``i`` breaks tolerance ties; its
    exceptions propagate unchanged and inputs are not modified.

    The sorted results form ``curve``, a tuple of one dict per
    tolerance with keys in the order ``tolerance, matched, missing,
    bias, rmse, max_abs, within_tolerance, quality``: ``tolerance`` is
    ``round(float(t), 6)`` (negative zero normalized to ``0.0``) and
    the other fields are copied from the :func:`cross_scale` result.

    With ``r_i = within_tolerance / matched`` for curve item ``i``
    (``0.0`` when ``matched == 0``), ``monotonic`` is ``True`` iff
    ``within_tolerance`` is non-decreasing and ``missing`` is
    non-increasing along the curve; ``first_pass_tolerance`` is the
    tolerance of the first curve item whose ``quality`` is ``"pass"``,
    or ``None``. ``area`` is ``0.0`` for fewer than two curve items,
    otherwise
    ``round(sum((t_i - t_{i-1}) * (r_i + r_{i-1}) / 2), 6)`` over the
    unrounded sorted tolerances (negative zero normalized to ``0.0``).

    ``quality`` is ``"pass"`` only when every curve item has
    ``missing == 0``, every item's ``quality`` is ``"pass"``, the curve
    is monotonic and a first passing tolerance exists, and ``"fail"``
    otherwise.

    Returns a dict with keys in the order ``curve, monotonic,
    first_pass_tolerance, area, quality``: ``curve`` is a tuple,
    ``monotonic`` is a bool, ``first_pass_tolerance`` is a float or
    ``None``, ``area`` is a float and ``quality`` is a str.
    """
    _validate_scale_grid("fine", fine)
    _validate_scale_grid("coarse", coarse)

    if not isinstance(tolerances, (list, tuple)):
        raise TypeError("tolerances must be a list or tuple")
    if len(tolerances) == 0:
        raise ValueError("tolerances must not be empty")

    checked = []
    for i in range(len(tolerances)):
        prefix = f"tolerances[{i}]: "
        value = tolerances[i]
        if not _is_real_number(value):
            raise TypeError(prefix + "must be a non-bool int or float")
        if not math.isfinite(value):
            raise ValueError(prefix + "must be finite")
        if not value > 0:
            raise ValueError(prefix + "must be > 0")
        checked.append(value)

    order = sorted(range(len(checked)), key=lambda i: (checked[i], i))

    curve = []
    ratios = []
    for i in order:
        tolerance = checked[i]
        result = cross_scale(fine, coarse, tolerance)
        matched = result["matched"]
        missing = result["missing"]
        within = result["within_tolerance"]
        ratios.append(within / matched if matched > 0 else 0)
        curve.append(
            {
                "tolerance": _round6(tolerance),
                "matched": matched,
                "missing": missing,
                "bias": result["bias"],
                "rmse": result["rmse"],
                "max_abs": result["max_abs"],
                "within_tolerance": within,
                "quality": result["quality"],
            }
        )
    curve = tuple(curve)

    monotonic = all(
        curve[i]["within_tolerance"] >= curve[i - 1]["within_tolerance"]
        and curve[i]["missing"] <= curve[i - 1]["missing"]
        for i in range(1, len(curve))
    )

    first_pass_tolerance = None
    for item in curve:
        if item["quality"] == "pass":
            first_pass_tolerance = item["tolerance"]
            break

    m = len(curve)
    if m < 2:
        area = 0.0
    else:
        sorted_tolerances = [checked[i] for i in order]
        area = _round6(
            math.fsum(
                (sorted_tolerances[i] - sorted_tolerances[i - 1])
                * (ratios[i] + ratios[i - 1])
                / 2
                for i in range(1, m)
            )
        )

    grade = (
        "pass"
        if all(item["missing"] == 0 for item in curve)
        and all(item["quality"] == "pass" for item in curve)
        and monotonic
        and first_pass_tolerance is not None
        else "fail"
    )

    return {
        "curve": curve,
        "monotonic": monotonic,
        "first_pass_tolerance": first_pass_tolerance,
        "area": area,
        "quality": grade,
    }


_SCALE_RECORD_KEYS = ("matched", "missing", "within_tolerance", "quality")
_SCALE_DASHBOARD_SUMMARY_KEYS = (
    "tolerance_count",
    "pass_count",
    "fail_count",
    "matched_total",
    "missing_total",
    "within_total",
    "within_ratio",
    "quality_score",
)


def scale_dashboard(records) -> dict:
    """Aggregate per-tolerance :func:`cross_scale` records into one dashboard.

    ``records`` must be a non-empty tuple; a non-tuple container raises
    ``TypeError`` and an empty tuple raises ``ValueError``. Each item
    ``i`` must be a dict with keys exactly in the order
    ``matched, missing, within_tolerance, quality``: the first three
    fields are non-bool non-negative ints with
    ``within_tolerance <= matched``, and ``quality`` is the string
    ``"pass"`` or ``"fail"``. Items are validated in order, stopping at
    the first error; item errors are prefixed with ``"records[i]: "``.
    Container, key-order and field-type mismatches (including bool)
    raise ``TypeError``; emptiness, range and enum errors raise
    ``ValueError``. The input is not modified.

    With ``m`` the number of records, ``p`` the number of ``"pass"``
    records and ``M``/``N``/``W`` the respective sums of ``matched``,
    ``missing`` and ``within_tolerance``, ``R = W / M`` when
    ``M > 0`` and ``0.0`` otherwise.

    Returns a dict with keys in the order ``summary, quality``.
    ``summary`` has keys in the order ``tolerance_count, pass_count,
    fail_count, matched_total, missing_total, within_total,
    within_ratio, quality_score``: the first six values are ints
    (``m``, ``p``, ``m - p``, ``M``, ``N`` and ``W``) and the last two
    are the floats ``round(R, 6)`` and
    ``round(100 * R * (1 if p == m else 0), 6)`` (negative zero
    normalized to ``0.0``). ``quality`` is ``"pass"`` only when
    ``p == m``, ``N == 0`` and ``W == M``, and ``"fail"`` otherwise.
    """
    if not isinstance(records, tuple):
        raise TypeError("records must be a tuple")
    if len(records) == 0:
        raise ValueError("records must not be empty")

    m = len(records)
    p = 0
    M = N = W = 0
    for i in range(m):
        prefix = f"records[{i}]: "
        record = records[i]
        if not isinstance(record, dict):
            raise TypeError(prefix + "must be a dict")
        if list(record.keys()) != list(_SCALE_RECORD_KEYS):
            raise TypeError(
                prefix
                + "keys must be in the order matched, missing, "
                "within_tolerance, quality"
            )

        matched = record["matched"]
        if type(matched) is not int:
            raise TypeError(prefix + "matched must be a non-bool int")
        if not matched >= 0:
            raise ValueError(prefix + "matched must be >= 0")

        missing = record["missing"]
        if type(missing) is not int:
            raise TypeError(prefix + "missing must be a non-bool int")
        if not missing >= 0:
            raise ValueError(prefix + "missing must be >= 0")

        within = record["within_tolerance"]
        if type(within) is not int:
            raise TypeError(prefix + "within_tolerance must be a non-bool int")
        if not within >= 0:
            raise ValueError(prefix + "within_tolerance must be >= 0")
        if not within <= matched:
            raise ValueError(prefix + "within_tolerance must be <= matched")

        grade = record["quality"]
        if type(grade) is not str:
            raise TypeError(prefix + "quality must be a str")
        if grade not in ("pass", "fail"):
            raise ValueError(prefix + "quality must be 'pass' or 'fail'")

        if grade == "pass":
            p += 1
        M += matched
        N += missing
        W += within

    R = W / M if M > 0 else 0.0
    within_ratio = _round6(R)
    quality_score = _round6(100 * R * (1 if p == m else 0))

    quality = "pass" if p == m and N == 0 and W == M else "fail"

    return {
        "summary": {
            "tolerance_count": int(m),
            "pass_count": int(p),
            "fail_count": int(m - p),
            "matched_total": int(M),
            "missing_total": int(N),
            "within_total": int(W),
            "within_ratio": within_ratio,
            "quality_score": quality_score,
        },
        "quality": quality,
    }


def scale_report(fine, coarse, tolerances) -> dict:
    """Combine :func:`scale_profile` and :func:`scale_dashboard` into one report.

    ``fine``, ``coarse`` and ``tolerances`` have exactly the same
    constraints, validation order, exception types and
    ``"fine.cells[i]: "`` / ``"coarse.cells[i]: "`` /
    ``"tolerances[i]: "`` prefixes as in :func:`scale_profile`; all
    validation is carried out by that function. Type mismatches
    (including bool) raise ``TypeError`` and all other constraint
    errors raise ``ValueError``.

    :func:`scale_profile` is called exactly once as
    ``scale_profile(fine, coarse, tolerances)``; its exceptions
    propagate unchanged and inputs are not modified. From its ``curve``
    a new tuple is built in the same order, one dict per item with keys
    in the order ``matched, missing, within_tolerance, quality`` and
    the four values copied as-is; :func:`scale_dashboard` is then
    called exactly once with that tuple.

    Returns a dict with keys in the order ``profile, dashboard,
    quality``: ``profile`` and ``dashboard`` are the objects returned
    by the two calls as-is, and ``quality`` is ``"pass"`` only when
    both their ``quality`` values are ``"pass"``, and ``"fail"``
    otherwise.
    """
    profile = scale_profile(fine, coarse, tolerances)

    records = tuple(
        {
            "matched": item["matched"],
            "missing": item["missing"],
            "within_tolerance": item["within_tolerance"],
            "quality": item["quality"],
        }
        for item in profile["curve"]
    )
    dashboard = scale_dashboard(records)

    grade = (
        "pass"
        if profile["quality"] == "pass" and dashboard["quality"] == "pass"
        else "fail"
    )

    return {
        "profile": profile,
        "dashboard": dashboard,
        "quality": grade,
    }


def metrics(r, nx, ny, cells):
    """Compute coverage and depth/volume summary for a regular depth grid.

    Inputs, the shape of ``cells`` and the validation order and
    exception types are exactly as for :func:`analyze`; cell errors are
    prefixed with ``"cells[i]: "``.

    Only non-empty cells (``count > 0``) contribute. With ``A = r * r``
    the per-cell area and ``valid`` the number of non-empty cells,
    ``coverage`` is ``valid / (nx * ny)``, ``min_depth``/``max_depth``
    are the smallest/largest cell means and ``mean_depth`` is
    ``math.fsum(means) / valid``; ``volume`` is
    ``math.fsum(mean * A for mean in means)``. When there are no
    non-empty cells, the three depth values are ``None`` and the volume
    is ``0.0``.

    Returns a dict with keys in the order ``resolution, nx, ny, total,
    valid, coverage, min_depth, max_depth, mean_depth, volume``:
    ``resolution`` is ``r``, ``total``/``valid`` are ints and the other
    fields are floats. Every non-``None`` value is rounded with
    ``round(float(v), 6)`` (negative zero normalized to ``0.0``);
    computations use the unrounded means. Inputs are not modified.
    """
    means = [m for m in _validated_means(r, nx, ny, cells) if m is not None]

    total = int(nx * ny)
    valid = len(means)
    coverage = valid / total
    if valid == 0:
        min_depth = max_depth = mean_depth = None
        volume = 0.0
    else:
        area = r * r
        min_depth = _round6(min(means))
        max_depth = _round6(max(means))
        mean_depth = _round6(math.fsum(means) / valid)
        volume = _round6(math.fsum(mean * area for mean in means))

    return {
        "resolution": _round6(r),
        "nx": int(nx),
        "ny": int(ny),
        "total": total,
        "valid": valid,
        "coverage": _round6(coverage),
        "min_depth": min_depth,
        "max_depth": max_depth,
        "mean_depth": mean_depth,
        "volume": volume,
    }


def stats(r, nx, ny, cells):
    """Summarize the slope/roughness analysis of a regular depth grid.

    Inputs, the shape of ``cells`` and the validation order and
    exception types are exactly as for :func:`analyze`; cell errors are
    prefixed with ``"cells[i]: "``. :func:`analyze` is called exactly
    once and its exceptions propagate unchanged; inputs are not
    modified.

    With ``A`` the tuple returned by :func:`analyze`, ``valid`` is the
    number of non-empty cells, ``slope_valid`` the number of entries of
    ``A`` whose slope is not ``None`` and ``roughness_valid`` the
    number whose roughness is not ``None``. ``min_slope``/
    ``max_slope``/``mean_slope`` and ``min_roughness``/
    ``max_roughness``/``mean_roughness`` summarize the non-``None``
    slopes and roughnesses of ``A``, with means computed via
    ``math.fsum``; when the corresponding count is zero all three
    values of that metric are ``None``.

    Returns a dict with keys in the order ``resolution, total, valid,
    slope_valid, roughness_valid, min_slope, max_slope, mean_slope,
    min_roughness, max_roughness, mean_roughness``: ``total`` is
    ``nx * ny``, the counts are ints and every non-``None`` numeric
    value is rounded with ``round(float(v), 6)`` (negative zero
    normalized to ``0.0``).
    """
    analysis = analyze(r, nx, ny, cells)

    valid = sum(1 for cell in cells if cell[0] > 0)
    slopes = [slope for slope, _ in analysis if slope is not None]
    roughnesses = [roughness for _, roughness in analysis if roughness is not None]

    if slopes:
        min_slope = _round6(min(slopes))
        max_slope = _round6(max(slopes))
        mean_slope = _round6(math.fsum(slopes) / len(slopes))
    else:
        min_slope = max_slope = mean_slope = None

    if roughnesses:
        min_roughness = _round6(min(roughnesses))
        max_roughness = _round6(max(roughnesses))
        mean_roughness = _round6(math.fsum(roughnesses) / len(roughnesses))
    else:
        min_roughness = max_roughness = mean_roughness = None

    return {
        "resolution": _round6(r),
        "total": int(nx * ny),
        "valid": valid,
        "slope_valid": len(slopes),
        "roughness_valid": len(roughnesses),
        "min_slope": min_slope,
        "max_slope": max_slope,
        "mean_slope": mean_slope,
        "min_roughness": min_roughness,
        "max_roughness": max_roughness,
        "mean_roughness": mean_roughness,
    }


def analyze_layers(layers):
    """Analyze several depth grids in one call.

    ``layers`` is a non-empty list/tuple whose items, in input order,
    are four-element list/tuples ``(r, nx, ny, cells)`` with the same
    constraints as the parameters of :func:`analyze`.

    Validation order: the outer container, non-emptiness, then per
    layer ``i`` its container, length, ``r``, ``nx``, ``ny``, the
    ``cells`` container and length, and finally per cell ``j`` its
    container, length, ``count`` and ``mean``; the first error stops
    the call. Container/type mismatches (including bool) raise
    ``TypeError``, all other constraint errors raise ``ValueError``.
    Errors are prefixed with ``"layers[i]: "`` or
    ``"layers[i].cells[j]: "``.

    Each layer is passed to :func:`analyze` unchanged. Returns a tuple
    in input order of dicts with keys ``resolution``, ``nx``, ``ny``,
    ``analysis`` (in that order): ``resolution`` is
    ``round(float(r), 6)`` (negative zero normalized to ``0.0``),
    ``nx``/``ny`` are ints and ``analysis`` is the tuple returned by
    :func:`analyze` as-is. Inputs are not modified.
    """
    if not isinstance(layers, (list, tuple)):
        raise TypeError("layers must be a list or tuple")
    if len(layers) == 0:
        raise ValueError("layers must not be empty")

    results = []
    for i in range(len(layers)):
        prefix = f"layers[{i}]: "
        layer = layers[i]
        if not isinstance(layer, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(layer) != 4:
            raise ValueError(prefix + "must have 4 elements")
        r, nx, ny, cells = layer

        if not _is_real_number(r):
            raise TypeError(prefix + "r must be a non-bool int or float")
        if not math.isfinite(r):
            raise ValueError(prefix + "r must be finite")
        if not r > 0:
            raise ValueError(prefix + "r must be > 0")

        for name, value in (("nx", nx), ("ny", ny)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not value > 0:
                raise ValueError(prefix + f"{name} must be > 0")

        if not isinstance(cells, (list, tuple)):
            raise TypeError(prefix + "cells must be a list or tuple")
        if len(cells) != nx * ny:
            raise ValueError(prefix + "cells must have nx * ny elements")

        for j in range(len(cells)):
            cell_prefix = f"layers[{i}].cells[{j}]: "
            cell = cells[j]
            if not isinstance(cell, (list, tuple)):
                raise TypeError(cell_prefix + "must be a list or tuple")
            if len(cell) != 2:
                raise ValueError(cell_prefix + "must have 2 elements")
            count, mean = cell
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError(cell_prefix + "count must be a non-bool int")
            if not count >= 0:
                raise ValueError(cell_prefix + "count must be >= 0")
            if count == 0:
                if mean is not None:
                    raise ValueError(
                        cell_prefix + "mean must be None when count is 0"
                    )
            else:
                if not _is_real_number(mean):
                    raise TypeError(
                        cell_prefix + "mean must be a non-bool int or float"
                    )
                if not math.isfinite(mean):
                    raise ValueError(cell_prefix + "mean must be finite")
                if not mean >= 0:
                    raise ValueError(cell_prefix + "mean must be >= 0")

        results.append(
            {
                "resolution": _round6(r),
                "nx": int(nx),
                "ny": int(ny),
                "analysis": analyze(r, nx, ny, cells),
            }
        )
    return tuple(results)


def compare_layers(layers, slope_limit=5.0, roughness_limit=1.0):
    """Compare the :func:`stats` summaries of several depth grids.

    ``layers`` is a non-empty list/tuple whose items, in input order,
    are four-element list/tuples ``(r, nx, ny, cells)`` with the same
    constraints as the parameters of :func:`analyze`; the ``r`` values
    must additionally be strictly increasing in layer order.

    Validation order: the outer container, non-emptiness and the
    per-layer/per-cell checks exactly as in :func:`analyze_layers`
    (with the same ``"layers[i]: "`` /
    ``"layers[i].cells[j]: "`` prefixes), then the strictly increasing
    ``r`` values, then ``slope_limit`` and ``roughness_limit``; the
    first error stops the call. The limits are finite non-bool
    ints/floats ``> 0``. Type mismatches (including bool) raise
    ``TypeError``, all other constraint errors raise ``ValueError``.

    Each layer is passed to :func:`stats` exactly once, in input order;
    :func:`analyze_layers` is not called. Exceptions from :func:`stats`
    propagate unchanged and inputs are not modified.

    Returns a dict with keys in the order ``layers, slope_deltas,
    roughness_deltas, stable``: ``layers`` is a tuple of the dicts
    returned by :func:`stats`, and each delta list has ``n - 1``
    entries. Entry ``i`` compares layers ``i + 1`` and ``i`` using
    their ``mean_slope``/``mean_roughness`` values; it is ``None`` when
    either mean is ``None`` and ``round(float(next - prev), 6)``
    otherwise (negative zero normalized to ``0.0``). ``stable`` is
    ``True`` when every non-``None`` slope delta has absolute value
    ``<= slope_limit`` and every non-``None`` roughness delta has
    absolute value ``<= roughness_limit`` (including when there is
    nothing to compare), and ``False`` otherwise.
    """
    if not isinstance(layers, (list, tuple)):
        raise TypeError("layers must be a list or tuple")
    if len(layers) == 0:
        raise ValueError("layers must not be empty")

    validated = []
    for i in range(len(layers)):
        prefix = f"layers[{i}]: "
        layer = layers[i]
        if not isinstance(layer, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(layer) != 4:
            raise ValueError(prefix + "must have 4 elements")
        r, nx, ny, cells = layer

        if not _is_real_number(r):
            raise TypeError(prefix + "r must be a non-bool int or float")
        if not math.isfinite(r):
            raise ValueError(prefix + "r must be finite")
        if not r > 0:
            raise ValueError(prefix + "r must be > 0")

        for name, value in (("nx", nx), ("ny", ny)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not value > 0:
                raise ValueError(prefix + f"{name} must be > 0")

        if not isinstance(cells, (list, tuple)):
            raise TypeError(prefix + "cells must be a list or tuple")
        if len(cells) != nx * ny:
            raise ValueError(prefix + "cells must have nx * ny elements")

        for j in range(len(cells)):
            cell_prefix = f"layers[{i}].cells[{j}]: "
            cell = cells[j]
            if not isinstance(cell, (list, tuple)):
                raise TypeError(cell_prefix + "must be a list or tuple")
            if len(cell) != 2:
                raise ValueError(cell_prefix + "must have 2 elements")
            count, mean = cell
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError(cell_prefix + "count must be a non-bool int")
            if not count >= 0:
                raise ValueError(cell_prefix + "count must be >= 0")
            if count == 0:
                if mean is not None:
                    raise ValueError(
                        cell_prefix + "mean must be None when count is 0"
                    )
            else:
                if not _is_real_number(mean):
                    raise TypeError(
                        cell_prefix + "mean must be a non-bool int or float"
                    )
                if not math.isfinite(mean):
                    raise ValueError(cell_prefix + "mean must be finite")
                if not mean >= 0:
                    raise ValueError(cell_prefix + "mean must be >= 0")

        validated.append((r, nx, ny, cells))

    for i in range(1, len(validated)):
        if not validated[i][0] > validated[i - 1][0]:
            raise ValueError(
                f"layers[{i}]: r must be strictly greater than the "
                f"previous layer's r"
            )

    for name, value in (
        ("slope_limit", slope_limit),
        ("roughness_limit", roughness_limit),
    ):
        if not _is_real_number(value):
            raise TypeError(f"{name} must be a non-bool int or float")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if not value > 0:
            raise ValueError(f"{name} must be > 0")

    summaries = tuple(stats(r, nx, ny, cells) for r, nx, ny, cells in validated)

    slope_deltas = []
    roughness_deltas = []
    for i in range(1, len(summaries)):
        prev, nxt = summaries[i - 1], summaries[i]

        prev_slope, next_slope = prev["mean_slope"], nxt["mean_slope"]
        if prev_slope is None or next_slope is None:
            slope_deltas.append(None)
        else:
            slope_deltas.append(_round6(next_slope - prev_slope))

        prev_roughness, next_roughness = (
            prev["mean_roughness"],
            nxt["mean_roughness"],
        )
        if prev_roughness is None or next_roughness is None:
            roughness_deltas.append(None)
        else:
            roughness_deltas.append(_round6(next_roughness - prev_roughness))

    stable = True
    for slope_delta, roughness_delta in zip(slope_deltas, roughness_deltas):
        if slope_delta is not None and abs(slope_delta) > slope_limit:
            stable = False
            break
        if (
            roughness_delta is not None
            and abs(roughness_delta) > roughness_limit
        ):
            stable = False
            break

    return {
        "layers": summaries,
        "slope_deltas": slope_deltas,
        "roughness_deltas": roughness_deltas,
        "stable": stable,
    }


def breakdown(layers, slope_limit=5.0, roughness_limit=1.0):
    """Break down per-cell slope/roughness exceedance per depth grid.

    ``layers``, ``slope_limit`` and ``roughness_limit`` have exactly the
    same constraints and validation order as in
    :func:`compare_layers` (including the strictly increasing ``r``
    values, the first-error rule and the ``"layers[i]: "`` /
    ``"layers[i].cells[j]: "`` prefixes); the limits are finite
    non-bool ints/floats ``> 0``. Type mismatches (including bool)
    raise ``TypeError`` and all other constraint errors raise
    ``ValueError``.

    Each layer is passed to :func:`analyze` exactly once, in input
    order; exceptions propagate unchanged and inputs are not modified.

    For each layer, ``slope_valid``/``roughness_valid`` are the numbers
    of entries whose slope/roughness is not ``None`` in the tuple
    returned by :func:`analyze`, and ``slope_exceed``/
    ``roughness_exceed`` are the numbers of those values strictly
    greater than ``slope_limit``/``roughness_limit``.
    ``slope_rate``/``roughness_rate`` are the exceedance fractions
    ``slope_exceed / slope_valid`` and
    ``roughness_exceed / roughness_valid`` (``0.0`` when the
    denominator is zero), rounded with ``round(float(v), 6)``
    (negative zero normalized to ``0.0``). ``quality`` is ``"pass"``
    when both exceedance counts are zero and ``"fail"`` otherwise.

    Returns a dict with keys in the order ``layers, overall``:
    ``layers`` is a tuple, in input order, of dicts with keys
    ``resolution, total, slope_valid, roughness_valid, slope_exceed,
    roughness_exceed, slope_rate, roughness_rate, quality`` (in that
    order), where ``resolution`` is ``round(float(r), 6)`` (negative
    zero normalized to ``0.0``), ``total`` is ``nx * ny`` and the
    counts are ints. ``overall`` is ``"pass"`` when every layer passes
    and ``"fail"`` otherwise.
    """
    if not isinstance(layers, (list, tuple)):
        raise TypeError("layers must be a list or tuple")
    if len(layers) == 0:
        raise ValueError("layers must not be empty")

    validated = []
    for i in range(len(layers)):
        prefix = f"layers[{i}]: "
        layer = layers[i]
        if not isinstance(layer, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(layer) != 4:
            raise ValueError(prefix + "must have 4 elements")
        r, nx, ny, cells = layer

        if not _is_real_number(r):
            raise TypeError(prefix + "r must be a non-bool int or float")
        if not math.isfinite(r):
            raise ValueError(prefix + "r must be finite")
        if not r > 0:
            raise ValueError(prefix + "r must be > 0")

        for name, value in (("nx", nx), ("ny", ny)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not value > 0:
                raise ValueError(prefix + f"{name} must be > 0")

        if not isinstance(cells, (list, tuple)):
            raise TypeError(prefix + "cells must be a list or tuple")
        if len(cells) != nx * ny:
            raise ValueError(prefix + "cells must have nx * ny elements")

        for j in range(len(cells)):
            cell_prefix = f"layers[{i}].cells[{j}]: "
            cell = cells[j]
            if not isinstance(cell, (list, tuple)):
                raise TypeError(cell_prefix + "must be a list or tuple")
            if len(cell) != 2:
                raise ValueError(cell_prefix + "must have 2 elements")
            count, mean = cell
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError(cell_prefix + "count must be a non-bool int")
            if not count >= 0:
                raise ValueError(cell_prefix + "count must be >= 0")
            if count == 0:
                if mean is not None:
                    raise ValueError(
                        cell_prefix + "mean must be None when count is 0"
                    )
            else:
                if not _is_real_number(mean):
                    raise TypeError(
                        cell_prefix + "mean must be a non-bool int or float"
                    )
                if not math.isfinite(mean):
                    raise ValueError(cell_prefix + "mean must be finite")
                if not mean >= 0:
                    raise ValueError(cell_prefix + "mean must be >= 0")

        validated.append((r, nx, ny, cells))

    for i in range(1, len(validated)):
        if not validated[i][0] > validated[i - 1][0]:
            raise ValueError(
                f"layers[{i}]: r must be strictly greater than the "
                f"previous layer's r"
            )

    for name, value in (
        ("slope_limit", slope_limit),
        ("roughness_limit", roughness_limit),
    ):
        if not _is_real_number(value):
            raise TypeError(f"{name} must be a non-bool int or float")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if not value > 0:
            raise ValueError(f"{name} must be > 0")

    results = []
    for r, nx, ny, cells in validated:
        analysis = analyze(r, nx, ny, cells)

        slope_valid = sum(1 for slope, _ in analysis if slope is not None)
        roughness_valid = sum(
            1 for _, roughness in analysis if roughness is not None
        )
        slope_exceed = sum(
            1 for slope, _ in analysis if slope is not None and slope > slope_limit
        )
        roughness_exceed = sum(
            1
            for _, roughness in analysis
            if roughness is not None and roughness > roughness_limit
        )
        slope_rate = (
            _round6(slope_exceed / slope_valid) if slope_valid > 0 else 0.0
        )
        roughness_rate = (
            _round6(roughness_exceed / roughness_valid)
            if roughness_valid > 0
            else 0.0
        )
        grade = (
            "pass" if slope_exceed == 0 and roughness_exceed == 0 else "fail"
        )

        results.append(
            {
                "resolution": _round6(r),
                "total": int(nx * ny),
                "slope_valid": int(slope_valid),
                "roughness_valid": int(roughness_valid),
                "slope_exceed": int(slope_exceed),
                "roughness_exceed": int(roughness_exceed),
                "slope_rate": slope_rate,
                "roughness_rate": roughness_rate,
                "quality": grade,
            }
        )

    overall = "pass" if all(layer["quality"] == "pass" for layer in results) else "fail"

    return {
        "layers": tuple(results),
        "overall": overall,
    }


def quality(layers, slope_limit=5.0, roughness_limit=1.0):
    """Grade the multi-layer comparison of several depth grids.

    ``layers``, ``slope_limit`` and ``roughness_limit`` have exactly the
    same constraints and validation order as in
    :func:`compare_layers` (including the strictly increasing ``r``
    values, the first-error rule and the ``"layers[i]: "`` /
    ``"layers[i].cells[j]: "`` prefixes); type mismatches raise
    ``TypeError`` and all other constraint errors raise
    ``ValueError``. :func:`compare_layers` is called exactly once as
    ``compare_layers(layers, slope_limit, roughness_limit)``; its
    exceptions propagate unchanged and inputs are not modified.

    With ``C`` the dict returned by :func:`compare_layers` and
    ``n = len(C["layers"])``, ``coverage`` is a tuple of one float per
    layer, ``round(valid / total, 6)`` from that layer's
    :func:`stats` summary. ``mean_coverage`` is
    ``round(math.fsum(coverage) / n, 6)`` and ``score`` is
    ``round(100 * mean_coverage * (1 if C["stable"] else 0), 6)``
    (negative zero normalized to ``0.0``). ``quality`` is ``"pass"``
    when ``C["stable"]`` is true and every coverage value is ``1.0``,
    and ``"fail"`` otherwise.

    Returns a dict with keys in the order ``comparison, coverage,
    mean_coverage, score, quality``: ``comparison`` is ``C`` as-is,
    ``coverage`` has length ``n`` and ``mean_coverage``/``score`` are
    floats.
    """
    comparison = compare_layers(layers, slope_limit, roughness_limit)

    n = len(comparison["layers"])
    coverage = tuple(
        round(layer["valid"] / layer["total"], 6)
        for layer in comparison["layers"]
    )
    mean_coverage = _round6(math.fsum(coverage) / n)
    score = _round6(
        100 * mean_coverage * (1 if comparison["stable"] else 0)
    )
    grade = (
        "pass"
        if comparison["stable"] and all(value == 1.0 for value in coverage)
        else "fail"
    )

    return {
        "comparison": comparison,
        "coverage": coverage,
        "mean_coverage": mean_coverage,
        "score": score,
        "quality": grade,
    }


def trend(layers, slope_limit=5.0, roughness_limit=1.0):
    """Track the slope/roughness exceedance rates across depth grids.

    ``layers``, ``slope_limit`` and ``roughness_limit`` have exactly the
    same constraints and validation order as in
    :func:`compare_layers` (including the strictly increasing ``r``
    values, finite non-bool limits ``> 0``, the first-error rule and
    the ``"layers[i]: "`` / ``"layers[i].cells[j]: "`` prefixes); type
    mismatches (including bool) raise ``TypeError`` and all other
    constraint errors raise ``ValueError``.

    :func:`breakdown` is called exactly once as
    ``breakdown(layers, slope_limit, roughness_limit)``; its exceptions
    propagate unchanged and inputs are not modified.

    With ``B`` the dict returned by :func:`breakdown` and
    ``n = len(B["layers"])``, ``slope_deltas``/``roughness_deltas`` are
    float tuples each with ``n - 1`` entries. Entry ``i`` (for
    ``i`` from ``0`` to ``n - 2``) is the ``slope_rate``/
    ``roughness_rate`` of layer ``i + 1`` minus that of layer ``i``,
    rounded with ``round(float(v), 6)`` (negative zero normalized to
    ``0.0``). ``monotonic`` is ``True`` when every delta is ``<= 0``
    (including when ``n == 1``) and ``False`` otherwise. ``overall`` is
    ``"pass"`` when ``monotonic`` is true and ``"fail"`` otherwise.

    Returns a dict with keys in the order ``breakdown, slope_deltas,
    roughness_deltas, monotonic, overall``: ``breakdown`` is ``B``
    as-is.
    """
    B = breakdown(layers, slope_limit, roughness_limit)

    layer_results = B["layers"]
    n = len(layer_results)

    slope_deltas = tuple(
        _round6(layer_results[i + 1]["slope_rate"] - layer_results[i]["slope_rate"])
        for i in range(n - 1)
    )
    roughness_deltas = tuple(
        _round6(
            layer_results[i + 1]["roughness_rate"]
            - layer_results[i]["roughness_rate"]
        )
        for i in range(n - 1)
    )

    monotonic = all(delta <= 0 for delta in slope_deltas) and all(
        delta <= 0 for delta in roughness_deltas
    )
    overall = "pass" if monotonic else "fail"

    return {
        "breakdown": B,
        "slope_deltas": slope_deltas,
        "roughness_deltas": roughness_deltas,
        "monotonic": monotonic,
        "overall": overall,
    }


def dashboard(layers, slope_limit=5.0, roughness_limit=1.0):
    """Combine the :func:`quality` and :func:`trend` reports.

    ``layers``, ``slope_limit`` and ``roughness_limit`` have exactly the
    same constraints as the parameters of :func:`quality` and
    :func:`trend`; all validation (container and threshold types,
    layer/cell shapes, finite non-bool numbers, strictly increasing
    ``r`` values and positive limits, in the first-error order with the
    ``"layers[i]: "`` / ``"layers[i].cells[j]: "`` prefixes) is carried
    out by those functions. Type mismatches (including bool) raise
    ``TypeError`` and all other constraint errors raise ``ValueError``.

    :func:`quality` is called exactly once as
    ``quality(layers, slope_limit, roughness_limit)`` and then
    :func:`trend` exactly once as
    ``trend(layers, slope_limit, roughness_limit)``; exceptions from
    either call propagate unchanged and inputs are not modified.

    Returns a dict with keys in the order ``quality, trend, overall``:
    ``quality`` and ``trend`` are the dicts returned by the two calls
    as-is, and ``overall`` is ``"pass"`` only when the quality grade and
    the trend overall grade are both ``"pass"``, and ``"fail"``
    otherwise.
    """
    Q = quality(layers, slope_limit, roughness_limit)
    T = trend(layers, slope_limit, roughness_limit)

    overall = (
        "pass"
        if Q["quality"] == "pass" and T["overall"] == "pass"
        else "fail"
    )

    return {
        "quality": Q,
        "trend": T,
        "overall": overall,
    }
