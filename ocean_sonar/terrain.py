"""Terrain analysis of gridded bathymetry.

Given a regular grid of ``nx`` columns and ``ny`` rows (cells ordered
by ``y`` then ``x``), each non-empty cell's roughness is the range of
the means in its boundary-clipped 3×3 neighbourhood and its slope is
derived from the four orthogonal neighbours.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["analyze"]


def analyze(r, nx, ny, cells):
    """Compute slope and roughness for every cell of a binned grid.

    ``r`` is a finite non-bool int/float with ``r > 0``; ``nx``/``ny``
    are non-bool positive ints. ``cells`` is a list/tuple of length
    ``nx * ny``, ordered by ``y`` then ``x``; each item is a
    two-element list/tuple ``(count, mean)`` where ``count`` is a
    non-bool non-negative int, ``mean`` is exactly ``None`` when
    ``count == 0`` and otherwise a finite non-bool int/float with
    ``mean >= 0``.

    For a non-empty centre, roughness is ``max - min`` of all non-empty
    means in the 3×3 neighbourhood clipped to the grid boundary. With
    the left/right/below/above neighbour means denoted ``L``/``R``/
    ``D``/``U``, slope is
    ``degrees(atan(hypot((R - L) / (2*r), (U - D) / (2*r))))`` when
    all four neighbours exist and are non-empty, and ``None``
    otherwise. Empty centres are fixed as ``(None, None)``.

    Validation follows the signature order (``r``, ``nx``, ``ny``,
    ``cells``) and stops at the first error; within ``cells`` items
    are checked in order, each as container type, length, ``count``
    type/value and then ``mean`` presence/type/finiteness/value.
    Type mismatches (including bool) raise ``TypeError``; all other
    constraint errors raise ``ValueError``.

    Returns a tuple in ``cells`` order; each item is
    ``(slope, roughness)``. Every non-``None`` number is
    ``round(float(v), 6)`` with negative zero normalized to ``0.0``.
    Calculations use the unrounded means; inputs are not modified.
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
    for name, value in (("nx", nx), ("ny", ny)):
        if not value > 0:
            raise ValueError(f"{name} must be positive")

    if not isinstance(cells, (list, tuple)):
        raise TypeError("cells must be a list or tuple")
    if len(cells) != nx * ny:
        raise ValueError("cells must have length nx * ny")

    means: list[float | None] = []
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
        if count < 0:
            raise ValueError(prefix + "count must be non-negative")
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
            means.append(float(mean))

    def rounded(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    result = []
    for iy in range(ny):
        for ix in range(nx):
            i = iy * nx + ix
            if means[i] is None:
                result.append((None, None))
                continue

            neighbours = []
            for dy in (-1, 0, 1):
                jy = iy + dy
                if not 0 <= jy < ny:
                    continue
                row = jy * nx
                for dx in (-1, 0, 1):
                    jx = ix + dx
                    if 0 <= jx < nx and means[row + jx] is not None:
                        neighbours.append(means[row + jx])
            roughness = rounded(max(neighbours) - min(neighbours))

            slope = None
            if ix > 0 and ix + 1 < nx and iy > 0 and iy + 1 < ny:
                left = means[i - 1]
                right = means[i + 1]
                below = means[i - nx]
                above = means[i + nx]
                if (
                    left is not None
                    and right is not None
                    and below is not None
                    and above is not None
                ):
                    slope = rounded(
                        math.degrees(
                            math.atan(
                                math.hypot(
                                    (right - left) / (2 * r),
                                    (above - below) / (2 * r),
                                )
                            )
                        )
                    )

            result.append((slope, roughness))
    return tuple(result)
