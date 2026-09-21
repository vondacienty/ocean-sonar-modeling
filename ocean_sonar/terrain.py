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

__all__ = ["analyze"]


def _round6(value):
    result = round(float(value), 6)
    if result == 0:
        result = 0.0
    return result


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

    means = [cell[1] if cell[0] > 0 else None for cell in cells]

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
