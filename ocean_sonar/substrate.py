"""Seabed substrate classification from slope/roughness analysis grids.

Each layer pairs a regular per-cell ``(slope, roughness)`` analysis grid
(as produced by :func:`ocean_sonar.terrain.analyze`) with its cell size
and classifies every cell into a substrate class by thresholding slope
and roughness.
"""

from __future__ import annotations

import json
import math

from .svp import _is_real_number

__all__ = ["batch", "classify"]

_CLASSES = ("mud", "sand", "gravel", "rock")


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


def classify(layers, slope_limit=5.0, roughness_limit=1.0):
    """Classify analysis grids into seabed substrate classes.

    ``layers`` is a non-empty list/tuple of four-element list/tuples
    ``(r, nx, ny, analysis)``: ``r`` is the cell size, a finite non-bool
    int/float with ``r > 0``; ``nx``/``ny`` are non-bool positive ints;
    ``analysis`` is a list/tuple of length ``nx * ny`` ordered by ``y``
    then ``x``. Each cell is a two-element list/tuple ``(slope,
    roughness)``; ``(None, None)``, ``(None, q)`` and ``(p, q)`` are
    legal (``None`` marks unknown), ``(p, None)`` with non-``None``
    ``p`` is not. Non-``None`` values must be finite non-bool
    int/float ``>= 0``. ``slope_limit``/``roughness_limit`` are finite
    non-bool int/float ``> 0``.

    A cell with ``slope`` equal to ``None`` is ``unknown``. Otherwise
    the bit pair ``(slope > slope_limit, roughness > roughness_limit)``
    selects the class: ``00`` mud, ``01`` sand, ``10`` gravel,
    ``11`` rock.

    Validation order: ``layers`` container, non-emptiness, then per
    layer (container, 4 elements, ``r``, ``nx``, ``ny``, ``analysis``
    container/length), then per cell (container, 2 elements, ``slope``,
    ``roughness``), then ``slope_limit``, then ``roughness_limit``;
    checking stops at the first error. Type mismatches (including bool)
    raise ``TypeError``, all other constraint errors raise
    ``ValueError``. Layer errors are prefixed with ``"layers[i]: "``
    and cell errors with ``"layers[i].analysis[j]: "``.

    Returns a tuple with one dict per layer, keys in order
    ``resolution``, ``nx``, ``ny``, ``classes``, ``counts``.
    ``resolution`` is ``round(float(r), 6)`` (negative zero normalized
    to ``0.0``); ``classes`` is a tuple of class name strings in grid
    order (``y`` then ``x``); ``counts`` maps ``unknown``, ``mud``,
    ``sand``, ``gravel``, ``rock`` (in that key order) to int counts.
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
                        cell_prefix + "slope must be a non-bool int or float"
                    )
                if not math.isfinite(slope):
                    raise ValueError(cell_prefix + "slope must be finite")
                if not slope >= 0:
                    raise ValueError(cell_prefix + "slope must be >= 0")
            if roughness is None:
                if slope is not None:
                    raise ValueError(
                        cell_prefix
                        + "roughness must not be None when slope is not None"
                    )
            else:
                if not _is_real_number(roughness):
                    raise TypeError(
                        cell_prefix + "roughness must be a non-bool int or float"
                    )
                if not math.isfinite(roughness):
                    raise ValueError(cell_prefix + "roughness must be finite")
                if not roughness >= 0:
                    raise ValueError(cell_prefix + "roughness must be >= 0")

    _check_limit("slope_limit", slope_limit)
    _check_limit("roughness_limit", roughness_limit)

    result = []
    for layer in layers:
        r, nx, ny, analysis = layer
        classes = []
        counts = {"unknown": 0, "mud": 0, "sand": 0, "gravel": 0, "rock": 0}
        for cell in analysis:
            slope, roughness = cell
            if slope is None:
                name = "unknown"
            else:
                index = (
                    2 * (slope > slope_limit) + (roughness > roughness_limit)
                )
                name = _CLASSES[index]
            classes.append(name)
            counts[name] += 1
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


def batch(analysis, intensities) -> bytes:
    """Classify analysis cells with backscatter intensities as JSON bytes.

    ``analysis`` is a non-empty list/tuple of two-element list/tuples
    ``(p, q)``: when ``p`` is ``None``, ``q`` is ``None`` or a finite
    non-bool int/float ``>= 0``; otherwise ``p`` and ``q`` are both
    finite non-bool ints/floats ``>= 0``. ``intensities`` is a
    list/tuple of the same length whose items are ``None`` or finite
    non-bool ints/floats in ``[0, 1]``.

    Validation order: the ``analysis`` container, non-emptiness, then
    per cell (container, 2 elements, ``p``, ``q``), then the
    ``intensities`` container, its length and finally each item in
    order; checking stops at the first error. Type mismatches
    (including bool) raise ``TypeError``, all other constraint errors
    raise ``ValueError``. Cell errors are prefixed with
    ``"analysis[i]: "`` and item errors with ``"intensities[i]: "``.

    A cell whose ``p`` or intensity is ``None`` yields
    ``["unknown", 0.0]``. Otherwise, with ``g = p > 5 or q > 1`` and
    ``a = intensity >= 0.5``, the bit pair ``(g, a)`` selects the
    class: ``00`` mud, ``01`` sand, ``10`` gravel, ``11`` rock, with
    confidence ``1.0``.

    The returned document has top-level keys exactly in the order
    ``results, summary``. ``results`` is an array in input order of
    ``[class, confidence]`` pairs. ``summary`` has keys exactly in the
    order ``count, unknown, quality``: ``count`` is the number of
    cells, ``unknown`` the number of ``unknown`` results (both ints),
    and ``quality`` is ``"pass"`` only when ``unknown == 0`` and
    ``"fail"`` otherwise.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``terrain.batch``. Any JSON or
    UTF-8 encoding failure raises ``ValueError``.

    Inputs are not modified. Returns the JSON document as ``bytes``.
    """
    if not isinstance(analysis, (list, tuple)):
        raise TypeError("analysis must be a list or tuple")
    if len(analysis) == 0:
        raise ValueError("analysis must be non-empty")

    for i in range(len(analysis)):
        prefix = f"analysis[{i}]: "
        cell = analysis[i]
        if not isinstance(cell, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        p, q = cell
        if p is not None:
            if not _is_real_number(p):
                raise TypeError(prefix + "p must be a non-bool int or float")
            if not math.isfinite(p):
                raise ValueError(prefix + "p must be finite")
            if not p >= 0:
                raise ValueError(prefix + "p must be >= 0")
        if q is None:
            if p is not None:
                raise ValueError(
                    prefix + "q must not be None when p is not None"
                )
        else:
            if not _is_real_number(q):
                raise TypeError(prefix + "q must be a non-bool int or float")
            if not math.isfinite(q):
                raise ValueError(prefix + "q must be finite")
            if not q >= 0:
                raise ValueError(prefix + "q must be >= 0")

    if not isinstance(intensities, (list, tuple)):
        raise TypeError("intensities must be a list or tuple")
    if len(intensities) != len(analysis):
        raise ValueError("intensities must have the same length as analysis")
    for i in range(len(intensities)):
        prefix = f"intensities[{i}]: "
        intensity = intensities[i]
        if intensity is None:
            continue
        if not _is_real_number(intensity):
            raise TypeError(prefix + "must be a non-bool int or float")
        if not math.isfinite(intensity):
            raise ValueError(prefix + "must be finite")
        if not 0 <= intensity <= 1:
            raise ValueError(prefix + "must be in [0, 1]")

    results = []
    unknown = 0
    for i in range(len(analysis)):
        p, q = analysis[i]
        intensity = intensities[i]
        if p is None or intensity is None:
            results.append(["unknown", 0.0])
            unknown += 1
        else:
            g = p > 5 or q > 1
            a = intensity >= 0.5
            results.append([_CLASSES[2 * g + a], 1.0])

    count = len(analysis)
    document = {
        "results": results,
        "summary": {
            "count": int(count),
            "unknown": int(unknown),
            "quality": "pass" if unknown == 0 else "fail",
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
