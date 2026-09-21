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

import math

from .svp import _is_real_number

__all__ = ["build"]

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
