"""End-to-end bathymetric product pipeline.

Runs the full chain in one call: grid binning
(:mod:`ocean_sonar.grid`), terrain analysis
(:mod:`ocean_sonar.terrain`), quality assessment
(:mod:`ocean_sonar.quality`), substrate classification
(:mod:`ocean_sonar.substrate`), crosspoint evaluation
(:mod:`ocean_sonar.crosspoint`) and the combined verdict
(:mod:`ocean_sonar.report`). :func:`serialize` encodes a :func:`build`
product dict as canonical UTF-8 JSON bytes.
"""

from __future__ import annotations

import json
import math

from . import crosspoint, grid, quality, report, substrate, terrain

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
_COUNT_KEYS = ("unknown", "mud", "sand", "gravel", "rock")
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


def _check_cells(cells, nx, ny, index):
    prefix = f"layers[{index}].cells"
    if not isinstance(cells, tuple):
        raise TypeError(prefix + " must be a tuple")
    if len(cells) != nx * ny:
        raise ValueError(prefix + " must have nx * ny elements")

    for j in range(len(cells)):
        cell_prefix = f"layers[{index}].cells[{j}]: "
        cell = cells[j]
        if not isinstance(cell, tuple):
            raise TypeError(cell_prefix + "must be a tuple")
        if len(cell) != 2:
            raise ValueError(cell_prefix + "must have 2 elements")
        count, mean = cell
        if type(count) is not int:
            raise TypeError(cell_prefix + "count must be a non-bool int")
        if not count >= 0:
            raise ValueError(cell_prefix + "count must be >= 0")
        if count == 0:
            if mean is not None:
                raise ValueError(cell_prefix + "mean must be None when count is 0")
        else:
            if type(mean) is not float:
                raise TypeError(cell_prefix + "mean must be a float")
            if not math.isfinite(mean):
                raise ValueError(cell_prefix + "mean must be finite")
            if not mean >= 0:
                raise ValueError(cell_prefix + "mean must be >= 0")


def _check_analysis(analysis, nx, ny, index):
    prefix = f"layers[{index}].analysis"
    if not isinstance(analysis, tuple):
        raise TypeError(prefix + " must be a tuple")
    if len(analysis) != nx * ny:
        raise ValueError(prefix + " must have nx * ny elements")

    for j in range(len(analysis)):
        cell_prefix = f"layers[{index}].analysis[{j}]: "
        cell = analysis[j]
        if not isinstance(cell, tuple):
            raise TypeError(cell_prefix + "must be a tuple")
        if len(cell) != 2:
            raise ValueError(cell_prefix + "must have 2 elements")
        slope, roughness = cell
        if slope is not None:
            if type(slope) is not float:
                raise TypeError(cell_prefix + "slope must be None or a float")
            if not math.isfinite(slope):
                raise ValueError(cell_prefix + "slope must be finite")
            if not slope >= 0:
                raise ValueError(cell_prefix + "slope must be >= 0")
        if slope is None and roughness is None:
            continue
        if type(roughness) is not float:
            raise TypeError(cell_prefix + "roughness must be a float")
        if not math.isfinite(roughness):
            raise ValueError(cell_prefix + "roughness must be finite")
        if not roughness >= 0:
            raise ValueError(cell_prefix + "roughness must be >= 0")


def _check_quality(item, resolution, nx, ny, index):
    prefix = f"layers[{index}].quality: "
    if not isinstance(item, dict):
        raise TypeError(prefix + "must be a dict")
    if list(item.keys()) != list(_QUALITY_KEYS):
        raise TypeError(
            prefix
            + "keys must be in the order resolution, total, valid, "
            "coverage, slope_exceed, roughness_exceed"
        )

    if type(item["resolution"]) is not float:
        raise TypeError(prefix + "resolution must be a float")
    if not math.isfinite(item["resolution"]):
        raise ValueError(prefix + "resolution must be finite")
    if item["resolution"] < 0:
        raise ValueError(prefix + "resolution must be >= 0")
    if item["resolution"] != resolution:
        raise ValueError(prefix + "resolution must match the layer resolution")

    total = nx * ny
    if type(item["total"]) is not int:
        raise TypeError(prefix + "total must be a non-bool int")
    if item["total"] != total:
        raise ValueError(prefix + "total must equal nx * ny")

    if type(item["valid"]) is not int:
        raise TypeError(prefix + "valid must be a non-bool int")
    if not 0 <= item["valid"] <= total:
        raise ValueError(prefix + "valid must be in [0, total]")

    if type(item["coverage"]) is not float:
        raise TypeError(prefix + "coverage must be a float")
    if not math.isfinite(item["coverage"]):
        raise ValueError(prefix + "coverage must be finite")
    if not 0 <= item["coverage"] <= 1:
        raise ValueError(prefix + "coverage must be in [0, 1]")

    for name in ("slope_exceed", "roughness_exceed"):
        if type(item[name]) is not int:
            raise TypeError(prefix + f"{name} must be a non-bool int")
        if not 0 <= item[name] <= total:
            raise ValueError(prefix + f"{name} must be in [0, total]")


