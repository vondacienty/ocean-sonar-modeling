"""Quality assessment of gridded terrain analysis results.

Given one or more layers of per-cell slope/roughness analysis (as
produced by :func:`ocean_sonar.terrain.analyze`), summarize each layer
with coverage and threshold-exceedance counts.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["assess"]


def _round6(value):
    result = round(float(value), 6)
    if result == 0:
        result = 0.0
    return result


def _check_limit(name, value):
    if not _is_real_number(value):
        raise TypeError(f"{name} must be a non-bool int or float")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not value > 0:
        raise ValueError(f"{name} must be > 0")


def assess(layers, slope_limit=5.0, roughness_limit=1.0):
    """Summarize quality metrics for each analysed grid layer.

    ``layers`` is a non-empty list/tuple of items
    ``(r, nx, ny, analysis)``: ``r`` is the cell size, a finite
    non-bool int/float with ``r > 0``; ``nx``/``ny`` are non-bool
    positive ints; ``analysis`` is a list/tuple of length ``nx * ny``
    whose items are two-element list/tuples ``(slope, roughness)`` that
    are either ``(None, None)`` or have ``slope`` equal to ``None`` or
    a finite non-bool int/float ``>= 0`` and ``roughness`` a finite
    non-bool int/float ``>= 0``. ``slope_limit`` and
    ``roughness_limit`` are finite non-bool int/floats, both ``> 0``.

    Validation follows the signature parameter order, then layer index,
    then field order, stopping at the first error: type mismatches
    (including bool) raise ``TypeError``, all other constraint errors
    raise ``ValueError``. Layer errors are prefixed with
    ``"layers[i]: "`` and grid-cell errors with
    ``"layers[i].analysis[j]: "``.

    Returns a tuple in the same order as ``layers`` of dicts with keys
    ``resolution, total, valid, coverage, slope_exceed,
    roughness_exceed``: ``total`` is ``nx * ny``, ``valid`` the number
    of non-``(None, None)`` cells, ``coverage`` is ``valid / total``
    and ``resolution`` is ``r``. ``slope_exceed``/``roughness_exceed``
    count cells whose non-``None`` value is strictly greater than the
    corresponding limit. Counts are ints; the other values are rounded
    with ``round(float(v), 6)`` (negative zero normalized to ``0.0``).
    Inputs are not modified.
    """
    if not isinstance(layers, (list, tuple)):
        raise TypeError("layers must be a list or tuple")
    if len(layers) == 0:
        raise ValueError("layers must be non-empty")

    for i in range(len(layers)):
        prefix = f"layers[{i}]: "
        layer = layers[i]
        if not isinstance(layer, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(layer) != 4:
            raise ValueError(prefix + "must have 4 elements")
        r, nx, ny, analysis = layer

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

        if not isinstance(analysis, (list, tuple)):
            raise TypeError(prefix + "analysis must be a list or tuple")
        if len(analysis) != nx * ny:
            raise ValueError(prefix + "analysis must have nx * ny elements")

        for j in range(len(analysis)):
            cell_prefix = f"layers[{i}].analysis[{j}]: "
            cell = analysis[j]
            if not isinstance(cell, (list, tuple)):
                raise TypeError(cell_prefix + "must be a list or tuple")
            if len(cell) != 2:
                raise ValueError(cell_prefix + "must have 2 elements")
            slope, roughness = cell

            if slope is not None:
                if not _is_real_number(slope):
                    raise TypeError(
                        cell_prefix + "slope must be None or a non-bool int or float"
                    )
                if not math.isfinite(slope):
                    raise ValueError(cell_prefix + "slope must be finite")
                if not slope >= 0:
                    raise ValueError(cell_prefix + "slope must be >= 0")

            if roughness is None:
                if slope is not None:
                    raise ValueError(
                        cell_prefix + "roughness must be None only when slope is None"
                    )
            else:
                if not _is_real_number(roughness):
                    raise TypeError(
                        cell_prefix + "roughness must be None or a non-bool int or float"
                    )
                if not math.isfinite(roughness):
                    raise ValueError(cell_prefix + "roughness must be finite")
                if not roughness >= 0:
                    raise ValueError(cell_prefix + "roughness must be >= 0")

    _check_limit("slope_limit", slope_limit)
    _check_limit("roughness_limit", roughness_limit)

    result = []
    for r, nx, ny, analysis in layers:
        total = nx * ny
        valid = 0
        slope_exceed = 0
        roughness_exceed = 0
        for slope, roughness in analysis:
            if slope is None and roughness is None:
                continue
            valid += 1
            if slope is not None and slope > slope_limit:
                slope_exceed += 1
            if roughness > roughness_limit:
                roughness_exceed += 1
        result.append(
            {
                "resolution": _round6(r),
                "total": total,
                "valid": valid,
                "coverage": _round6(valid / total),
                "slope_exceed": slope_exceed,
                "roughness_exceed": roughness_exceed,
            }
        )
    return tuple(result)
