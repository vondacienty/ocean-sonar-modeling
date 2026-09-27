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
    _CROSSPOINT_KEYS,
    _from_jsonable,
    _overall_verdict,
    _reject_json_constant,
    _to_jsonable,
)

__all__ = [
    "build",
    "dashboard",
    "dashboard_summary",
    "serialize",
    "render",
    "write",
    "metrics",
    "load",
    "quality_report",
    "load_quality_report",
    "quality_trend",
    "serialize_quality_trend",
    "load_quality_trend",
    "render_quality_trend",
]

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
_QUALITY_REPORT_KEYS = (
    "layers",
    "total",
    "valid",
    "coverage",
    "terrain_exceed",
    "unknown",
    "worst",
    "crosspoint",
    "quality",
)
_QUALITY_REPORT_INT_KEYS = (
    "layers",
    "total",
    "valid",
    "terrain_exceed",
    "unknown",
    "worst",
)
_QUALITY_TREND_KEYS = ("changes", "worst", "quality")
_QUALITY_TREND_ITEM_KEYS = (
    "index",
    "coverage_delta",
    "terrain_exceed_delta",
    "unknown_delta",
    "quality",
)


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


def dashboard(
    points,
    bounds,
    resolutions,
    crossings,
    tolerances,
    slope_limit=5.0,
    roughness_limit=1.0,
):
    """Build the gridded terrain product and the combined dashboard in one call.

    The stages run strictly in this order, exactly once each and with
    no interleaving, and every exception from any stage short-circuits
    and is propagated unchanged:

    1. :func:`grid.build(points, bounds, resolutions)
       <ocean_sonar.grid.build>` bins the soundings into one grid per
       resolution; each layer is ``(resolution, nx, ny, cells)``.
    2. The grids are passed unchanged to
       :func:`terrain.analyze_layers <ocean_sonar.terrain.analyze_layers>`.
    3. From every analysis dict the tuple
       ``(resolution, nx, ny, analysis)`` is built, in input order, and
       these tuples are passed together with ``crossings``,
       ``tolerances``, ``slope_limit`` and ``roughness_limit`` to
       :func:`report.dashboard <ocean_sonar.report.dashboard>`.

    The validation and first-error order is therefore that of
    :func:`~ocean_sonar.grid.build` (points, bounds, resolutions),
    then :func:`~ocean_sonar.terrain.analyze_layers`, then the
    :func:`~ocean_sonar.report.dashboard` order (its internal
    ``crosspoint.dashboard``, ``assess`` and ``classify`` parameter
    checks, including their index prefixes). Inputs are neither
    modified nor reordered and no other function is called.

    Returns the dict returned by :func:`~ocean_sonar.report.dashboard`
    unchanged, with keys in the order
    ``crosspoint, terrain, substrate, quality``; the first three items
    keep their identity and ``quality`` is a tuple of ``str`` with one
    entry per tolerance in ``tolerances`` order. All nested key orders,
    tuple levels, types and six-decimal rounding are exactly those
    produced by :func:`~ocean_sonar.report.dashboard`.
    """
    grids = grid.build(points, bounds, resolutions)
    analyzed = terrain.analyze_layers(grids)

    layers = tuple(
        (item["resolution"], item["nx"], item["ny"], item["analysis"])
        for item in analyzed
    )

    return report.dashboard(
        crossings,
        tolerances,
        layers,
        slope_limit,
        roughness_limit,
    )


