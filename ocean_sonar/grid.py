"""Regular grid binning of sounding points.

Points are binned into a regular grid over a bounding box, once per
requested resolution; each cell reports the count and the mean depth
of the points falling inside it.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["build"]


def _round6(value):
    rounded = round(float(value), 6)
    if rounded == 0:
        return 0.0
    return rounded


def build(points, bounds, resolutions):
    """Bin points into regular grids at the given resolutions.

    ``points`` is a non-empty list/tuple of ``(x, y, d)`` triples,
    ``bounds`` a ``(xmin, ymin, xmax, ymax)`` quadruple and
    ``resolutions`` a list/tuple of at least two strictly increasing
    cell sizes; all three containers and every point must be
    lists/tuples. Every number must be a finite non-bool int/float
    with ``d >= 0``, ``xmin < xmax``, ``ymin < ymax`` and ``r > 0``.
    Each point must lie within the closed bounds, and for every ``r``
    the quotients ``(xmax - xmin) / r`` and ``(ymax - ymin) / r`` —
    computed as Python floats — must satisfy ``is_integer()``; those
    quotients converted to int give ``nx`` and ``ny``.

    Cells include the left/bottom edge and exclude the right/top edge;
    a point on the maximum edge falls into the last column/row. Cells
    are expanded row by row (y first, then x). Within a cell the ``d``
    values are averaged in input order with ``math.fsum``.

    Validation runs in the order above and stops at the first error:
    container or numeric type errors (including bool) raise
    ``TypeError``, every other violated constraint raises
    ``ValueError``.

    Returns a tuple in the same order as ``resolutions``; each layer
    is ``(r, nx, ny, cells)`` and each cell ``(count, mean)`` with
    empty cells fixed at ``(0, None)``. ``nx``/``ny``/``count`` are
    ints; ``r``/``mean`` are floats from ``round(float(v), 6)`` with
    negative zero normalized to ``0.0``. Unrounded values are used
    throughout and the inputs are not modified.
    """
    if not isinstance(points, (list, tuple)):
        raise TypeError("points must be a list or tuple")
    if not isinstance(bounds, (list, tuple)):
        raise TypeError("bounds must be a list or tuple")
    if not isinstance(resolutions, (list, tuple)):
        raise TypeError("resolutions must be a list or tuple")

    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)):
            raise TypeError(f"points[{i}] must be a list or tuple")

    if len(points) == 0:
        raise ValueError("points must be non-empty")
    for i, point in enumerate(points):
        if len(point) != 3:
            raise ValueError(f"points[{i}] must be exactly (x, y, d)")
    if len(bounds) != 4:
        raise ValueError("bounds must be exactly (xmin, ymin, xmax, ymax)")
    if len(resolutions) < 2:
        raise ValueError("resolutions must have at least 2 elements")

    for i, point in enumerate(points):
        for j, value in enumerate(point):
            if not _is_real_number(value):
                raise TypeError(f"points[{i}][{j}] must be a non-bool int or float")
            if not math.isfinite(value):
                raise ValueError(f"points[{i}][{j}] must be finite")
        if not point[2] >= 0:
            raise ValueError(f"points[{i}][2] (d) must be >= 0")

    for name, value in zip(("xmin", "ymin", "xmax", "ymax"), bounds):
        if not _is_real_number(value):
            raise TypeError(f"bounds {name} must be a non-bool int or float")
        if not math.isfinite(value):
            raise ValueError(f"bounds {name} must be finite")
    xmin, ymin, xmax, ymax = bounds
    if not xmin < xmax:
        raise ValueError("xmin must be < xmax")
    if not ymin < ymax:
        raise ValueError("ymin must be < ymax")

    for i, r in enumerate(resolutions):
        if not _is_real_number(r):
            raise TypeError(f"resolutions[{i}] must be a non-bool int or float")
        if not math.isfinite(r):
            raise ValueError(f"resolutions[{i}] must be finite")
        if not r > 0:
            raise ValueError(f"resolutions[{i}] must be > 0")
    for k in range(len(resolutions) - 1):
        if not resolutions[k] < resolutions[k + 1]:
            raise ValueError("resolutions must be strictly increasing")

    for i, point in enumerate(points):
        if not (xmin <= point[0] <= xmax and ymin <= point[1] <= ymax):
            raise ValueError(f"points[{i}] must lie within the closed bounds")

    width = xmax - xmin
    height = ymax - ymin
    for i, r in enumerate(resolutions):
        if not (width / r).is_integer():
            raise ValueError(f"(xmax - xmin) / resolutions[{i}] must be an integer")
        if not (height / r).is_integer():
            raise ValueError(f"(ymax - ymin) / resolutions[{i}] must be an integer")

    layers = []
    for r in resolutions:
        nx = int(width / r)
        ny = int(height / r)
        buckets = [[] for _ in range(nx * ny)]
        for x, y, d in points:
            col = int((x - xmin) / r)
            row = int((y - ymin) / r)
            if col >= nx:
                col = nx - 1
            if row >= ny:
                row = ny - 1
            buckets[row * nx + col].append(d)
        cells = []
        for bucket in buckets:
            if bucket:
                cells.append((len(bucket), _round6(math.fsum(bucket) / len(bucket))))
            else:
                cells.append((0, None))
        layers.append((_round6(r), nx, ny, tuple(cells)))
    return tuple(layers)
