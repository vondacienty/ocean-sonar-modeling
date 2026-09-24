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

__all__ = ["analyze", "analyze_layers", "metrics", "stats"]


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
    once and any exception it raises propagates unchanged; inputs are
    not modified.

    With ``A`` the tuple returned by :func:`analyze`, ``valid`` is the
    number of non-empty cells, ``slope_valid`` the number of entries
    whose slope is not ``None`` and ``roughness_valid`` the number
    whose roughness is not ``None``. ``min_slope``/``max_slope``/
    ``mean_slope`` summarize the non-``None`` slopes and
    ``min_roughness``/``max_roughness``/``mean_roughness`` the
    non-``None`` roughness values, each mean computed with
    ``math.fsum``; when a metric has no values its min/max/mean are all
    ``None``.

    Returns a dict with keys in the order ``resolution, total, valid,
    slope_valid, roughness_valid, min_slope, max_slope, mean_slope,
    min_roughness, max_roughness, mean_roughness``: ``resolution`` is
    ``r``, ``total`` is ``nx * ny`` and the counts are ints. Every
    non-``None`` numeric value is rounded with ``round(float(v), 6)``
    (negative zero normalized to ``0.0``).
    """
    analysis = analyze(r, nx, ny, cells)

    slopes = [slope for slope, _ in analysis if slope is not None]
    roughnesses = [
        roughness for _, roughness in analysis if roughness is not None
    ]

    def summarize(values):
        if not values:
            return None, None, None
        return (
            _round6(min(values)),
            _round6(max(values)),
            _round6(math.fsum(values) / len(values)),
        )

    min_slope, max_slope, mean_slope = summarize(slopes)
    min_roughness, max_roughness, mean_roughness = summarize(roughnesses)

    return {
        "resolution": _round6(r),
        "total": int(nx * ny),
        "valid": len(roughnesses),
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