def dashboard_summary(
    points,
    bounds,
    resolutions,
    crossings,
    tolerances,
    slope_limit=5.0,
    roughness_limit=1.0,
) -> dict:
    """Build the gridded terrain product and the dashboard summary in one call.

    The stages run strictly in this order, exactly once each and with
    no interleaving, and every exception from any stage short-circuits
    and is propagated unchanged:

    1. :func:`grid.build(points, bounds, resolutions)
       <ocean_sonar.grid.build>` bins the soundings into one grid per
       resolution; each layer is ``(resolution, nx, ny, cells)``.
    2. The grids are passed unchanged to
       :func:`terrain.analyze_layers <ocean_sonar.terrain.analyze_layers>`.
    3. From every analysis dict the tuple
       ``(resolution, nx, ny, analysis)`` is built, in input order, and
       these tuples are passed together with ``crossings``,
       ``tolerances``, ``slope_limit`` and ``roughness_limit`` to
       :func:`report.dashboard_summary
       <ocean_sonar.report.dashboard_summary>`.

    The validation and first-error order is therefore that of
    :func:`~ocean_sonar.grid.build` (points, bounds, resolutions),
    then :func:`~ocean_sonar.terrain.analyze_layers`, then the
    :func:`~ocean_sonar.report.dashboard_summary` order. No other
    combining function is called; inputs are neither modified nor
    reordered.

    Returns the dict returned by
    :func:`~ocean_sonar.report.dashboard_summary` unchanged (identity
    preserved), with keys in the order ``dashboard, summary``; all
    nested key orders, tuple levels, types, tolerance order, rounding,
    negative-zero handling and quality judgements are exactly those
    produced by :func:`~ocean_sonar.report.dashboard_summary`.
    """
    grids = grid.build(points, bounds, resolutions)
    analyzed = terrain.analyze_layers(grids)

    layers = tuple(
        (item["resolution"], item["nx"], item["ny"], item["analysis"])
        for item in analyzed
    )

    return report.dashboard_summary(
        crossings,
        tolerances,
        layers,
        slope_limit,
        roughness_limit,
    )


def _check_product_crosspoint(item):
    _check_crosspoint(item)
    expected = (
        "pass" if item["within_tolerance"] == item["count"] else "fail"
    )
    if item["quality"] != expected:
        raise ValueError(
            "crosspoint: quality must be 'pass' when within_tolerance "
            "== count and 'fail' when within_tolerance < count"
        )


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
    ``count, bias, rmse, max_abs, within_tolerance, quality``) with
    ``count`` a positive non-bool int, ``within_tolerance`` a non-bool
    int in ``[0, count]``, ``bias``/``rmse``/``max_abs`` finite floats
    (the latter two ``>= 0``) and ``quality`` equal to ``"pass"``
    exactly when ``within_tolerance == count`` and to ``"fail"``
    exactly when ``within_tolerance < count``;
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
    _check_product_crosspoint(crosspoint_result)

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


def _format_scalar(value):
    if value is None:
        return "None"
    if isinstance(value, float):
        return format(value, ".6f")
    return str(value)


