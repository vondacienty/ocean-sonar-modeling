"""End-to-end bathymetric product pipeline.

Runs the full chain in one call: grid binning
(:mod:`ocean_sonar.grid`), terrain analysis
(:mod:`ocean_sonar.terrain`), quality assessment
(:mod:`ocean_sonar.quality`), substrate classification
(:mod:`ocean_sonar.substrate`), crosspoint evaluation
(:mod:`ocean_sonar.crosspoint`) and the combined verdict
(:mod:`ocean_sonar.report`).
"""

from __future__ import annotations

import json
import math

from . import crosspoint, grid, quality, report, substrate, terrain
from .report import (
    _check_crosspoint,
    _COUNT_KEYS,
    _overall_verdict,
    _to_jsonable,
)

__all__ = ["build", "serialize"]

_PRODUCT_KEYS = ("crosspoint", "layers", "overall")
_LAYER_KEYS = (
    "resolution",
    "nx",
    "ny",
    "cells",
    "analysis",
    "quality",
    "substrate",
)
_QUALITY_KEYS = (
    "resolution",
    "total",
    "valid",
    "coverage",
    "slope_exceed",
    "roughness_exceed",
)
_SUBSTRATE_KEYS = ("resolution", "nx", "ny", "classes", "counts")
_QUALITY_VALUES = ("pass", "fail")


def build(
    points,
    bounds,
    resolutions,
    crossings,
    tolerance=0.5,
    slope_limit=5.0,
    roughness_limit=1.0,
):
    """Build the full gridded terrain product in one pipeline.

    The stages run strictly in this order, exactly once each and with
    no interleaving, and every exception from any stage short-circuits
    and is propagated unchanged:

    1. :func:`grid.build(points, bounds, resolutions)
       <ocean_sonar.grid.build>` bins the soundings into one grid per
       resolution; each layer is ``(resolution, nx, ny, cells)``.
    2. The grids are passed unchanged to
       :func:`terrain.analyze_layers <ocean_sonar.terrain.analyze_layers>`.
    3. From every analysis dict the tuple
       ``(resolution, nx, ny, analysis)`` is fed, in layer order, to
       :func:`quality.assess <ocean_sonar.quality.assess>` and
       :func:`substrate.classify <ocean_sonar.substrate.classify>`
       together with ``slope_limit`` and ``roughness_limit``.
    4. :func:`crosspoint.evaluate <ocean_sonar.crosspoint.evaluate>` is
       called with ``crossings`` and ``tolerance``.
    5. The crosspoint, quality and substrate results are passed
       unchanged to :func:`report.summarize
       <ocean_sonar.report.summarize>`, whose ``overall`` verdict is
       used.

    The validation and first-error order is therefore that of
    :func:`~ocean_sonar.grid.build` (points, bounds, resolutions),
    then :func:`~ocean_sonar.terrain.analyze_layers`, then
    :func:`~ocean_sonar.quality.assess` (layers, ``slope_limit``,
    ``roughness_limit``), then :func:`~ocean_sonar.substrate.classify`,
    then :func:`~ocean_sonar.crosspoint.evaluate` (``crossings``,
    ``tolerance``), then :func:`~ocean_sonar.report.summarize`. All
    numeric types, rounding (six decimals, negative zero normalized)
    and key orders are exactly those produced by the underlying
    functions. Inputs are not modified.

    Returns a dict with keys in the order
    ``crosspoint, layers, overall``: ``crosspoint`` is the dict
    returned by :func:`~ocean_sonar.crosspoint.evaluate`, ``layers`` is
    a tuple with one dict per resolution and ``overall`` is the
    :func:`~ocean_sonar.report.summarize` verdict (``"pass"`` or
    ``"fail"``). Each layer dict has keys in the order
    ``resolution, nx, ny, cells, analysis, quality, substrate``:
    ``resolution``, ``nx``, ``ny`` and ``cells`` come from the
    corresponding :func:`~ocean_sonar.grid.build` layer, ``analysis``
    is the tuple from :func:`~ocean_sonar.terrain.analyze_layers`, and
    ``quality``/``substrate`` are the matching items returned by
    :func:`~ocean_sonar.quality.assess` and
    :func:`~ocean_sonar.substrate.classify`.
    """
    grids = grid.build(points, bounds, resolutions)
    analyzed = terrain.analyze_layers(grids)

    assess_layers = tuple(
        (item["resolution"], item["nx"], item["ny"], item["analysis"])
        for item in analyzed
    )
    qualities = quality.assess(
        assess_layers, slope_limit, roughness_limit
    )
    substrates = substrate.classify(
        assess_layers, slope_limit, roughness_limit
    )

    crosspoint_result = crosspoint.evaluate(crossings, tolerance)
    overall = report.summarize(
        crosspoint_result, qualities, substrates
    )["overall"]

    layers = tuple(
        {
            "resolution": analyzed[i]["resolution"],
            "nx": analyzed[i]["nx"],
            "ny": analyzed[i]["ny"],
            "cells": grids[i][3],
            "analysis": analyzed[i]["analysis"],
            "quality": qualities[i],
            "substrate": substrates[i],
        }
        for i in range(len(grids))
    )

    return {
        "crosspoint": crosspoint_result,
        "layers": layers,
        "overall": overall,
    }


