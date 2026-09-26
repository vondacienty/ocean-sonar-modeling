"""Grid binning of sonar soundings at multiple resolutions.

For every resolution ``r`` the rectangle ``(xmin, ymin)``-
``(xmax, ymax)`` is divided into ``nx = (xmax - xmin) / r`` columns
and ``ny = (ymax - ymin) / r`` rows, both integral. A cell includes
its left/bottom edges and excludes its right/top edges; a point on the
maximum edge is assigned to the last column/row. Cells are ordered by
``y`` then ``x`` (``y`` primary), and the depths falling in each cell
are averaged with ``math.fsum`` in point input order.
"""

from __future__ import annotations

import json
import math

from .svp import _is_real_number

__all__ = ["build", "batch"]

_FIELDS = ("x", "y", "d")


def build(points, bounds, resolutions):
    """Bin points into regular grids at several resolutions.

    ``points`` is a non-empty list/tuple of three-element lists/tuples
    ``(x, y, d)``; ``bounds`` is a four-element list/tuple
    ``(xmin, ymin, xmax, ymax)``; ``resolutions`` is a list/tuple of at
    least two strictly increasing values. Every value must be a finite
    non-bool int/float. In addition ``d >= 0``, ``xmin < xmax``,
    ``ymin < ymax`` and each resolution ``r > 0``; every point must lie
    within the closed bounds and both ``(xmax - xmin) / r`` and
    ``(ymax - ymin) / r`` must be integral Python floats.

    For each resolution ``r``, ``nx``/``ny`` are the two quotients as
    ints. Cells include the left/bottom edges and exclude the
    right/top edges, except that a point on the maximum edge joins the
    last column/row. Cells are expanded by ``y`` then ``x``; the depths
    of a cell are averaged as ``math.fsum`` over input order divided by
    their count.

    Validation order (first error wins): the three containers, point
    non-emptiness, each point (container, length), the bounds length,
    the resolutions minimum length, then the numeric types and
    finiteness of points/bounds/resolutions in that order; then
    ``d >= 0`` per point, ``xmin < xmax``, ``ymin < ymax``, the strict
    increase and positivity of resolutions, the closed-bounds
    containment per point, and finally per resolution the integral
    width/height quotients. Container and value type errors (including
    bool) raise ``TypeError``; all other constraint errors raise
    ``ValueError``. Point errors are prefixed with ``"points[i]: "``.

    Returns a tuple in resolutions order; each layer is
    ``(r, nx, ny, cells)`` and each cell is ``(count, mean)`` with empty
    cells fixed as ``(0, None)``. ``nx``/``ny``/``count`` are ints;
    ``r``/``mean`` are floats rounded to 6 decimals with
    ``round(float(v), 6)`` (negative zero normalized to ``0.0``). All
    binning uses the unrounded input values; inputs are not modified.
    """
    for name, value in (
        ("points", points),
        ("bounds", bounds),
        ("resolutions", resolutions),
    ):
        if not isinstance(value, (list, tuple)):
            raise TypeError(f"{name} must be a list or tuple")

    if len(points) == 0:
        raise ValueError("points must be non-empty")
    for i in range(len(points)):
        prefix = f"points[{i}]: "
        if not isinstance(points[i], (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(points[i]) != 3:
            raise ValueError(prefix + "must have 3 elements")
    if len(bounds) != 4:
        raise ValueError("bounds must have 4 elements")
    if len(resolutions) < 2:
        raise ValueError("resolutions must have at least 2 elements")

    for i in range(len(points)):
        prefix = f"points[{i}]: "
        for name, value in zip(_FIELDS, points[i]):
            if not _is_real_number(value):
                raise TypeError(prefix + f"{name} must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(prefix + f"{name} must be finite")
    for value in bounds:
        if not _is_real_number(value):
            raise TypeError("bounds elements must be non-bool int or float")
    for value in bounds:
        if not math.isfinite(value):
            raise ValueError("bounds elements must be finite")
    for value in resolutions:
        if not _is_real_number(value):
            raise TypeError("resolutions elements must be non-bool int or float")
    for value in resolutions:
        if not math.isfinite(value):
            raise ValueError("resolutions elements must be finite")

    for i in range(len(points)):
        if not points[i][2] >= 0:
            raise ValueError(f"points[{i}]: d must be >= 0")

    xmin, ymin, xmax, ymax = bounds
    if not xmin < xmax:
        raise ValueError("xmin must be < xmax")
    if not ymin < ymax:
        raise ValueError("ymin must be < ymax")

    for k in range(len(resolutions) - 1):
        if not resolutions[k] < resolutions[k + 1]:
            raise ValueError("resolutions must be strictly increasing")
    for k in range(len(resolutions)):
        if not resolutions[k] > 0:
            raise ValueError(f"resolutions[{k}] must be > 0")

    for i in range(len(points)):
        x, y, _ = points[i]
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            raise ValueError(f"points[{i}]: point must be within bounds")

    width = xmax - xmin
    height = ymax - ymin
    grids = []
    for k in range(len(resolutions)):
        r = resolutions[k]
        qx = width / r
        qy = height / r
        if not qx.is_integer():
            raise ValueError(f"width must be divisible by resolutions[{k}]")
        if not qy.is_integer():
            raise ValueError(f"height must be divisible by resolutions[{k}]")
        grids.append((r, int(qx), int(qy)))

    layers = []
    for r, nx, ny in grids:
        buckets = [[] for _ in range(ny * nx)]
        for x, y, d in points:
            ix = math.floor((x - xmin) / r)
            iy = math.floor((y - ymin) / r)
            if ix == nx:
                ix = nx - 1
            if iy == ny:
                iy = ny - 1
            buckets[iy * nx + ix].append(d)

        cells = []
        for bucket in buckets:
            count = len(bucket)
            if count == 0:
                cells.append((0, None))
                continue
            mean = round(float(math.fsum(bucket) / count), 6)
            if mean == 0:
                mean = 0.0
            cells.append((count, mean))

        rr = round(float(r), 6)
        if rr == 0:
            rr = 0.0
        layers.append((rr, nx, ny, tuple(cells)))
    return tuple(layers)


def batch(points, bounds, resolutions, min_coverage=1.0) -> bytes:
    """Build grids at several resolutions and serialize coverage as JSON bytes.

    Calls :func:`build` exactly once with ``(points, bounds,
    resolutions)`` — its validation and exceptions apply unchanged and
    the inputs are not modified. ``min_coverage`` is validated after the
    build: it must be a finite non-bool int/float within ``[0, 1]``. A
    bool or non-number raises ``TypeError`` and a non-finite value or a
    value outside ``[0, 1]`` raises ``ValueError``.

    With ``G`` the tuple returned by :func:`build`, the returned
    document has top-level keys exactly in the order ``results,
    summary``. ``results`` is an array in the layer order of ``G``; each
    item has keys exactly in the order ``resolution, nx, ny, cells,
    filled, coverage`` where ``resolution`` is the layer's ``r``,
    ``nx``/``ny`` its grid dimensions, ``cells`` an array in the
    layer's cell order of ``[count, mean]`` arrays (``None`` means
    encoded as ``null``), ``filled`` the number of non-empty cells and
    ``coverage`` equal to ``round(filled / (nx * ny), 6)``. ``summary``
    has keys exactly in the order ``layer_count, total_cells,
    filled_cells, mean_coverage, quality`` where ``layer_count`` is the
    number of layers, ``total_cells`` the total number of cells,
    ``filled_cells`` the total number of non-empty cells,
    ``mean_coverage`` the ``math.fsum`` mean of the per-layer
    ``coverage`` values rounded to 6 decimals, and ``quality`` is
    ``"pass"`` only when every ``coverage`` is ``>= min_coverage``,
    otherwise ``"fail"``.

    Counts are ints and all other numbers floats; floats are rounded
    with ``round(float(v), 6)`` and negative zero is normalized to
    ``0.0``. The object is encoded as UTF-8 JSON with
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing newline,
    as in ``strip.batch``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    layers = build(points, bounds, resolutions)

    if not _is_real_number(min_coverage):
        raise TypeError("min_coverage must be a non-bool int or float")
    if not math.isfinite(min_coverage):
        raise ValueError("min_coverage must be finite")
    if not 0 <= min_coverage <= 1:
        raise ValueError("min_coverage must be in [0, 1]")

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    results = []
    coverages = []
    for r, nx, ny, cells in layers:
        filled = sum(1 for count, _ in cells if count > 0)
        coverage = rounded_float(filled / (nx * ny))
        coverages.append(coverage)
        results.append(
            {
                "resolution": rounded_float(r),
                "nx": int(nx),
                "ny": int(ny),
                "cells": [
                    [int(count), None if mean is None else rounded_float(mean)]
                    for count, mean in cells
                ],
                "filled": int(filled),
                "coverage": coverage,
            }
        )

    layer_count = int(len(layers))
    total_cells = int(sum(nx * ny for _, nx, ny, _ in layers))
    filled_cells = int(sum(item["filled"] for item in results))
    mean_coverage = rounded_float(math.fsum(coverages) / layer_count)
    document = {
        "results": results,
        "summary": {
            "layer_count": layer_count,
            "total_cells": total_cells,
            "filled_cells": filled_cells,
            "mean_coverage": mean_coverage,
            "quality": (
                "pass"
                if all(coverage >= min_coverage for coverage in coverages)
                else "fail"
            ),
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