def render(product) -> str:
    """Render a :func:`build` result dict as a plain-text report.

    ``product`` is first validated with :func:`serialize`, so it must
    satisfy that function's full contract; every validation exception
    is propagated unchanged and the input is not modified.

    On success returns a ``str`` of ``"\\n"``-joined lines with no
    trailing newline: an ``OVERALL=<overall>`` line; a
    ``CROSSPOINT=`` line with ``count, bias, rmse, max_abs,
    within_tolerance, quality`` as semicolon-joined ``key=value``
    fields; then, per layer in index order, five lines:
    ``LAYER[i]=resolution=<r>;nx=<nx>;ny=<ny>``; ``CELLS[i]=`` with
    the layer's ``(count, mean)`` cells in their y-then-x tuple order,
    the two values of each cell joined by a comma and the cells joined
    by ``|`` (an empty mean renders as ``None``); ``ANALYSIS[i]=`` with
    the ``(slope, roughness)`` pairs in the same layout (a missing
    slope or roughness renders as ``None``); ``QUALITY[i]=`` with the
    fields ``resolution, total, valid, coverage, slope_exceed,
    roughness_exceed``; and ``SUBSTRATE[i]=`` with the fields
    ``resolution, nx, ny, classes, counts``. ``classes`` is the class
    names joined by commas with no spaces; ``counts`` lists
    ``unknown, mud, sand, gravel, rock`` in that order joined by
    commas. Floats are formatted with ``format(v, ".6f")``, ints in
    decimal and ``None`` as ``"None"``.
    """
    serialize(product)

    lines = [f"OVERALL={product['overall']}"]

    crosspoint = product["crosspoint"]
    cp_fields = ";".join(
        f"{key}={_format_scalar(crosspoint[key])}" for key in _CROSSPOINT_KEYS
    )
    lines.append(f"CROSSPOINT={cp_fields}")

    for i, layer in enumerate(product["layers"]):
        lines.append(
            f"LAYER[{i}]=resolution={format(layer['resolution'], '.6f')}"
            f";nx={layer['nx']};ny={layer['ny']}"
        )

        cell_fields = "|".join(
            f"{count},{_format_scalar(mean)}"
            for count, mean in layer["cells"]
        )
        lines.append(f"CELLS[{i}]={cell_fields}")

        analysis_fields = "|".join(
            f"{_format_scalar(slope)},{_format_scalar(roughness)}"
            for slope, roughness in layer["analysis"]
        )
        lines.append(f"ANALYSIS[{i}]={analysis_fields}")

        quality = layer["quality"]
        quality_fields = ";".join(
            f"{key}={_format_scalar(quality[key])}" for key in _QUALITY_KEYS
        )
        lines.append(f"QUALITY[{i}]={quality_fields}")

        substrate = layer["substrate"]
        substrate_fields = ";".join(
            (
                f"resolution={format(substrate['resolution'], '.6f')}",
                f"nx={substrate['nx']}",
                f"ny={substrate['ny']}",
                f"classes={','.join(substrate['classes'])}",
                "counts="
                + ",".join(
                    str(substrate["counts"][name]) for name in _COUNT_KEYS
                ),
            )
        )
        lines.append(f"SUBSTRATE[{i}]={substrate_fields}")

    return "\n".join(lines)


def write(product, path) -> bytes:
    """Serialize a :func:`build` result and overwrite ``path`` with it.

    The bytes written are exactly those returned by :func:`serialize`
    (compact UTF-8 JSON, key order preserved, no trailing newline);
    ``product`` must therefore satisfy the full :func:`serialize`
    contract and is not modified.

    Validation order, stopping at the first error: ``product`` is
    serialized first — :func:`serialize` is called once and its
    ``TypeError``/``ValueError`` exceptions are propagated unchanged —
    and only then is ``path`` validated: a non-str ``path`` raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. Because
    serialization happens before the file is touched, a serialization
    failure never creates or modifies ``path``.

    On success the bytes are written by overwriting ``path`` opened in
    binary mode (``"wb"``), with no added newline. A missing parent
    directory raises ``FileNotFoundError``, an existing directory at
    ``path`` raises ``IsADirectoryError`` and every other ``OSError``
    is propagated unchanged.

    Returns the JSON document as ``bytes``.
    """
    data = serialize(product)

    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "wb") as handle:
        handle.write(data)

    return data


def metrics(product):
    """Collect per-layer terrain metrics for a :func:`build` result dict.

    ``product`` must be the dict returned by :func:`build`. It is first
    validated with :func:`serialize`, so it must satisfy that
    function's full contract; every validation exception is propagated
    unchanged and the input is not modified.

    Afterwards, for every layer of ``product["layers"]`` in input order
    and exactly once, :func:`ocean_sonar.terrain.metrics` is called with
    that layer's ``resolution``, ``nx``, ``ny`` and ``cells`` passed
    unchanged (no reordering or copying). Every exception from these
    calls is also propagated unchanged.

    Returns a tuple with one dict per layer in layer order; each dict is
    the object returned by the matching
    :func:`~ocean_sonar.terrain.metrics` call, passed through unchanged
    with keys in the order ``resolution, nx, ny, total, valid,
    coverage, min_depth, max_depth, mean_depth, volume``. Numeric
    values, ``None`` entries, six-decimal rounding and negative-zero
    normalization are therefore exactly those produced by
    :func:`~ocean_sonar.terrain.metrics`. The input is not modified.
    """
    serialize(product)

    return tuple(
        terrain.metrics(
            layer["resolution"],
            layer["nx"],
            layer["ny"],
            layer["cells"],
        )
        for layer in product["layers"]
    )