def _check_cells(index, cells, nx, ny):
    if not isinstance(cells, tuple):
        raise TypeError(f"layers[{index}].cells must be a tuple")
    if len(cells) != nx * ny:
        raise ValueError(
            f"layers[{index}].cells must have nx * ny elements"
        )
    for j in range(len(cells)):
        prefix = f"layers[{index}].cells[{j}]: "
        cell = cells[j]
        if not isinstance(cell, tuple):
            raise TypeError(prefix + "must be a tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        count, mean = cell
        if type(count) is not int:
            raise TypeError(prefix + "count must be a non-bool int")
        if not count >= 0:
            raise ValueError(prefix + "count must be >= 0")
        if count == 0:
            if mean is not None:
                raise ValueError(prefix + "mean must be None when count is 0")
        else:
            if type(mean) is not float:
                raise TypeError(prefix + "mean must be a float")
            if not math.isfinite(mean):
                raise ValueError(prefix + "mean must be finite")
            if not mean >= 0:
                raise ValueError(prefix + "mean must be >= 0")


def _check_analysis(index, analysis, nx, ny):
    if not isinstance(analysis, tuple):
        raise TypeError(f"layers[{index}].analysis must be a tuple")
    if len(analysis) != nx * ny:
        raise ValueError(
            f"layers[{index}].analysis must have nx * ny elements"
        )
    for j in range(len(analysis)):
        prefix = f"layers[{index}].analysis[{j}]: "
        cell = analysis[j]
        if not isinstance(cell, tuple):
            raise TypeError(prefix + "must be a tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        slope, roughness = cell
        if slope is not None:
            if type(slope) is not float:
                raise TypeError(prefix + "slope must be a float")
            if not math.isfinite(slope):
                raise ValueError(prefix + "slope must be finite")
            if not slope >= 0:
                raise ValueError(prefix + "slope must be >= 0")
        if roughness is None:
            if slope is not None:
                raise ValueError(
                    prefix
                    + "roughness must not be None when slope is not None"
                )
        else:
            if type(roughness) is not float:
                raise TypeError(prefix + "roughness must be a float")
            if not math.isfinite(roughness):
                raise ValueError(prefix + "roughness must be finite")
            if not roughness >= 0:
                raise ValueError(prefix + "roughness must be >= 0")


def _check_quality(index, item):
    prefix = f"layers[{index}].quality: "
    if not isinstance(item, dict):
        raise TypeError(prefix + "must be a dict")
    if list(item.keys()) != list(_QUALITY_KEYS):
        raise TypeError(
            prefix
            + "keys must be in the order resolution, total, valid, "
            "coverage, slope_exceed, roughness_exceed"
        )

    resolution = item["resolution"]
    if type(resolution) is not float:
        raise TypeError(prefix + "resolution must be a float")
    if not math.isfinite(resolution):
        raise ValueError(prefix + "resolution must be finite")
    if resolution < 0:
        raise ValueError(prefix + "resolution must be >= 0")

    total = item["total"]
    if type(total) is not int:
        raise TypeError(prefix + "total must be a non-bool int")
    if not total > 0:
        raise ValueError(prefix + "total must be > 0")

    valid = item["valid"]
    if type(valid) is not int:
        raise TypeError(prefix + "valid must be a non-bool int")
    if not 0 <= valid <= total:
        raise ValueError(prefix + "valid must be in [0, total]")

    coverage = item["coverage"]
    if type(coverage) is not float:
        raise TypeError(prefix + "coverage must be a float")
    if not math.isfinite(coverage):
        raise ValueError(prefix + "coverage must be finite")
    if not 0 <= coverage <= 1:
        raise ValueError(prefix + "coverage must be in [0, 1]")

    for name in ("slope_exceed", "roughness_exceed"):
        value = item[name]
        if type(value) is not int:
            raise TypeError(prefix + f"{name} must be a non-bool int")
        if not 0 <= value <= total:
            raise ValueError(prefix + f"{name} must be in [0, total]")


def _check_substrate(index, item):
    prefix = f"layers[{index}].substrate: "
    if not isinstance(item, dict):
        raise TypeError(prefix + "must be a dict")
    if list(item.keys()) != list(_SUBSTRATE_KEYS):
        raise TypeError(
            prefix + "keys must be in the order resolution, nx, ny, classes, counts"
        )

    resolution = item["resolution"]
    if type(resolution) is not float:
        raise TypeError(prefix + "resolution must be a float")
    if not math.isfinite(resolution):
        raise ValueError(prefix + "resolution must be finite")
    if resolution < 0:
        raise ValueError(prefix + "resolution must be >= 0")

    nx = item["nx"]
    if type(nx) is not int:
        raise TypeError(prefix + "nx must be a non-bool int")
    if not nx > 0:
        raise ValueError(prefix + "nx must be > 0")

    ny = item["ny"]
    if type(ny) is not int:
        raise TypeError(prefix + "ny must be a non-bool int")
    if not ny > 0:
        raise ValueError(prefix + "ny must be > 0")

    classes = item["classes"]
    if not isinstance(classes, tuple):
        raise TypeError(prefix + "classes must be a tuple")
    if len(classes) != nx * ny:
        raise ValueError(prefix + "classes must have nx * ny elements")
    for j in range(len(classes)):
        cell_prefix = f"layers[{index}].substrate.classes[{j}]: "
        name = classes[j]
        if type(name) is not str:
            raise TypeError(cell_prefix + "must be a str")
        if name not in _COUNT_KEYS:
            raise ValueError(cell_prefix + f"unknown class {name!r}")

    counts = item["counts"]
    if not isinstance(counts, dict):
        raise TypeError(prefix + "counts must be a dict")
    if list(counts.keys()) != list(_COUNT_KEYS):
        raise TypeError(
            prefix + "counts keys must be in the order unknown, mud, sand, gravel, rock"
        )
    for name in _COUNT_KEYS:
        value = counts[name]
        if type(value) is not int:
            raise TypeError(prefix + f"counts.{name} must be a non-bool int")
        if value < 0:
            raise ValueError(prefix + f"counts.{name} must be >= 0")
        if value != classes.count(name):
            raise ValueError(prefix + f"counts.{name} must match classes")


def _check_layer(index, layer):
    prefix = f"layers[{index}]: "
    if not isinstance(layer, dict):
        raise TypeError(prefix + "must be a dict")
    if list(layer.keys()) != list(_LAYER_KEYS):
        raise TypeError(
            prefix
            + "keys must be in the order resolution, nx, ny, cells, "
            "analysis, quality, substrate"
        )

    resolution = layer["resolution"]
    if type(resolution) is not float:
        raise TypeError(prefix + "resolution must be a float")
    if not math.isfinite(resolution):
        raise ValueError(prefix + "resolution must be finite")
    if not resolution > 0:
        raise ValueError(prefix + "resolution must be > 0")

    nx = layer["nx"]
    if type(nx) is not int:
        raise TypeError(prefix + "nx must be a non-bool int")
    if not nx > 0:
        raise ValueError(prefix + "nx must be > 0")

    ny = layer["ny"]
    if type(ny) is not int:
        raise TypeError(prefix + "ny must be a non-bool int")
    if not ny > 0:
        raise ValueError(prefix + "ny must be > 0")

    _check_cells(index, layer["cells"], nx, ny)
    _check_analysis(index, layer["analysis"], nx, ny)

    quality_item = layer["quality"]
    _check_quality(index, quality_item)
    if quality_item["resolution"] != resolution:
        raise ValueError(
            prefix + "quality resolution must match layer resolution"
        )
    if quality_item["total"] != nx * ny:
        raise ValueError(prefix + "quality total must be nx * ny")

    substrate_item = layer["substrate"]
    _check_substrate(index, substrate_item)
    if substrate_item["resolution"] != resolution:
        raise ValueError(
            prefix + "substrate resolution must match layer resolution"
        )
    if substrate_item["nx"] != nx or substrate_item["ny"] != ny:
        raise ValueError(prefix + "substrate nx/ny must match layer nx/ny")


def serialize(product):
    """Serialize a :func:`build` result dict to UTF-8 JSON bytes.

    ``product`` must be the dict returned by :func:`build`, with keys
    exactly in the order ``crosspoint, layers, overall``:
    ``crosspoint`` is the dict returned by
    :func:`ocean_sonar.crosspoint.evaluate` (keys
    ``count, bias, rmse, max_abs, within_tolerance, quality``);
    ``layers`` is a non-empty tuple with one dict per resolution and
    ``overall`` is ``"pass"`` or ``"fail"``. Each layer dict has keys
    exactly in the order
    ``resolution, nx, ny, cells, analysis, quality, substrate``:
    ``resolution`` a finite float ``> 0``; ``nx``/``ny`` non-bool
    positive ints; ``cells`` and ``analysis`` tuples of length
    ``nx * ny`` whose items are the ``(count, mean)`` and
    ``(slope, roughness)`` tuples produced by
    :func:`ocean_sonar.grid.build` and
    :func:`ocean_sonar.terrain.analyze` — empty cells are
    ``(0, None)``/``(None, None)`` and boundary cells may also be
    ``(None, roughness)`` —; ``quality`` and ``substrate`` are
    the matching items returned by :func:`ocean_sonar.quality.assess`
    and :func:`ocean_sonar.substrate.classify`. ``overall`` is
    recomputed with the :func:`ocean_sonar.report.summarize` rule from
    ``crosspoint`` and the per-layer ``quality``/``substrate`` values.

    Validation order, stopping at the first error: the top-level
    container and key order, then ``crosspoint``, then the layers tuple
    and each layer in index order — per layer its container, key order
    and ``resolution``/``nx``/``ny``, then ``cells``, then
    ``analysis``, then ``quality``, then ``substrate`` — and finally
    ``overall``. Container, key-order and field-type errors raise
    ``TypeError``; length, finiteness, range, consistency and enum
    errors (including an ``overall`` that disagrees with the recomputed
    verdict) raise ``ValueError``. The input is not modified.

    On success the product is encoded as UTF-8 JSON with the key order
    preserved, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation and no trailing newline.
    Floats are first rounded with ``round(float(v), 6)`` and negative
    zero is normalized to ``0.0``; tuples are recursively converted to
    arrays. Any JSON or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(product, dict):
        raise TypeError("product must be a dict")
    if list(product.keys()) != list(_PRODUCT_KEYS):
        raise TypeError(
            "product keys must be in the order crosspoint, layers, overall"
        )

    crosspoint_result = product["crosspoint"]
    layers = product["layers"]
    _check_crosspoint(crosspoint_result)

    if not isinstance(layers, tuple):
        raise TypeError("layers must be a tuple")
    if len(layers) == 0:
        raise ValueError("layers must be non-empty")

    for i in range(len(layers)):
        _check_layer(i, layers[i])

    overall = product["overall"]
    if type(overall) is not str:
        raise TypeError("overall must be a str")
    if overall not in _QUALITY_VALUES:
        raise ValueError("overall must be 'pass' or 'fail'")

    terrain = tuple(layer["quality"] for layer in layers)
    substrates = tuple(layer["substrate"] for layer in layers)
    recomputed = _overall_verdict(crosspoint_result, terrain, substrates)
    if overall != recomputed:
        raise ValueError(
            "overall is inconsistent with crosspoint, layers and substrate"
        )

    try:
        text = json.dumps(
            _to_jsonable(product),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"product: could not be serialized to JSON: {exc}"
        ) from exc