def _check_substrate(item, resolution, nx, ny, index):
    prefix = f"layers[{index}].substrate: "
    if not isinstance(item, dict):
        raise TypeError(prefix + "must be a dict")
    if list(item.keys()) != list(_SUBSTRATE_KEYS):
        raise TypeError(
            prefix + "keys must be in the order resolution, nx, ny, classes, counts"
        )

    if type(item["resolution"]) is not float:
        raise TypeError(prefix + "resolution must be a float")
    if not math.isfinite(item["resolution"]):
        raise ValueError(prefix + "resolution must be finite")
    if item["resolution"] < 0:
        raise ValueError(prefix + "resolution must be >= 0")
    if item["resolution"] != resolution:
        raise ValueError(prefix + "resolution must match the layer resolution")

    for name, value in (("nx", item["nx"]), ("ny", item["ny"])):
        if type(value) is not int:
            raise TypeError(prefix + f"{name} must be a non-bool int")
        if not value > 0:
            raise ValueError(prefix + f"{name} must be > 0")
    if item["nx"] != nx or item["ny"] != ny:
        raise ValueError(prefix + "nx and ny must match the layer dimensions")

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


def _check_layer(layer, index):
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
    if resolution < 0:
        raise ValueError(prefix + "resolution must be >= 0")

    nx = layer["nx"]
    ny = layer["ny"]
    for name, value in (("nx", nx), ("ny", ny)):
        if type(value) is not int:
            raise TypeError(prefix + f"{name} must be a non-bool int")
        if not value > 0:
            raise ValueError(prefix + f"{name} must be > 0")

    _check_cells(layer["cells"], nx, ny, index)
    _check_analysis(layer["analysis"], nx, ny, index)
    _check_quality(layer["quality"], resolution, nx, ny, index)
    _check_substrate(layer["substrate"], resolution, nx, ny, index)

    return layer["quality"], layer["substrate"]


def _to_jsonable(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(float(value), 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, (tuple, list)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def serialize(product):
    """Serialize a :func:`build` product dict to UTF-8 JSON bytes.

    ``product`` must be the dict returned by :func:`build`, with keys
    exactly in the order ``crosspoint, layers, overall``.
    ``crosspoint`` must satisfy the :func:`~ocean_sonar.crosspoint.
    evaluate` result contract (keys ``count, bias, rmse, max_abs,
    within_tolerance, quality`` in that order with the same types and
    ranges). ``layers`` must be a non-empty tuple; each layer must have
    keys exactly in the order ``resolution, nx, ny, cells, analysis,
    quality, substrate``: ``resolution`` a finite non-negative float
    and ``nx``/``ny`` non-bool positive ints; ``cells`` and
    ``analysis`` are tuples of length ``nx * ny`` whose items are
    two-element tuples, respectively ``(count, mean)`` as produced by
    :func:`~ocean_sonar.grid.build` (``(0, None)`` for empty cells) and
    ``(slope, roughness)`` as produced by
    :func:`~ocean_sonar.terrain.analyze` (``(None, None)`` for empty
    cells); ``quality`` and ``substrate`` must satisfy the
    :func:`~ocean_sonar.quality.assess` and
    :func:`~ocean_sonar.substrate.classify` result contracts, and their
    ``resolution`` (and substrate ``nx``/``ny``) must match the layer.
    ``overall`` must be ``"pass"`` or ``"fail"`` and is recomputed
    following the :func:`~ocean_sonar.report.summarize` rules.

    Validation order, stopping at the first error: the top-level
    container and key order, ``crosspoint``, the ``layers`` container,
    then per layer in index order its fields, ``cells``, ``analysis``,
    ``quality`` and ``substrate``, and finally ``overall``. Container,
    key-order and field-type mismatches raise ``TypeError``; length,
    finiteness, range, consistency (including an ``overall`` value that
    disagrees with the recomputed verdict) and enum errors raise
    ``ValueError``. The input is not modified.

    On success the product is encoded as UTF-8 JSON with the key order
    preserved, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation and no trailing newline.
    Tuples are recursively converted to arrays and floats are first
    rounded with ``round(float(v), 6)`` with negative zero normalized
    to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(product, dict):
        raise TypeError("product must be a dict")
    if list(product.keys()) != list(_PRODUCT_KEYS):
        raise TypeError(
            "product keys must be in the order crosspoint, layers, overall"
        )

    report._check_crosspoint(product["crosspoint"])

    layers = product["layers"]
    if not isinstance(layers, tuple):
        raise TypeError("layers must be a tuple")
    if len(layers) == 0:
        raise ValueError("layers must be non-empty")

    qualities = []
    substrates = []
    for i in range(len(layers)):
        quality_item, substrate_item = _check_layer(layers[i], i)
        qualities.append(quality_item)
        substrates.append(substrate_item)

    overall = product["overall"]
    if type(overall) is not str:
        raise TypeError("overall must be a str")
    if overall not in _QUALITY_VALUES:
        raise ValueError("overall must be 'pass' or 'fail'")

    recomputed = report._overall_verdict(
        product["crosspoint"], qualities, substrates
    )
    if overall != recomputed:
        raise ValueError(
            "overall is inconsistent with crosspoint, quality and substrate"
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
        raise ValueError(f"product: could not be serialized to JSON: {exc}") from exc
