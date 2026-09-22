"""Seabed substrate classification of gridded terrain-analysis layers.

Given per-layer ``(r, nx, ny, analysis)`` descriptions where each
analysis cell is a ``(slope, roughness)`` pair as produced by
:func:`ocean_sonar.terrain.analyze`, classify every cell from whether
slope and roughness strictly exceed the given limits. The bit pair
``(slope > slope_limit, roughness > roughness_limit)`` maps ``00`` to
``"mud"``, ``01`` to ``"sand"``, ``10`` to ``"gravel"`` and ``11`` to
``"rock"``; a cell whose slope is ``None`` is ``"unknown"``.
"""

from __future__ import annotations

import math

from .svp import _is_real_number

__all__ = ["classify"]

# Indexed by the (slope-exceed, roughness-exceed) booleans:
# 00 -> mud, 01 -> sand, 10 -> gravel, 11 -> rock.
_LABELS = (("mud", "sand"), ("gravel", "rock"))

_COUNT_NAMES = ("unknown", "mud", "sand", "gravel", "rock")


def _round6(value):
    result = round(float(value), 6)
    if result == 0:
        result = 0.0
    return result


def classify(layers, slope_limit=5.0, roughness_limit=1.0):
    """Classify seabed substrate per terrain layer.

    ``layers`` is a non-empty list/tuple of ``(r, nx, ny, analysis)``
    items: ``r`` is a finite non-bool int/float ``> 0``; ``nx``/``ny``
    are non-bool positive ints; ``analysis`` is a list/tuple of length
    ``nx * ny`` whose items are two-element list/tuples
    ``(slope, roughness)`` ordered by ``y`` then ``x``. A cell is
    exactly ``(None, None)``, ``(None, roughness)`` or
    ``(slope, roughness)`` — only ``slope`` may be ``None`` — and a
    non-``None`` value is a finite non-bool int/float ``>= 0``.
    ``slope_limit``/``roughness_limit`` are finite non-bool int/float
    values ``> 0``.

    A cell whose ``slope`` is ``None`` classifies as ``"unknown"``;
    otherwise the pair of strict comparisons
    ``(slope > slope_limit, roughness > roughness_limit)`` maps
    ``00`` to ``"mud"``, ``01`` to ``"sand"``, ``10`` to ``"gravel"``
    and ``11`` to ``"rock"``.

    Validation follows the signature parameter order, then layer and
    cell index order, then field order, stopping at the first error:
    type mismatches (including bool) raise ``TypeError``, all other
    constraint errors raise ``ValueError``. Layer errors are prefixed
    with ``"layers[i]: "`` and cell errors with
    ``"layers[i].analysis[j]: "``.

    Returns a tuple in the same order as ``layers``; each item is a
    dict with keys ``resolution, nx, ny, classes, counts``.
    ``resolution`` is ``round(float(r), 6)`` (negative zero normalized
    to ``0.0``), ``classes`` is a tuple of label strings in ``y`` then
    ``x`` order and ``counts`` is a dict with keys
    ``unknown, mud, sand, gravel, rock`` and int values. Inputs are
    not modified.
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
            if slope is None and roughness is None:
                continue
            if slope is not None:
                if not _is_real_number(slope):
                    raise TypeError(
                        cell_prefix
                        + "slope must be None or a non-bool int or float"
                    )
                if not math.isfinite(slope):
                    raise ValueError(cell_prefix + "slope must be finite")
                if not slope >= 0:
                    raise ValueError(cell_prefix + "slope must be >= 0")
            if not _is_real_number(roughness):
                raise TypeError(
                    cell_prefix + "roughness must be a non-bool int or float"
                )
            if not math.isfinite(roughness):
                raise ValueError(cell_prefix + "roughness must be finite")
            if not roughness >= 0:
                raise ValueError(cell_prefix + "roughness must be >= 0")

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

    result = []
    for r, nx, ny, analysis in layers:
        classes = []
        counts = {name: 0 for name in _COUNT_NAMES}
        for slope, roughness in analysis:
            if slope is None:
                label = "unknown"
            else:
                label = _LABELS[slope > slope_limit][roughness > roughness_limit]
            classes.append(label)
            counts[label] += 1
        result.append(
            {
                "resolution": _round6(r),
                "nx": nx,
                "ny": ny,
                "classes": tuple(classes),
                "counts": counts,
            }
        )
    return tuple(result)