def load(path):
    """Load a :func:`serialize`-produced JSON product from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by :func:`serialize` for
    the same value: compact UTF-8 JSON with no BOM and no trailing
    newline. A BOM, a trailing newline, a UTF-8 decoding failure, a
    JSON parsing failure or a ``NaN``/``Infinity`` constant raises
    ``ValueError``. The decoded value must satisfy the full
    :func:`serialize` contract — top-level key order
    ``crosspoint, layers, overall`` and all nested key orders, tuple
    lengths, field types/ranges and consistency (including ``counts``
    matching ``classes`` and an ``overall`` consistent with the
    recomputed verdict) — and the file bytes must equal the canonical
    re-serialization of the decoded value byte for byte; any
    key-order, type, range, consistency or normalization-byte mismatch
    raises ``ValueError``.

    JSON arrays are recursively converted to tuples and floats are
    rounded with ``round(float(v), 6)`` with negative zero normalized
    to ``0.0``, mirroring :func:`serialize`.

    Returns the product as a dict with keys in the order
    ``crosspoint, layers, overall``.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    product = _from_jsonable(parsed)
    try:
        canonical = serialize(product)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"file does not contain a valid product: {exc}") from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize output"
        )

    return product


def quality_report(path) -> bytes:
    """Summarize a :func:`serialize`-produced JSON product as quality bytes.

    Exactly one call to :func:`load` is made with ``path`` unchanged and
    no other work happens before it; the ``path`` validation contract,
    the read behavior, every exception (propagated unchanged) and the
    file invariance of :func:`load` therefore apply here verbatim. The
    product file is not modified.

    Let ``P`` be the dict returned by that single :func:`load` call.
    The report is computed from ``P`` alone, without modifying it, and
    encoded with keys exactly in the order ``layers, total, valid,
    coverage, terrain_exceed, unknown, worst, crosspoint, quality``:

    - ``layers``: the number of layers, ``len(P["layers"])``.
    - ``total``/``valid``: the sums of ``quality.total`` and
      ``quality.valid`` over all layers.
    - ``coverage``: ``round(float(valid / total), 6)``.
    - ``terrain_exceed``: the sum of ``quality.slope_exceed`` and
      ``quality.roughness_exceed`` over all layers.
    - ``unknown``: the sum of ``substrate.counts.unknown`` over all
      layers.
    - ``worst``: the index of the layer maximizing the unrounded tuple
      ``(layer unknown, layer slope_exceed + roughness_exceed,
      -layer coverage, -index)``.
    - ``crosspoint``: ``P["crosspoint"]["quality"]``.
    - ``quality``: ``P["overall"]``.

    All counts and ``worst`` are ``int`` and ``coverage`` is a
    ``float``. The JSON byte specification follows :func:`serialize`:
    UTF-8, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; floats are rounded with ``round(float(v), 6)`` and
    negative zero is normalized to ``0.0``. Any JSON or UTF-8 encoding
    failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    product = load(path)

    layers = product["layers"]
    total = 0
    valid = 0
    terrain_exceed = 0
    unknown = 0
    worst = 0
    worst_key = None
    for i in range(len(layers)):
        quality = layers[i]["quality"]
        total += quality["total"]
        valid += quality["valid"]
        exceed = quality["slope_exceed"] + quality["roughness_exceed"]
        terrain_exceed += exceed
        layer_unknown = layers[i]["substrate"]["counts"]["unknown"]
        unknown += layer_unknown
        key = (layer_unknown, exceed, -quality["coverage"], -i)
        if worst_key is None or key > worst_key:
            worst_key = key
            worst = i

    report = {
        "layers": len(layers),
        "total": total,
        "valid": valid,
        "coverage": round(float(valid / total), 6),
        "terrain_exceed": terrain_exceed,
        "unknown": unknown,
        "worst": worst,
        "crosspoint": product["crosspoint"]["quality"],
        "quality": product["overall"],
    }

    return _dump_quality_report(report)


def _dump_quality_report(report) -> bytes:
    try:
        text = json.dumps(
            _to_jsonable(report),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"quality report: could not be serialized to JSON: {exc}"
        ) from exc


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _check_quality_report(report):
    if not isinstance(report, dict):
        raise ValueError("quality report must be a JSON object")
    if list(report.keys()) != list(_QUALITY_REPORT_KEYS):
        raise ValueError(
            "quality report keys must be in the order "
            "layers, total, valid, coverage, terrain_exceed, unknown, "
            "worst, crosspoint, quality"
        )

    for name in _QUALITY_REPORT_INT_KEYS:
        value = report[name]
        if type(value) is not int:
            raise ValueError(f"quality report: {name} must be a non-bool int")

    layers = report["layers"]
    if not layers > 0:
        raise ValueError("quality report: layers must be > 0")

    total = report["total"]
    if not total > 0:
        raise ValueError("quality report: total must be > 0")

    valid = report["valid"]
    if not 0 <= valid <= total:
        raise ValueError("quality report: valid must be in [0, total]")

    terrain_exceed = report["terrain_exceed"]
    if terrain_exceed < 0:
        raise ValueError("quality report: terrain_exceed must be >= 0")

    unknown = report["unknown"]
    if unknown < 0:
        raise ValueError("quality report: unknown must be >= 0")

    worst = report["worst"]
    if not 0 <= worst < layers:
        raise ValueError("quality report: worst must be in [0, layers)")

    coverage = report["coverage"]
    if type(coverage) is not float:
        raise ValueError("quality report: coverage must be a float")
    if not math.isfinite(coverage):
        raise ValueError("quality report: coverage must be finite")
    expected_coverage = round(float(valid / total), 6)
    if expected_coverage == 0:
        expected_coverage = 0.0
    if coverage != expected_coverage:
        raise ValueError(
            "quality report: coverage must equal round(float(valid / total), 6)"
        )
    if coverage == 0.0 and math.copysign(1.0, coverage) < 0:
        raise ValueError("quality report: coverage must not be negative zero")

    crosspoint = report["crosspoint"]
    if type(crosspoint) is not str:
        raise ValueError("quality report: crosspoint must be a str")
    if crosspoint not in _QUALITY_VALUES:
        raise ValueError("quality report: crosspoint must be 'pass' or 'fail'")

    quality = report["quality"]
    if type(quality) is not str:
        raise ValueError("quality report: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("quality report: quality must be 'pass' or 'fail'")

    expected_quality = (
        "pass"
        if crosspoint == "pass" and terrain_exceed == 0 and unknown == 0
        else "fail"
    )
    if quality != expected_quality:
        raise ValueError(
            "quality report: quality must be 'pass' exactly when "
            "crosspoint is 'pass' and terrain_exceed and unknown are both 0"
        )


def load_quality_report(path) -> dict:
    """Load a :func:`quality_report`-produced JSON quality report from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by :func:`quality_report`
    for the same value: compact UTF-8 JSON with no BOM and no trailing
    newline. A BOM, a trailing newline, a UTF-8 decoding failure, a JSON
    parsing failure, a ``NaN``/``Infinity`` constant or a repeated JSON
    object key raises ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``layers, total, valid, coverage, terrain_exceed, unknown,
    worst, crosspoint, quality``. Every field except ``coverage`` and
    the two quality fields must be a non-bool int: ``layers`` and
    ``total`` must be ``> 0``, ``valid`` in ``[0, total]``,
    ``terrain_exceed`` and ``unknown`` ``>= 0`` and ``worst`` in
    ``[0, layers)``. ``coverage`` must be a finite non-bool float equal
    to ``round(float(valid / total), 6)`` and must not be negative
    zero; ``crosspoint`` and ``quality`` must each be ``"pass"`` or
    ``"fail"``, and ``quality`` must be ``"pass"`` exactly when
    ``crosspoint`` is ``"pass"`` and both exception counts are ``0``.
    Finally the file bytes must equal the canonical re-encoding of the
    decoded value byte for byte. Any key-order, type, range, relation,
    parse or canonical-byte mismatch raises ``ValueError``.

    Returns the report as a dict with the keys in the order above; the
    file is never modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        _check_quality_report(parsed)
        canonical = _dump_quality_report(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid quality report: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical quality_report output"
        )

    return parsed


def quality_trend(paths) -> dict:
    """Compare successive :func:`load_quality_report` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_quality_report` is then called exactly once per path,
    in input order; any exception it raises is propagated unchanged.
    The input and the loaded files are not modified.

    Every loaded report must have the same ``layers`` and ``total``
    values as the first one; otherwise a ``ValueError`` is raised.

    For each successive pair ``i = 1..n-1`` the unrounded deltas are
    ``dc = coverage_i - coverage_(i-1)``,
    ``dt = terrain_exceed_i - terrain_exceed_(i-1)`` and
    ``du = unknown_i - unknown_(i-1)``; a comparison fails (``q`` is
    ``"fail"``) when ``dc < 0``, ``dt > 0``, ``du > 0`` or its quality
    changes from ``"pass"`` to ``"fail"``, and is ``"pass"`` otherwise.

    Returns a dict with keys in the order ``changes, worst, quality``:
    ``changes`` is a tuple with one dict per pair (in ``i`` order), each
    with keys in the order
    ``index, coverage_delta, terrain_exceed_delta, unknown_delta,
    quality`` — ``index`` is ``i``, ``coverage_delta`` is
    ``round(float(dc), 6)`` (negative zero normalized to ``0.0``),
    ``terrain_exceed_delta``/``unknown_delta`` are the unrounded ``dt``
    and ``du`` and ``quality`` is ``q``. ``index``, ``dt`` and ``du``
    are non-bool ints and ``coverage_delta`` is a float. ``worst`` is
    the ``changes`` item minimizing the *unrounded* tuple
    ``(dc, -dt, -du, i)``; ``quality`` is ``"pass"`` exactly when every
    ``q`` is ``"pass"`` and ``"fail"`` otherwise. Items are not sorted,
    values are not recomputed and no other keys are added.
    """
    if not isinstance(paths, (list, tuple)):
        raise TypeError("paths must be a list or tuple")
    if len(paths) < 2:
        raise ValueError("paths must contain at least 2 items")
    for i in range(len(paths)):
        prefix = f"paths[{i}]: "
        if not isinstance(paths[i], str):
            raise TypeError(prefix + "must be a str")
        if paths[i] == "":
            raise ValueError(prefix + "must not be empty")

    reports = [load_quality_report(path) for path in paths]

    first_layers = reports[0]["layers"]
    first_total = reports[0]["total"]
    for i in range(1, len(reports)):
        if reports[i]["layers"] != first_layers:
            raise ValueError(
                f"quality report at paths[{i}] layers {reports[i]['layers']} "
                f"does not match {first_layers}"
            )
        if reports[i]["total"] != first_total:
            raise ValueError(
                f"quality report at paths[{i}] total {reports[i]['total']} "
                f"does not match {first_total}"
            )

    changes = []
    worst_item = None
    worst_key = None
    overall = "pass"
    for i in range(1, len(reports)):
        previous = reports[i - 1]
        current = reports[i]
        dc = current["coverage"] - previous["coverage"]
        dt = current["terrain_exceed"] - previous["terrain_exceed"]
        du = current["unknown"] - previous["unknown"]
        if (
            dc < 0
            or dt > 0
            or du > 0
            or (previous["quality"] == "pass" and current["quality"] == "fail")
        ):
            verdict = "fail"
            overall = "fail"
        else:
            verdict = "pass"

        coverage_delta = round(float(dc), 6)
        if coverage_delta == 0:
            coverage_delta = 0.0

        item = {
            "index": int(i),
            "coverage_delta": coverage_delta,
            "terrain_exceed_delta": int(dt),
            "unknown_delta": int(du),
            "quality": verdict,
        }
        changes.append(item)

        key = (dc, -dt, -du, i)
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "changes": tuple(changes),
        "worst": worst_item,
        "quality": overall,
    }


def _dump_quality_trend(trend) -> bytes:
    try:
        text = json.dumps(
            _to_jsonable(trend),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"quality trend: could not be serialized to JSON: {exc}"
        ) from exc


def serialize_quality_trend(paths) -> bytes:
    """Serialize the :func:`quality_trend` comparison of ``paths`` to bytes.

    Exactly one call to :func:`quality_trend` is made with ``paths``
    unchanged and no other work happens before it; the ``paths``
    validation contract, the per-path :func:`load_quality_report`
    behavior, every exception (propagated unchanged) and the
    input/file invariance of :func:`quality_trend` therefore apply
    here verbatim. Neither ``paths`` nor the loaded files are
    modified.

    Let ``T`` be the dict returned by that single :func:`quality_trend`
    call. It is encoded with keys exactly in the order ``changes,
    worst, quality``; the ``changes`` tuple is converted to a JSON
    array and each item keeps its key order ``index, coverage_delta,
    terrain_exceed_delta, unknown_delta, quality``.

    The JSON byte specification follows :func:`quality_report`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; floats are rounded with ``round(float(v), 6)`` and
    negative zero is normalized to ``0.0``; tuples are recursively
    converted to arrays. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    trend = quality_trend(paths)
    return _dump_quality_trend(trend)


def _check_quality_trend_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(_QUALITY_TREND_ITEM_KEYS):
        raise ValueError(
            prefix + "keys must be in the order index, coverage_delta, "
            "terrain_exceed_delta, unknown_delta, quality"
        )

    index = item["index"]
    if type(index) is not int:
        raise ValueError(prefix + "index must be a non-bool int")

    coverage_delta = item["coverage_delta"]
    if type(coverage_delta) is not float:
        raise ValueError(prefix + "coverage_delta must be a float")
    if not math.isfinite(coverage_delta):
        raise ValueError(prefix + "coverage_delta must be finite")
    if not -1.0 <= coverage_delta <= 1.0:
        raise ValueError(prefix + "coverage_delta must be in [-1, 1]")
    if coverage_delta != round(coverage_delta, 6):
        raise ValueError(
            prefix + "coverage_delta must have at most 6 decimals"
        )
    if coverage_delta == 0.0 and math.copysign(1.0, coverage_delta) < 0:
        raise ValueError(prefix + "coverage_delta must not be negative zero")

    for name in ("terrain_exceed_delta", "unknown_delta"):
        value = item[name]
        if type(value) is not int:
            raise ValueError(prefix + f"{name} must be a non-bool int")

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")


def _check_quality_trend(trend):
    if not isinstance(trend, dict):
        raise ValueError("quality trend must be a JSON object")
    if list(trend.keys()) != list(_QUALITY_TREND_KEYS):
        raise ValueError(
            "quality trend keys must be in the order changes, worst, quality"
        )

    changes = trend["changes"]
    if not isinstance(changes, list):
        raise ValueError("quality trend: changes must be a JSON array")
    if len(changes) == 0:
        raise ValueError("quality trend: changes must be non-empty")
    for i in range(len(changes)):
        prefix = f"quality trend: changes[{i}]: "
        item = changes[i]
        _check_quality_trend_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(
                prefix + "index must run consecutively from 1"
            )

    worst = trend["worst"]
    _check_quality_trend_item(worst, "quality trend: worst: ")
    if worst not in changes:
        raise ValueError(
            "quality trend: worst must equal one of the changes items"
        )

    quality = trend["quality"]
    if type(quality) is not str:
        raise ValueError("quality trend: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("quality trend: quality must be 'pass' or 'fail'")
    expected = (
        "pass"
        if all(item["quality"] == "pass" for item in changes)
        else "fail"
    )
    if quality != expected:
        raise ValueError(
            "quality trend: quality must be 'pass' exactly when every "
            "changes item is 'pass'"
        )


def load_quality_trend(path) -> dict:
    """Load a :func:`serialize_quality_trend`-produced JSON trend from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_quality_trend` for the same value: compact UTF-8
    JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``changes, worst, quality``. ``changes`` must be a non-empty
    JSON array whose items, like ``worst``, are objects with keys
    exactly in the order ``index, coverage_delta,
    terrain_exceed_delta, unknown_delta, quality``: ``index`` a
    non-bool int running consecutively from ``1``; ``coverage_delta``
    a finite non-bool float in ``[-1, 1]`` with at most six decimals
    and not negative zero; ``terrain_exceed_delta`` and
    ``unknown_delta`` non-bool ints; ``quality`` either ``"pass"`` or
    ``"fail"``. ``worst`` must equal one of the ``changes`` items and
    the top-level ``quality`` must be ``"pass"`` exactly when every
    ``changes`` item is ``"pass"``. Finally the file bytes must equal
    the canonical re-encoding of the decoded value byte for byte.
    Every key-order, type, range, relation, parse or canonical-byte
    mismatch raises ``ValueError``.

    Returns the trend as a dict with the keys in the order ``changes,
    worst, quality``, where ``changes`` is converted to a tuple and
    ``worst`` is the matching item of that tuple; the file is never
    modified.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "rb") as handle:
        data = handle.read()

    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("file must not start with a UTF-8 BOM")
    if data.endswith(b"\n"):
        raise ValueError("file must not end with a trailing newline")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        _check_quality_trend(parsed)
        canonical = _dump_quality_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid quality trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_quality_trend output"
        )

    changes = parsed["changes"]
    worst = parsed["worst"]
    matched = None
    for item in changes:
        if item == worst:
            matched = item
            break

    return {
        "changes": tuple(changes),
        "worst": matched,
        "quality": parsed["quality"],
    }


def _format_trend_value(value):
    if isinstance(value, float):
        return format(0.0 if value == 0 else value, ".6f")
    if isinstance(value, int):
        return str(value)
    return value


def render_quality_trend(path) -> str:
    """Render a :func:`load_quality_trend`-loaded JSON trend as two lines.

    :func:`load_quality_trend` is called exactly once with ``path``
    unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_quality_trend` therefore apply here
    verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``C =
    T["changes"]`` and ``W = T["worst"]``; returns two lines joined by
    ``"\\n"`` with no trailing newline::

        TREND=<len(C)>,<T["quality"]>;WORST=<i>,<c>,<t>,<u>,<q>
        CHANGES=<i>:<c>:<t>:<u>:<q>|...

    The WORST values and each CHANGES item are taken in the key order
    ``index, coverage_delta, terrain_exceed_delta, unknown_delta,
    quality`` (denoted ``i, c, t, u, q``); CHANGES items are joined by
    ``"|"`` in ``C`` order with no re-sorting. Values are copied
    directly from ``T``: ints are formatted in decimal, strings are
    copied as-is and floats use ``format(v, ".6f")`` with negative zero
    rendered as ``"0.000000"``.
    """
    trend = load_quality_trend(path)
    changes = trend["changes"]
    worst = trend["worst"]

    worst_fields = ",".join(
        _format_trend_value(worst[name]) for name in _QUALITY_TREND_ITEM_KEYS
    )
    first_line = (
        f"TREND={len(changes)},{_format_trend_value(trend['quality'])};"
        f"WORST={worst_fields}"
    )

    change_fields = "|".join(
        ":".join(
            _format_trend_value(item[name]) for name in _QUALITY_TREND_ITEM_KEYS
        )
        for item in changes
    )
    second_line = f"CHANGES={change_fields}"

    return "\n".join((first_line, second_line))
