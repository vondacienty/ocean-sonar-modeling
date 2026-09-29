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
from .crosspoint import _atomic_write_bytes, _reject_export_output_overlap
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
    "serialize_quality_trend_report",
    "load_quality_trend_report",
    "quality_report_trend",
    "serialize_quality_report_trend",
    "load_quality_report_trend",
    "render_quality_trend",
    "render_quality_trend_report",
    "render_quality_report_trend",
    "export_quality_trend",
    "export_quality_trend_report",
    "export_quality_report_trend",
    "quality_dashboard",
    "serialize_overview",
    "load_overview",
    "render_overview",
    "export_overview",
    "overview_trend",
    "serialize_overview_trend",
    "load_overview_trend",
    "render_overview_trend",
    "export_overview_trend",
    "export_overview_trend_report",
    "load_overview_trend_report",
    "render_overview_trend_report",
    "compare_overview_reports",
    "serialize_overview_comparison",
    "serialize_overview_comparison_report",
    "load_overview_comparison",
    "load_overview_comparison_report",
    "export_overview_comparison",
    "export_overview_comparison_report",
    "render_overview_comparison",
    "render_overview_comparison_report",
    "overview_comparison_report_trend",
    "serialize_overview_comparison_report_trend",
    "load_overview_comparison_report_trend",
    "export_overview_comparison_report_trend",
    "render_overview_comparison_report_trend",
    "trend_dashboard",
    "serialize_trend_dashboard",
    "load_trend_dashboard",
    "export_trend_dashboard",
    "dashboard_history",
    "serialize_dashboard_history",
    "load_dashboard_history",
    "export_dashboard_history",
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
_QUALITY_TREND_REPORT_KEYS = (
    "schema_version",
    "source",
    "summary",
    "worst",
    "quality",
)
_QUALITY_TREND_REPORT_SOURCE_KEYS = ("path", "kind")
_QUALITY_TREND_REPORT_SUMMARY_KEYS = ("count", "failed", "coverage_delta")
_QUALITY_REPORT_TREND_ITEM_KEYS = (
    "index",
    "failed_delta",
    "coverage_delta",
    "quality",
)
_OVERVIEW_KEYS = ("product", "substrate", "crosspoint", "summary", "quality")
_OVERVIEW_SUMMARY_KEYS = (
    "domain_count",
    "pass_count",
    "fail_count",
    "quality",
)
_DASHBOARD_KEYS = ("trend", "summary", "quality")
_DASHBOARD_SUMMARY_KEYS = ("count", "passed", "failed", "coverage_delta")
_OVERVIEW_TREND_KEYS = (
    "count",
    "changes",
    "regressed",
    "worst",
    "quality",
)
_OVERVIEW_TREND_ITEM_KEYS = (
    "index",
    "qualities",
    "regressions",
    "quality",
)
_OVERVIEW_TREND_REPORT_KEYS = (
    "schema_version",
    "source",
    "summary",
    "worst",
    "quality",
)
_OVERVIEW_TREND_REPORT_SOURCE_KEYS = ("path", "kind")
_OVERVIEW_TREND_REPORT_SUMMARY_KEYS = (
    "count",
    "changes",
    "regressed",
    "passed",
)
_OVERVIEW_COMPARISON_KEYS = ("changes", "worst", "quality")
_OVERVIEW_COMPARISON_ITEM_KEYS = (
    "index",
    "regressed_delta",
    "passed_delta",
    "quality",
)
_OVERVIEW_COMPARISON_REPORT_KEYS = (
    "schema_version",
    "source",
    "summary",
    "worst",
    "quality",
)
_OVERVIEW_COMPARISON_REPORT_SOURCE_KEYS = ("path", "kind")
_OVERVIEW_COMPARISON_REPORT_SUMMARY_KEYS = (
    "count",
    "failed",
    "regressed_delta",
    "passed_delta",
)
_OVERVIEW_COMPARISON_REPORT_TREND_KEYS = (
    "count",
    "changes",
    "regressed",
    "worst",
    "quality",
)
_OVERVIEW_COMPARISON_REPORT_TREND_ITEM_KEYS = (
    "index",
    "failed_delta",
    "regressed_delta",
    "passed_delta",
    "quality",
)
_TREND_DASHBOARD_KEYS = ("trend", "summary", "quality")
_TREND_DASHBOARD_SUMMARY_KEYS = (
    "reports",
    "passed",
    "regressed",
    "ratio",
    "worst",
)
_DASHBOARD_HISTORY_KEYS = ("count", "changes", "regressed", "worst", "quality")
_DASHBOARD_HISTORY_ITEM_KEYS = (
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
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


def serialize_quality_trend_report(path) -> bytes:
    """Serialize a report derived from a :func:`load_quality_trend` file.

    Exactly one call to :func:`load_quality_trend` is made with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_quality_trend` therefore apply here
    verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``C =
    T["changes"]`` and ``W = T["worst"]``. The report is computed from
    ``T`` alone, without modifying it, and encoded with keys exactly in
    the order ``schema_version, source, summary, worst, quality``:

    - ``schema_version``: the non-bool int ``1``.
    - ``source``: keys in the order ``path, kind``, with ``path`` the
      original ``path`` argument and ``kind`` the string
      ``"quality_trend"``.
    - ``summary``: keys in the order ``count, failed,
      coverage_delta`` — ``count`` is ``len(C)``, ``failed`` is the
      number of ``C`` items whose ``quality`` is ``"fail"`` and
      ``coverage_delta`` is ``round(math.fsum(c["coverage_delta"] for c
      in C) / len(C), 6)`` (negative zero is normalized only when
      written out).
    - ``worst``: an object with keys in the order ``index,
      coverage_delta, terrain_exceed_delta, unknown_delta, quality``,
      each value taken from ``W`` in that order.
    - ``quality``: ``T["quality"]``.

    ``count`` and ``failed`` are ``int``; every other value keeps the
    type it has in ``T``. Items are neither sorted nor copied with
    extra keys and the input is not modified. The JSON byte
    specification follows :func:`serialize_quality_trend`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; every float is rounded with ``round(float(v), 6)`` and
    negative zero is normalized to ``0.0`` only at write time; tuples
    are recursively converted to arrays. Any JSON or UTF-8 encoding
    failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    trend = load_quality_trend(path)
    changes = trend["changes"]
    worst = trend["worst"]

    count = len(changes)
    failed = 0
    for item in changes:
        if item["quality"] == "fail":
            failed += 1

    mean_delta = round(
        math.fsum(item["coverage_delta"] for item in changes) / count,
        6,
    )

    report = {
        "schema_version": 1,
        "source": {
            "path": path,
            "kind": "quality_trend",
        },
        "summary": {
            "count": count,
            "failed": failed,
            "coverage_delta": mean_delta,
        },
        "worst": {name: worst[name] for name in _QUALITY_TREND_ITEM_KEYS},
        "quality": trend["quality"],
    }

    return _dump_quality_trend(report)


def _check_trend_report_coverage_delta(value, prefix):
    if type(value) is not float:
        raise ValueError(prefix + "must be a float")
    if not math.isfinite(value):
        raise ValueError(prefix + "must be finite")
    if not -1.0 <= value <= 1.0:
        raise ValueError(prefix + "must be in [-1, 1]")
    if value != round(value, 6):
        raise ValueError(prefix + "must have at most 6 decimals")
    if value == 0.0 and math.copysign(1.0, value) < 0:
        raise ValueError(prefix + "must not be negative zero")


def _check_quality_trend_report(report):
    if not isinstance(report, dict):
        raise ValueError("quality trend report must be a JSON object")
    if list(report.keys()) != list(_QUALITY_TREND_REPORT_KEYS):
        raise ValueError(
            "quality trend report keys must be in the order "
            "schema_version, source, summary, worst, quality"
        )

    schema_version = report["schema_version"]
    if type(schema_version) is not int:
        raise ValueError(
            "quality trend report: schema_version must be a non-bool int"
        )
    if schema_version != 1:
        raise ValueError("quality trend report: schema_version must be 1")

    source = report["source"]
    if not isinstance(source, dict):
        raise ValueError(
            "quality trend report: source must be a JSON object"
        )
    if list(source.keys()) != list(_QUALITY_TREND_REPORT_SOURCE_KEYS):
        raise ValueError(
            "quality trend report: source keys must be in the order path, kind"
        )
    source_path = source["path"]
    if type(source_path) is not str:
        raise ValueError("quality trend report: source.path must be a str")
    if source_path == "":
        raise ValueError(
            "quality trend report: source.path must not be empty"
        )
    if source["kind"] != "quality_trend":
        raise ValueError(
            "quality trend report: source.kind must be 'quality_trend'"
        )

    summary = report["summary"]
    if not isinstance(summary, dict):
        raise ValueError(
            "quality trend report: summary must be a JSON object"
        )
    if list(summary.keys()) != list(_QUALITY_TREND_REPORT_SUMMARY_KEYS):
        raise ValueError(
            "quality trend report: summary keys must be in the order "
            "count, failed, coverage_delta"
        )

    count = summary["count"]
    if type(count) is not int:
        raise ValueError(
            "quality trend report: summary.count must be a non-bool int"
        )
    if not count > 0:
        raise ValueError("quality trend report: summary.count must be > 0")

    failed = summary["failed"]
    if type(failed) is not int:
        raise ValueError(
            "quality trend report: summary.failed must be a non-bool int"
        )
    if not 0 <= failed <= count:
        raise ValueError(
            "quality trend report: summary.failed must be in [0, count]"
        )

    _check_trend_report_coverage_delta(
        summary["coverage_delta"],
        "quality trend report: summary.coverage_delta ",
    )

    worst = report["worst"]
    _check_quality_trend_item(worst, "quality trend report: worst: ")
    if not 1 <= worst["index"] <= count:
        raise ValueError(
            "quality trend report: worst.index must be in [1, count]"
        )

    quality = report["quality"]
    if type(quality) is not str:
        raise ValueError("quality trend report: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "quality trend report: quality must be 'pass' or 'fail'"
        )
    expected = "pass" if failed == 0 else "fail"
    if quality != expected:
        raise ValueError(
            "quality trend report: quality must be 'pass' exactly when "
            "summary.failed is 0"
        )
    if quality == "pass" and worst["quality"] != "pass":
        raise ValueError(
            "quality trend report: worst.quality must be 'pass' when "
            "quality is 'pass'"
        )


def load_quality_trend_report(path) -> dict:
    """Load a :func:`serialize_quality_trend_report` JSON report from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_quality_trend_report` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``schema_version, source, summary, worst, quality``:
    ``schema_version`` is the non-bool int ``1``; ``source`` is an
    object with keys exactly in the order ``path, kind`` whose values
    are a non-empty ``str`` and the string ``"quality_trend"``;
    ``summary`` is an object with keys exactly in the order ``count,
    failed, coverage_delta`` where ``count`` and ``failed`` are
    non-bool ints with ``count > 0`` and ``0 <= failed <= count`` and
    ``coverage_delta`` is a finite non-bool float in ``[-1, 1]`` with
    at most six decimals and not negative zero; ``worst`` is an object
    with keys exactly in the order ``index, coverage_delta,
    terrain_exceed_delta, unknown_delta, quality`` where ``index`` is
    a non-bool int in ``[1, count]``, ``coverage_delta`` follows the
    same rule as the summary one, ``terrain_exceed_delta`` and
    ``unknown_delta`` are non-bool ints and ``quality`` is ``"pass"``
    or ``"fail"``; and the top-level ``quality`` is ``"pass"`` or
    ``"fail"``, ``"pass"`` exactly when ``failed`` is ``0``, in which
    case ``worst.quality`` must also be ``"pass"``. Finally the file
    bytes must equal the canonical re-encoding of the decoded value
    byte for byte. Every key-order, type, range, relation, parse or
    canonical-byte mismatch raises ``ValueError``.

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
        _check_quality_trend_report(parsed)
        canonical = _dump_quality_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid quality trend report: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_quality_trend_report output"
        )

    return parsed


def quality_report_trend(paths) -> dict:
    """Compare successive :func:`load_quality_trend_report` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_quality_trend_report` is then called exactly once per
    path, in input order; any exception it raises is propagated
    unchanged. The input and the loaded files are not modified.

    Every loaded report must have the same ``summary.count`` value as
    the first one; otherwise a ``ValueError`` is raised.

    For each successive pair ``i = 1..n-1`` the unrounded deltas are
    ``df = failed_i - failed_(i-1)`` and
    ``dc = coverage_delta_i - coverage_delta_(i-1)`` (both taken from
    the reports' ``summary``); a comparison fails (``q`` is ``"fail"``)
    when ``df > 0``, ``dc < 0`` or the report ``quality`` changes from
    ``"pass"`` to ``"fail"``, and is ``"pass"`` otherwise.

    Returns a dict with keys in the order ``changes, worst, quality``:
    ``changes`` is a tuple with one dict per pair (in ``i`` order), each
    with keys in the order ``index, failed_delta, coverage_delta,
    quality`` — ``index`` is the non-bool int ``i``, ``failed_delta``
    is the unrounded non-bool int ``df``, ``coverage_delta`` is
    ``round(float(dc), 6)`` (negative zero normalized to ``0.0``) and
    ``quality`` is ``q``. ``worst`` is the ``changes`` item minimizing
    the *unrounded* tuple ``(dc, -df, i)`` lexicographically (the same
    dict object, never a copy); ``quality`` is ``"pass"`` exactly when
    every ``q`` is ``"pass"`` and ``"fail"`` otherwise. Items are not
    sorted, values are not recomputed and no other keys are added.
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

    reports = [load_quality_trend_report(path) for path in paths]

    first_count = reports[0]["summary"]["count"]
    for i in range(1, len(reports)):
        count = reports[i]["summary"]["count"]
        if count != first_count:
            raise ValueError(
                f"quality trend report at paths[{i}] summary.count "
                f"{count} does not match {first_count}"
            )

    changes = []
    worst_item = None
    worst_key = None
    overall = "pass"
    for i in range(1, len(reports)):
        previous_summary = reports[i - 1]["summary"]
        current_summary = reports[i]["summary"]
        df = int(current_summary["failed"]) - int(previous_summary["failed"])
        dc = (
            current_summary["coverage_delta"]
            - previous_summary["coverage_delta"]
        )
        if (
            df > 0
            or dc < 0
            or (
                reports[i - 1]["quality"] == "pass"
                and reports[i]["quality"] == "fail"
            )
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
            "failed_delta": int(df),
            "coverage_delta": coverage_delta,
            "quality": verdict,
        }
        changes.append(item)

        key = (dc, -df, i)
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "changes": tuple(changes),
        "worst": worst_item,
        "quality": overall,
    }


def serialize_quality_report_trend(paths) -> bytes:
    """Serialize the :func:`quality_report_trend` comparison of ``paths`` to bytes.

    Exactly one call to :func:`quality_report_trend` is made with
    ``paths`` unchanged and no other work happens before it; the
    ``paths`` validation contract, the per-path
    :func:`load_quality_trend_report` behavior, every exception
    (propagated unchanged) and the input/file invariance of
    :func:`quality_report_trend` therefore apply here verbatim.
    Neither ``paths`` nor the loaded files are modified.

    Let ``T`` be the dict returned by that single
    :func:`quality_report_trend` call. It is encoded with keys exactly
    in the order ``changes, worst, quality``; the ``changes`` tuple is
    converted to a JSON array and each item, like ``worst``, keeps its
    key order ``index, failed_delta, coverage_delta, quality``. Values
    are not recomputed and no keys are added or removed.

    The JSON byte specification follows
    :func:`serialize_quality_trend`: UTF-8, ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline; floats are rounded with
    ``round(float(v), 6)`` and negative zero is normalized to ``0.0``;
    tuples are recursively converted to arrays. Any JSON or UTF-8
    encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    trend = quality_report_trend(paths)
    return _dump_quality_trend(trend)


def _check_quality_report_trend_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(_QUALITY_REPORT_TREND_ITEM_KEYS):
        raise ValueError(
            prefix + "keys must be in the order index, failed_delta, "
            "coverage_delta, quality"
        )

    index = item["index"]
    if type(index) is not int:
        raise ValueError(prefix + "index must be a non-bool int")

    failed_delta = item["failed_delta"]
    if type(failed_delta) is not int:
        raise ValueError(prefix + "failed_delta must be a non-bool int")

    coverage_delta = item["coverage_delta"]
    if type(coverage_delta) is not float:
        raise ValueError(prefix + "coverage_delta must be a float")
    if not math.isfinite(coverage_delta):
        raise ValueError(prefix + "coverage_delta must be finite")
    if not -2.0 <= coverage_delta <= 2.0:
        raise ValueError(prefix + "coverage_delta must be in [-2, 2]")
    if coverage_delta != round(coverage_delta, 6):
        raise ValueError(
            prefix + "coverage_delta must have at most 6 decimals"
        )
    if coverage_delta == 0.0 and math.copysign(1.0, coverage_delta) < 0:
        raise ValueError(prefix + "coverage_delta must not be negative zero")

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")


def _check_quality_report_trend(trend):
    if not isinstance(trend, dict):
        raise ValueError("quality report trend must be a JSON object")
    if list(trend.keys()) != list(_QUALITY_TREND_KEYS):
        raise ValueError(
            "quality report trend keys must be in the order "
            "changes, worst, quality"
        )

    changes = trend["changes"]
    if not isinstance(changes, list):
        raise ValueError("quality report trend: changes must be a JSON array")
    if len(changes) == 0:
        raise ValueError("quality report trend: changes must be non-empty")
    for i in range(len(changes)):
        prefix = f"quality report trend: changes[{i}]: "
        item = changes[i]
        _check_quality_report_trend_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(
                prefix + "index must run consecutively from 1"
            )

    worst = trend["worst"]
    _check_quality_report_trend_item(worst, "quality report trend: worst: ")
    if worst not in changes:
        raise ValueError(
            "quality report trend: worst must equal one of the changes items"
        )

    quality = trend["quality"]
    if type(quality) is not str:
        raise ValueError("quality report trend: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "quality report trend: quality must be 'pass' or 'fail'"
        )
    expected = (
        "pass"
        if all(item["quality"] == "pass" for item in changes)
        else "fail"
    )
    if quality != expected:
        raise ValueError(
            "quality report trend: quality must be 'pass' exactly when "
            "every changes item is 'pass'"
        )


def load_quality_report_trend(path) -> dict:
    """Load a :func:`serialize_quality_report_trend`-produced JSON trend from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_quality_report_trend` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``changes, worst, quality``. ``changes`` must be a non-empty
    JSON array whose items, like ``worst``, are objects with keys
    exactly in the order ``index, failed_delta, coverage_delta,
    quality``: ``index`` a non-bool int running consecutively from
    ``1``; ``failed_delta`` a non-bool int; ``coverage_delta`` a finite
    non-bool float in ``[-2, 2]`` with at most six decimals and not
    negative zero; ``quality`` either ``"pass"`` or ``"fail"``.
    ``worst`` must equal one of the ``changes`` items and the
    top-level ``quality`` must be ``"pass"`` exactly when every
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
        _check_quality_report_trend(parsed)
        canonical = _dump_quality_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid quality report trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_quality_report_trend output"
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


def render_quality_trend_report(path) -> str:
    """Render a :func:`load_quality_trend_report`-loaded JSON report as three lines.

    :func:`load_quality_trend_report` is called exactly once with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_quality_trend_report` therefore
    apply here verbatim. The file is not modified.

    Let ``R`` be the dict returned by that single call; returns three
    lines joined by ``"\\n"`` with no trailing newline::

        REPORT=<schema_version>,<JSON path>,<kind>,<quality>
        SUMMARY=<count>,<failed>,<coverage_delta>
        WORST=<index>,<coverage_delta>,<terrain_exceed_delta>,<unknown_delta>,<quality>

    The REPORT values are ``R["schema_version"]``, the compact
    ``ensure_ascii=False`` JSON string of ``R["source"]["path"]``,
    ``R["source"]["kind"]`` and ``R["quality"]``; the SUMMARY values
    are the ``count``, ``failed`` and ``coverage_delta`` of
    ``R["summary"]``; the WORST values are the fields of
    ``R["worst"]`` in the key order ``index, coverage_delta,
    terrain_exceed_delta, unknown_delta, quality``. Values are copied
    directly from ``R``: ints are formatted in decimal, strings are
    copied as-is and floats use ``format(v, ".6f")`` with negative
    zero rendered as ``"0.000000"``.
    """
    report = load_quality_trend_report(path)
    source = report["source"]
    summary = report["summary"]
    worst = report["worst"]

    source_path = json.dumps(
        source["path"], ensure_ascii=False, separators=(",", ":")
    )
    first_line = (
        f"REPORT={_format_trend_value(report['schema_version'])},"
        f"{source_path},"
        f"{_format_trend_value(source['kind'])},"
        f"{_format_trend_value(report['quality'])}"
    )
    second_line = (
        f"SUMMARY={_format_trend_value(summary['count'])},"
        f"{_format_trend_value(summary['failed'])},"
        f"{_format_trend_value(summary['coverage_delta'])}"
    )
    third_line = "WORST=" + ",".join(
        _format_trend_value(worst[name]) for name in _QUALITY_TREND_ITEM_KEYS
    )

    return "\n".join((first_line, second_line, third_line))


def export_quality_trend(paths, output) -> bytes:
    """Serialize the :func:`quality_trend` comparison of ``paths`` and write it.

    Exactly one call to :func:`serialize_quality_trend` is made with
    ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``changes, worst,
    quality`` and JSON byte specification all apply here as well; in
    particular a bad ``paths`` value is reported before ``output`` is
    inspected. Neither ``paths`` nor the loaded files are modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_quality_trend`, ``output`` is then validated: it
    must be a non-empty ``str`` (a non-str raises ``TypeError`` and an
    empty ``str`` raises ``ValueError``), in that order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_quality_trend(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data


def export_quality_trend_report(path, output) -> bytes:
    """Serialize a quality trend report for ``path`` and write it.

    Exactly one call to :func:`serialize_quality_trend_report` is made
    with ``path`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    read behavior, report key order ``schema_version, source, summary,
    worst, quality`` and JSON byte specification all apply here as
    well; in particular a bad ``path`` value is reported before
    ``output`` is inspected. The input file is not modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_quality_trend_report`, ``output`` is then
    validated: it must be a non-empty ``str`` (a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``), in that
    order.

    ``output`` must not name the same file as ``path``: when both
    sides exist they are compared with ``os.path.samefile`` so soft and
    hard links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_quality_trend_report(path)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, [path])
    _atomic_write_bytes(output, data)
    return data


def render_quality_report_trend(path) -> str:
    """Render a :func:`load_quality_report_trend`-loaded JSON trend as text.

    :func:`load_quality_report_trend` is called exactly once with
    ``path`` unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_quality_report_trend` therefore apply
    here verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call and ``C =
    T["changes"]``; returns one line per change plus a leading summary
    line, joined by ``"\\n"`` with no trailing newline. The first line
    is::

        QUALITY=<T["quality"]>;COUNT=<len(C)>;WORST_INDEX=<T["worst"]["index"]>

    followed by, for every item of ``C`` in its original order, a line::

        CHANGE[<index>]=<failed_delta>,<coverage_delta>,<quality>

    where the three values are taken in the item's key order ``index,
    failed_delta, coverage_delta, quality`` with no re-sorting. Values
    are copied directly from ``T``: ints are formatted in decimal,
    strings are copied as-is and floats use ``format(v, ".6f")`` with
    negative zero rendered as ``"0.000000"``.
    """
    trend = load_quality_report_trend(path)
    changes = trend["changes"]

    lines = [
        f"QUALITY={_format_trend_value(trend['quality'])};"
        f"COUNT={len(changes)};"
        f"WORST_INDEX={_format_trend_value(trend['worst']['index'])}"
    ]
    for item in changes:
        lines.append(
            f"CHANGE[{_format_trend_value(item['index'])}]="
            f"{_format_trend_value(item['failed_delta'])},"
            f"{_format_trend_value(item['coverage_delta'])},"
            f"{_format_trend_value(item['quality'])}"
        )

    return "\n".join(lines)


def quality_dashboard(path) -> dict:
    """Summarize a :func:`load_quality_report_trend`-loaded JSON trend.

    :func:`load_quality_report_trend` is called exactly once with
    ``path`` unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_quality_report_trend` therefore apply
    here verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``C =
    T["changes"]``, ``n = len(C)``, ``p`` the number of ``C`` items
    whose ``quality`` is ``"pass"`` and ``c =
    round(float(math.fsum(item["coverage_delta"] for item in C) / n),
    6)`` with negative zero normalized to ``0.0``.

    Returns a dict with keys in the order ``trend, summary, quality``:
    ``trend`` is the ``T`` object itself (identity preserved, not
    modified); ``summary`` is a dict with keys in the order ``count,
    passed, failed, coverage_delta`` and values ``n``, ``p``, ``n - p``
    and ``c``; ``quality`` is ``T["quality"]``. ``count``, ``passed``
    and ``failed`` are ``int`` and ``coverage_delta`` is a ``float``.
    ``worst`` is not recomputed and no other keys are added.
    """
    trend = load_quality_report_trend(path)
    changes = trend["changes"]

    count = len(changes)
    passed = 0
    for item in changes:
        if item["quality"] == "pass":
            passed += 1

    coverage_delta = round(
        float(math.fsum(item["coverage_delta"] for item in changes) / count),
        6,
    )
    if coverage_delta == 0:
        coverage_delta = 0.0

    return {
        "trend": trend,
        "summary": {
            "count": count,
            "passed": passed,
            "failed": count - passed,
            "coverage_delta": coverage_delta,
        },
        "quality": trend["quality"],
    }


def serialize_overview(product_path, substrate_path, audit_path) -> bytes:
    """Serialize a combined three-domain quality overview to JSON bytes.

    The three domain loaders run strictly in this order, each exactly
    once and with no interleaving, and every exception from any of them
    short-circuits and is propagated unchanged:

    1. :func:`quality_dashboard` is called with ``product_path``.
    2. :func:`substrate.load_aggregate_report_trend
       <ocean_sonar.substrate.load_aggregate_report_trend>` is called
       with ``substrate_path``.
    3. :func:`crosspoint.load_audit_report_trend
       <ocean_sonar.crosspoint.load_audit_report_trend>` is called with
       ``audit_path``.

    No file is pre-read or reloaded; the validation, first-error order,
    exceptions and file invariance of the three loaders therefore apply
    here verbatim. None of the input files is modified.

    Let ``P``, ``S`` and ``C`` be the dicts returned by those three
    calls. The domain qualities are ``P["quality"]``,
    ``S["quality"]`` and ``C["trend"]["quality"]``. The
    overview is encoded with keys exactly in the order ``product,
    substrate, crosspoint, summary, quality``: the first three values
    are ``P``, ``S`` and ``C`` themselves, with every nested key order
    and value unchanged; ``summary`` has keys exactly in the order
    ``domain_count, pass_count, fail_count, quality`` with values the
    int ``3``, the number of domains whose quality is ``"pass"``, the
    number of remaining domains and ``"pass"`` only when all three
    domains pass (``"fail"`` otherwise); and the top-level ``quality``
    equals the ``summary`` quality. ``domain_count``, ``pass_count``
    and ``fail_count`` are non-bool ints. Neither ``P``, ``S`` nor
    ``C`` is modified and no domain statistic is recomputed.

    The JSON byte specification follows :func:`serialize`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; floats are rounded with ``round(float(v), 6)`` and
    negative zero is normalized to ``0.0``; tuples are recursively
    converted to arrays. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    product_result = quality_dashboard(product_path)
    substrate_result = substrate.load_aggregate_report_trend(substrate_path)
    crosspoint_result = crosspoint.load_audit_report_trend(audit_path)

    domain_qualities = (
        product_result["quality"],
        substrate_result["quality"],
        crosspoint_result["trend"]["quality"],
    )
    pass_count = 0
    for domain_quality in domain_qualities:
        if domain_quality == "pass":
            pass_count += 1
    fail_count = 3 - pass_count
    quality = "pass" if pass_count == 3 else "fail"

    overview = {
        "product": product_result,
        "substrate": substrate_result,
        "crosspoint": crosspoint_result,
        "summary": {
            "domain_count": 3,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "quality": quality,
        },
        "quality": quality,
    }

    return _dump_overview(overview)


def _dump_overview(overview) -> bytes:
    """Re-encode a validated overview dict like :func:`serialize_overview`."""
    try:
        text = json.dumps(
            _to_jsonable(overview),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"overview: could not be serialized to JSON: {exc}"
        ) from exc


def _check_overview_domain_float(value, prefix, low=-2.0, high=2.0):
    if type(value) is not float:
        raise ValueError(prefix + "must be a float")
    if not math.isfinite(value):
        raise ValueError(prefix + "must be finite")
    if not low <= value <= high:
        raise ValueError(prefix + f"must be in [{int(low)}, {int(high)}]")
    if value != round(float(value), 6):
        raise ValueError(prefix + "must have at most 6 decimals")
    if value == 0.0 and math.copysign(1.0, value) < 0:
        raise ValueError(prefix + "must not be negative zero")


def _check_overview_dashboard_summary(summary, count, changes):
    prefix = "overview: product.summary: "
    if not isinstance(summary, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(summary.keys()) != list(_DASHBOARD_SUMMARY_KEYS):
        raise ValueError(
            prefix + "keys must be in the order count, passed, failed, "
            "coverage_delta"
        )

    summary_count = summary["count"]
    if type(summary_count) is not int:
        raise ValueError(prefix + "count must be a non-bool int")
    if summary_count != count:
        raise ValueError(prefix + "count must match the number of changes")

    passed = summary["passed"]
    if type(passed) is not int:
        raise ValueError(prefix + "passed must be a non-bool int")
    expected_passed = 0
    for item in changes:
        if item["quality"] == "pass":
            expected_passed += 1
    if not 0 <= passed <= count:
        raise ValueError(prefix + "passed must be in [0, count]")
    if passed != expected_passed:
        raise ValueError(prefix + "passed must equal the number of pass items")

    failed = summary["failed"]
    if type(failed) is not int:
        raise ValueError(prefix + "failed must be a non-bool int")
    if failed != count - passed:
        raise ValueError(prefix + "failed must equal count - passed")

    coverage_delta = summary["coverage_delta"]
    _check_overview_domain_float(coverage_delta, prefix + "coverage_delta ")
    expected_coverage = round(
        float(math.fsum(item["coverage_delta"] for item in changes) / count),
        6,
    )
    if expected_coverage == 0:
        expected_coverage = 0.0
    if coverage_delta != expected_coverage:
        raise ValueError(
            prefix
            + "coverage_delta must equal round(float(fsum(item "
            "coverage_delta) / count), 6)"
        )


def _check_overview_product(product):
    """Validate the product section and return its normalized dict."""
    prefix = "overview: product: "
    if not isinstance(product, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(product.keys()) != list(_DASHBOARD_KEYS):
        raise ValueError(
            prefix + "keys must be in the order trend, summary, quality"
        )

    trend = product["trend"]
    _check_quality_report_trend(trend)

    changes = trend["changes"]
    worst = trend["worst"]
    matched = None
    for item in changes:
        if item == worst:
            matched = item
            break
    normalized_trend = {
        "changes": tuple(changes),
        "worst": matched,
        "quality": trend["quality"],
    }

    count = len(changes)
    _check_overview_dashboard_summary(product["summary"], count, changes)
    source_summary = product["summary"]
    normalized_summary = {
        "count": int(source_summary["count"]),
        "passed": int(source_summary["passed"]),
        "failed": int(source_summary["failed"]),
        "coverage_delta": source_summary["coverage_delta"],
    }

    quality = product["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    if quality != normalized_trend["quality"]:
        raise ValueError(prefix + "quality must equal trend.quality")

    return {
        "trend": normalized_trend,
        "summary": normalized_summary,
        "quality": quality,
    }


def _check_overview(parsed):
    """Validate a decoded overview and return its normalized dict."""
    if not isinstance(parsed, dict):
        raise ValueError("overview must be a JSON object")
    if list(parsed.keys()) != list(_OVERVIEW_KEYS):
        raise ValueError(
            "overview keys must be in the order product, substrate, "
            "crosspoint, summary, quality"
        )

    product_result = _check_overview_product(parsed["product"])
    substrate_result = substrate._check_aggregate_report_trend(
        parsed["substrate"]
    )
    crosspoint_result = crosspoint._check_audit_report_trend(
        parsed["crosspoint"]
    )

    summary = parsed["summary"]
    prefix = "overview: summary: "
    if not isinstance(summary, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(summary.keys()) != list(_OVERVIEW_SUMMARY_KEYS):
        raise ValueError(
            prefix + "keys must be in the order domain_count, pass_count, "
            "fail_count, quality"
        )

    domain_count = summary["domain_count"]
    if type(domain_count) is not int:
        raise ValueError(prefix + "domain_count must be a non-bool int")
    if domain_count != 3:
        raise ValueError(prefix + "domain_count must be 3")

    pass_count = summary["pass_count"]
    if type(pass_count) is not int:
        raise ValueError(prefix + "pass_count must be a non-bool int")
    if not 0 <= pass_count <= 3:
        raise ValueError(prefix + "pass_count must be in [0, 3]")

    fail_count = summary["fail_count"]
    if type(fail_count) is not int:
        raise ValueError(prefix + "fail_count must be a non-bool int")
    if fail_count != 3 - pass_count:
        raise ValueError(prefix + "fail_count must equal 3 - pass_count")

    domain_qualities = (
        product_result["quality"],
        substrate_result["quality"],
        crosspoint_result["trend"]["quality"],
    )
    expected_pass_count = 0
    for domain_quality in domain_qualities:
        if domain_quality == "pass":
            expected_pass_count += 1
    if pass_count != expected_pass_count:
        raise ValueError(
            prefix + "pass_count must equal the number of passing domains"
        )

    summary_quality = summary["quality"]
    if type(summary_quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if summary_quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    expected_quality = "pass" if pass_count == 3 else "fail"
    if summary_quality != expected_quality:
        raise ValueError(
            prefix
            + "quality must be 'pass' exactly when all three domains pass"
        )

    quality = parsed["quality"]
    if type(quality) is not str:
        raise ValueError("overview: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("overview: quality must be 'pass' or 'fail'")
    if quality != summary_quality:
        raise ValueError(
            "overview: quality must equal summary.quality"
        )

    return {
        "product": product_result,
        "substrate": substrate_result,
        "crosspoint": crosspoint_result,
        "summary": {
            "domain_count": int(domain_count),
            "pass_count": int(pass_count),
            "fail_count": int(fail_count),
            "quality": summary_quality,
        },
        "quality": quality,
    }


def load_overview(path) -> dict:
    """Load a :func:`serialize_overview`-produced JSON overview from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by :func:`serialize_overview`
    for the same value: compact UTF-8 JSON with no BOM and no trailing
    newline. A BOM, a trailing newline, a UTF-8 decoding failure, a JSON
    parsing failure, a ``NaN``/``Infinity`` constant or a repeated JSON
    object key raises ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``product, substrate, crosspoint, summary, quality``. The
    ``product`` value must satisfy the full :func:`quality_dashboard`
    return contract — keys ``trend, summary, quality`` with the ``trend``
    satisfying the :func:`load_quality_report_trend` contract (a
    non-empty ``changes`` array of items with keys ``index, failed_delta,
    coverage_delta, quality``, a ``worst`` equal to one of them, and the
    top-level trend quality), the ``summary`` fields consistent with
    those changes (``count`` their number, ``passed`` the number of pass
    items, ``failed`` their complement and ``coverage_delta`` the
    six-decimal mean of the item deltas with negative zero forbidden) and
    ``quality`` equal to the trend quality. The ``substrate`` value must
    satisfy the full
    :func:`ocean_sonar.substrate.load_aggregate_report_trend` return
    contract and the ``crosspoint`` value the full
    :func:`ocean_sonar.crosspoint.load_audit_report_trend` return
    contract (its structural type, range and relation rules; the
    referenced source files are not re-read). ``summary`` must have keys
    exactly in the order ``domain_count, pass_count, fail_count,
    quality``: the first three non-bool ints with ``domain_count`` equal
    to ``3``, ``pass_count`` the number of passing domains and
    ``fail_count`` equal to ``3 - pass_count``; its ``quality`` (and the
    top-level ``quality``, which must equal it) is ``"pass"`` exactly
    when all three domains pass and ``"fail"`` otherwise. Finally the
    file bytes must equal the canonical :func:`serialize_overview`
    re-encoding of the decoded value byte for byte. Every key-order,
    type, range, relation, parse or canonical-byte mismatch raises
    ``ValueError``.

    JSON arrays are restored following the embedded loader contracts:
    the product ``changes`` array becomes a tuple whose ``worst`` is the
    matching tuple item, the substrate ``worst`` becomes a tuple, the
    crosspoint ``sources`` stays a list and only its ``trend.worst``
    becomes a tuple.

    Returns the overview as a dict with the keys in the order above; the
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
        overview = _check_overview(parsed)
        canonical = _dump_overview(overview)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid overview: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize_overview output"
        )

    return overview


def render_overview(path) -> str:
    """Render a :func:`load_overview`-loaded JSON overview as four text lines.

    :func:`load_overview` is called exactly once with ``path``
    unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview` therefore apply here
    verbatim. The file is not modified.

    Let ``O`` be the dict returned by that single call, ``P =
    O["product"]``, ``S = O["substrate"]``, ``C = O["crosspoint"]
    ["trend"]`` and ``M = O["summary"]``; returns four lines joined by
    ``"\\n"`` with no trailing newline::

        OVERVIEW=<O["quality"]>,<M["domain_count"]>,<M["pass_count"]>,<M["fail_count"]>
        PRODUCT=<P["quality"]>,<P["summary"]["count"]>,<P["summary"]["passed"]>,<P["summary"]["failed"]>,<P["summary"]["coverage_delta"]>
        SUBSTRATE=<S["quality"]>,<S["count"]>,<S["changes"]>,<S["regressed"]>,<S["unknown_delta"]>,<S["unknown_ratio_delta"]>
        CROSSPOINT=<C["quality"]>,<C["count"]>,<C["changes"]>,<C["regressed"]>,<C["failed_delta"]>,<C["pass_ratio_delta"]>

    Values are taken directly in the stated key order with no
    recomputation or re-sorting: ints are formatted in decimal, strings
    are copied as-is and floats use ``format(v, ".6f")`` with negative
    zero rendered as ``"0.000000"``, following
    :func:`render_quality_report_trend`.
    """
    overview = load_overview(path)
    product = overview["product"]
    substrate = overview["substrate"]
    crosspoint_trend = overview["crosspoint"]["trend"]
    summary = overview["summary"]
    product_summary = product["summary"]

    lines = (
        "OVERVIEW={},{},{},{}".format(
            _format_trend_value(overview["quality"]),
            _format_trend_value(summary["domain_count"]),
            _format_trend_value(summary["pass_count"]),
            _format_trend_value(summary["fail_count"]),
        ),
        "PRODUCT={},{},{},{},{}".format(
            _format_trend_value(product["quality"]),
            _format_trend_value(product_summary["count"]),
            _format_trend_value(product_summary["passed"]),
            _format_trend_value(product_summary["failed"]),
            _format_trend_value(product_summary["coverage_delta"]),
        ),
        "SUBSTRATE={},{},{},{},{},{}".format(
            _format_trend_value(substrate["quality"]),
            _format_trend_value(substrate["count"]),
            _format_trend_value(substrate["changes"]),
            _format_trend_value(substrate["regressed"]),
            _format_trend_value(substrate["unknown_delta"]),
            _format_trend_value(substrate["unknown_ratio_delta"]),
        ),
        "CROSSPOINT={},{},{},{},{},{}".format(
            _format_trend_value(crosspoint_trend["quality"]),
            _format_trend_value(crosspoint_trend["count"]),
            _format_trend_value(crosspoint_trend["changes"]),
            _format_trend_value(crosspoint_trend["regressed"]),
            _format_trend_value(crosspoint_trend["failed_delta"]),
            _format_trend_value(crosspoint_trend["pass_ratio_delta"]),
        ),
    )

    return "\n".join(lines)


def export_overview(product_path, substrate_path, crosspoint_path, output) -> bytes:
    """Serialize the combined three-domain overview and write it.

    Exactly one call to :func:`serialize_overview` is made with
    ``product_path``, ``substrate_path`` and ``crosspoint_path`` —
    before any other work and no second time — so its loader order,
    validation, first-error order, exceptions (propagated unchanged),
    file invariance, overview key order ``product, substrate,
    crosspoint, summary, quality`` and JSON byte specification all
    apply here as well; in particular a bad input path is reported
    before ``output`` is inspected. None of the three input files is
    modified.

    With ``B`` the ``bytes`` returned by :func:`serialize_overview`,
    ``output`` is then validated: it must be a non-empty ``str`` (a
    non-str raises ``TypeError`` and an empty ``str`` raises
    ``ValueError``), in that order.

    ``output`` must not name the same file as any of the three input
    paths: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_overview(
        product_path, substrate_path, crosspoint_path
    )

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(
        output, [product_path, substrate_path, crosspoint_path]
    )
    _atomic_write_bytes(output, data)
    return data


def overview_trend(paths) -> dict:
    """Compare successive :func:`load_overview` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_overview` is then called exactly once per path, in
    input order; any exception it raises is propagated unchanged. The input
    and the loaded files are not modified.

    For each successive pair ``i = 1..n-1`` the four domain qualities
    of each snapshot are compared in the order ``product.quality``,
    ``substrate.quality``, ``crosspoint.trend.quality`` and the
    top-level ``quality``; only a change from ``"pass"`` to ``"fail"``
    counts as a regression.

    Returns a dict with keys in the order ``count, changes, regressed,
    worst, quality``: ``count`` is the non-bool int ``n`` (the number
    of snapshots); ``changes`` is a tuple with one dict per pair (in
    ``i`` order), each with keys in the order ``index, qualities,
    regressions, quality`` — ``index`` is the non-bool int ``i``,
    ``qualities`` is the tuple of the later snapshot's four quality
    strings in the order above, ``regressions`` is the same-order tuple
    of four ``bool`` flags (``True`` exactly where the quality changed
    from ``"pass"`` to ``"fail"``) and ``quality`` is ``"fail"`` when
    any regression flag is ``True`` and ``"pass"`` otherwise.
    ``regressed`` is the number of ``changes`` items whose ``quality``
    is ``"fail"``. ``worst`` is the ``changes`` item with the most
    regression flags (the same dict object, never a copy), ties broken
    by the smaller ``index``; the top-level ``quality`` is ``"pass"``
    exactly when ``regressed`` is ``0`` and ``"fail"`` otherwise. Items
    are not sorted, values are not recomputed and no other keys are
    added.
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

    overviews = [load_overview(path) for path in paths]

    changes = []
    regressed = 0
    worst_item = None
    worst_count = -1
    for i in range(1, len(overviews)):
        previous = overviews[i - 1]
        current = overviews[i]
        previous_qualities = (
            previous["product"]["quality"],
            previous["substrate"]["quality"],
            previous["crosspoint"]["trend"]["quality"],
            previous["quality"],
        )
        qualities = (
            current["product"]["quality"],
            current["substrate"]["quality"],
            current["crosspoint"]["trend"]["quality"],
            current["quality"],
        )
        regressions = tuple(
            previous_qualities[j] == "pass" and qualities[j] == "fail"
            for j in range(4)
        )
        regression_count = 0
        for flag in regressions:
            if flag:
                regression_count += 1
        if regression_count > 0:
            verdict = "fail"
            regressed += 1
        else:
            verdict = "pass"

        item = {
            "index": int(i),
            "qualities": qualities,
            "regressions": regressions,
            "quality": verdict,
        }
        changes.append(item)

        if regression_count > worst_count:
            worst_count = regression_count
            worst_item = item

    return {
        "count": len(paths),
        "changes": tuple(changes),
        "regressed": regressed,
        "worst": worst_item,
        "quality": "pass" if regressed == 0 else "fail",
    }


def _dump_overview_trend(trend) -> bytes:
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
            f"overview trend: could not be serialized to JSON: {exc}"
        ) from exc


def serialize_overview_trend(paths) -> bytes:
    """Serialize the :func:`overview_trend` comparison of ``paths`` to bytes.

    Exactly one call to :func:`overview_trend` is made with ``paths``
    unchanged and no other work happens before it; the ``paths``
    validation contract, the per-path :func:`load_overview` behavior,
    every exception (propagated unchanged) and the input/file
    invariance of :func:`overview_trend` therefore apply here verbatim.
    Neither ``paths`` nor the loaded files are modified.

    Let ``T`` be the dict returned by that single :func:`overview_trend`
    call. It is encoded with keys exactly in the order ``count,
    changes, regressed, worst, quality``; the ``changes`` tuple and the
    per-item ``qualities`` and ``regressions`` tuples are converted to
    JSON arrays and each item keeps its key order ``index, qualities,
    regressions, quality``.

    The JSON byte specification follows :func:`serialize_overview`:
    UTF-8, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; tuples are recursively converted to arrays. Any JSON or
    UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    trend = overview_trend(paths)
    return _dump_overview_trend(trend)


def _check_overview_trend_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(_OVERVIEW_TREND_ITEM_KEYS):
        raise ValueError(
            prefix + "keys must be in the order index, qualities, "
            "regressions, quality"
        )

    index = item["index"]
    if type(index) is not int:
        raise ValueError(prefix + "index must be a non-bool int")

    qualities = item["qualities"]
    if not isinstance(qualities, list):
        raise ValueError(prefix + "qualities must be a JSON array")
    if len(qualities) != 4:
        raise ValueError(prefix + "qualities must have 4 elements")
    for j in range(4):
        value = qualities[j]
        if type(value) is not str:
            raise ValueError(prefix + f"qualities[{j}] must be a str")
        if value not in _QUALITY_VALUES:
            raise ValueError(
                prefix + f"qualities[{j}] must be 'pass' or 'fail'"
            )

    regressions = item["regressions"]
    if not isinstance(regressions, list):
        raise ValueError(prefix + "regressions must be a JSON array")
    if len(regressions) != 4:
        raise ValueError(prefix + "regressions must have 4 elements")
    any_regression = False
    for j in range(4):
        value = regressions[j]
        if not isinstance(value, bool):
            raise ValueError(prefix + f"regressions[{j}] must be a bool")
        if value:
            any_regression = True

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    expected_quality = "fail" if any_regression else "pass"
    if quality != expected_quality:
        raise ValueError(
            prefix
            + "quality must be 'fail' when any regression flag is true "
            "and 'pass' otherwise"
        )


def _check_overview_trend(trend):
    if not isinstance(trend, dict):
        raise ValueError("overview trend must be a JSON object")
    if list(trend.keys()) != list(_OVERVIEW_TREND_KEYS):
        raise ValueError(
            "overview trend keys must be in the order count, changes, "
            "regressed, worst, quality"
        )

    count = trend["count"]
    if type(count) is not int:
        raise ValueError("overview trend: count must be a non-bool int")
    if not count >= 2:
        raise ValueError("overview trend: count must be >= 2")

    changes = trend["changes"]
    if not isinstance(changes, list):
        raise ValueError("overview trend: changes must be a JSON array")
    if len(changes) != count - 1:
        raise ValueError(
            "overview trend: changes must have count - 1 elements"
        )

    regressed_count = 0
    worst_item = None
    worst_count = -1
    for i in range(len(changes)):
        prefix = f"overview trend: changes[{i}]: "
        item = changes[i]
        _check_overview_trend_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(prefix + "index must run consecutively from 1")
        if item["quality"] == "fail":
            regressed_count += 1
        regression_count = 0
        for flag in item["regressions"]:
            if flag:
                regression_count += 1
        if regression_count > worst_count:
            worst_count = regression_count
            worst_item = item

    regressed = trend["regressed"]
    if type(regressed) is not int:
        raise ValueError("overview trend: regressed must be a non-bool int")
    if regressed != regressed_count:
        raise ValueError(
            "overview trend: regressed must equal the number of fail items"
        )

    worst = trend["worst"]
    _check_overview_trend_item(worst, "overview trend: worst: ")
    expected_worst_index = worst_item["index"]
    if worst["index"] != expected_worst_index or worst != worst_item:
        raise ValueError(
            "overview trend: worst must be the item with the most "
            "regression flags, ties broken by the smallest index"
        )

    quality = trend["quality"]
    if type(quality) is not str:
        raise ValueError("overview trend: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("overview trend: quality must be 'pass' or 'fail'")
    expected_quality = "pass" if regressed == 0 else "fail"
    if quality != expected_quality:
        raise ValueError(
            "overview trend: quality must be 'pass' exactly when "
            "regressed is 0"
        )


def load_overview_trend(path) -> dict:
    """Load a :func:`serialize_overview_trend`-produced JSON trend from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_overview_trend` for the same value: compact UTF-8
    JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``count, changes, regressed, worst, quality``. ``count`` must
    be a non-bool int ``>= 2`` and ``changes`` a JSON array of exactly
    ``count - 1`` items. Each item, like ``worst``, must be an object
    with keys exactly in the order ``index, qualities, regressions,
    quality``: ``index`` a non-bool int running consecutively from
    ``1``; ``qualities`` an array of exactly four ``"pass"``/``"fail"``
    strings; ``regressions`` an array of exactly four ``bool`` flags;
    and the item ``quality`` must be ``"fail"`` when any regression
    flag is ``True`` and ``"pass"`` otherwise. ``regressed`` must equal
    the number of ``changes`` items whose ``quality`` is ``"fail"``;
    ``worst`` must be the item with the most regression flags, ties
    broken by the smallest index; and the top-level ``quality`` must be
    ``"pass"`` exactly when ``regressed`` is ``0``. Finally the file
    bytes must equal the canonical re-encoding of the decoded value
    byte for byte. Every key-order, type, range, relation, parse or
    canonical-byte mismatch raises ``ValueError``.

    Returns the trend as a dict with the keys in the order ``count,
    changes, regressed, worst, quality``, where ``changes`` is
    converted to a tuple and each item's ``qualities`` and
    ``regressions`` arrays are converted to tuples; ``worst`` is the
    matching item of that tuple. The input and the file are never
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
        _check_overview_trend(parsed)
        canonical = _dump_overview_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid overview trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_overview_trend output"
        )

    changes = tuple(
        {
            "index": item["index"],
            "qualities": tuple(item["qualities"]),
            "regressions": tuple(item["regressions"]),
            "quality": item["quality"],
        }
        for item in parsed["changes"]
    )
    worst_index = parsed["worst"]["index"]
    worst_item = changes[worst_index - 1]

    return {
        "count": parsed["count"],
        "changes": changes,
        "regressed": parsed["regressed"],
        "worst": worst_item,
        "quality": parsed["quality"],
    }


def render_overview_trend(path) -> str:
    """Render a :func:`load_overview_trend`-loaded JSON trend as text.

    :func:`load_overview_trend` is called exactly once with ``path``
    unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_trend` therefore apply here
    verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``C =
    T["changes"]`` and ``W = T["worst"]``; returns a leading summary
    line, a ``WORST`` line and then one line per change, joined by
    ``"\\n"`` with no trailing newline::

        TREND=<count>,<len(C)>,<regressed>,<quality>
        WORST=<i>;<q0,q1,q2,q3>;<b0,b1,b2,b3>;<quality>
        CHANGE[<i>]=<q0,q1,q2,q3>;<b0,b1,b2,b3>;<quality>

    The first line takes ``T["count"]``, ``len(C)``,
    ``T["regressed"]`` and ``T["quality"]`` in that order. In the
    ``WORST`` line and each ``CHANGE`` line ``i`` is the item's
    ``index``; ``q0``..``q3`` are the item's ``qualities`` in order
    (product, substrate, crosspoint, overall) and ``b0``..``b3`` are
    the item's ``regressions`` in the same order, rendered strictly
    as ``"True"``/``"False"``; the trailing ``quality`` is the item's
    ``quality``. ``CHANGE`` lines follow the original order of ``C``
    with no re-sorting. Values are copied directly from ``T`` with no
    recomputation: ints are formatted in decimal, strings are copied
    as-is and bools use ``str(value)``, following
    :func:`render_quality_report_trend`.
    """
    trend = load_overview_trend(path)
    changes = trend["changes"]
    worst = trend["worst"]

    lines = [
        f"TREND={_format_trend_value(trend['count'])},"
        f"{len(changes)},"
        f"{_format_trend_value(trend['regressed'])},"
        f"{_format_trend_value(trend['quality'])}"
    ]

    worst_qualities = ",".join(
        _format_trend_value(value) for value in worst["qualities"]
    )
    worst_regressions = ",".join(
        _format_trend_value(value) for value in worst["regressions"]
    )
    lines.append(
        f"WORST={_format_trend_value(worst['index'])};"
        f"{worst_qualities};{worst_regressions};"
        f"{_format_trend_value(worst['quality'])}"
    )

    for item in changes:
        qualities = ",".join(
            _format_trend_value(value) for value in item["qualities"]
        )
        regressions = ",".join(
            _format_trend_value(value) for value in item["regressions"]
        )
        lines.append(
            f"CHANGE[{_format_trend_value(item['index'])}]="
            f"{qualities};{regressions};"
            f"{_format_trend_value(item['quality'])}"
        )

    return "\n".join(lines)


def export_quality_report_trend(paths, output) -> bytes:
    """Serialize the :func:`quality_report_trend` comparison of ``paths`` and write it.

    Exactly one call to :func:`serialize_quality_report_trend` is made
    with ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``changes, worst,
    quality`` and JSON byte specification all apply here as well; in
    particular a bad ``paths`` value is reported before ``output`` is
    inspected. Neither ``paths`` nor the loaded files are modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_quality_report_trend`, ``output`` is then
    validated: it must be a non-empty ``str`` (a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``), in that
    order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_quality_report_trend(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data


def export_overview_trend(paths, output) -> bytes:
    """Serialize the :func:`overview_trend` comparison of ``paths`` and write it.

    Exactly one call to :func:`serialize_overview_trend` is made with
    ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``count, changes,
    regressed, worst, quality`` and JSON byte specification all apply
    here as well; in particular a bad ``paths`` value is reported before
    ``output`` is inspected. Neither ``paths`` nor the loaded files are
    modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_overview_trend`, ``output`` is then validated: it
    must be a non-empty ``str`` (a non-str raises ``TypeError`` and an
    empty ``str`` raises ``ValueError``), in that order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_overview_trend(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data


def export_overview_trend_report(path, output) -> bytes:
    """Serialize an overview trend report for ``path`` and write it.

    Exactly one call to :func:`load_overview_trend` is made with
    ``path`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    read behavior and file invariance apply here verbatim; in
    particular a bad ``path`` value is reported before ``output`` is
    inspected. The input file is not modified.

    Let ``T`` be the dict returned by that single call. The report is
    computed from ``T`` alone, without modifying it or recomputing
    ``worst``, and its keys are exactly in the order ``schema_version,
    source, summary, worst, quality``:

    - ``schema_version``: the non-bool int ``1``.
    - ``source``: keys in the order ``path, kind``, with ``path`` the
      original ``path`` argument and ``kind`` the string
      ``"overview_trend"``.
    - ``summary``: keys in the order ``count, changes, regressed,
      passed`` with values ``T["count"]``, ``len(T["changes"])``,
      ``T["regressed"]`` and ``len(T["changes"]) - T["regressed"]``.
    - ``worst``: an object with keys in the order ``index, qualities,
      regressions, quality``, each value taken from ``T["worst"]`` in
      that order; its two four-element tuples are encoded as JSON
      arrays.
    - ``quality``: ``T["quality"]``.

    The report is encoded to ``bytes`` ``B`` following the
    :func:`serialize_overview_trend` JSON byte specification: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; tuples are recursively converted to arrays. Any JSON or
    UTF-8 encoding failure raises ``ValueError``. Only after ``B`` has
    been encoded is ``output`` validated: it must be a non-empty
    ``str`` (a non-str raises ``TypeError`` and an empty ``str`` raises
    ``ValueError``), in that order.

    ``output`` must not name the same file as ``path``: when both
    sides exist they are compared with ``os.path.samefile`` so soft and
    hard links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    trend = load_overview_trend(path)
    changes = trend["changes"]
    worst = trend["worst"]

    report = {
        "schema_version": 1,
        "source": {
            "path": path,
            "kind": "overview_trend",
        },
        "summary": {
            "count": trend["count"],
            "changes": len(changes),
            "regressed": trend["regressed"],
            "passed": len(changes) - trend["regressed"],
        },
        "worst": {name: worst[name] for name in _OVERVIEW_TREND_ITEM_KEYS},
        "quality": trend["quality"],
    }

    data = _dump_overview_trend(report)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, [path])
    _atomic_write_bytes(output, data)
    return data


def _check_overview_trend_report(report):
    if not isinstance(report, dict):
        raise ValueError("overview trend report must be a JSON object")
    if list(report.keys()) != list(_OVERVIEW_TREND_REPORT_KEYS):
        raise ValueError(
            "overview trend report keys must be in the order "
            "schema_version, source, summary, worst, quality"
        )

    schema_version = report["schema_version"]
    if type(schema_version) is not int:
        raise ValueError(
            "overview trend report: schema_version must be a non-bool int"
        )
    if schema_version != 1:
        raise ValueError("overview trend report: schema_version must be 1")

    source = report["source"]
    if not isinstance(source, dict):
        raise ValueError(
            "overview trend report: source must be a JSON object"
        )
    if list(source.keys()) != list(_OVERVIEW_TREND_REPORT_SOURCE_KEYS):
        raise ValueError(
            "overview trend report: source keys must be in the order "
            "path, kind"
        )
    source_path = source["path"]
    if type(source_path) is not str:
        raise ValueError("overview trend report: source.path must be a str")
    if source_path == "":
        raise ValueError(
            "overview trend report: source.path must not be empty"
        )
    if source["kind"] != "overview_trend":
        raise ValueError(
            "overview trend report: source.kind must be 'overview_trend'"
        )

    summary = report["summary"]
    if not isinstance(summary, dict):
        raise ValueError(
            "overview trend report: summary must be a JSON object"
        )
    if list(summary.keys()) != list(_OVERVIEW_TREND_REPORT_SUMMARY_KEYS):
        raise ValueError(
            "overview trend report: summary keys must be in the order "
            "count, changes, regressed, passed"
        )

    count = summary["count"]
    if type(count) is not int:
        raise ValueError(
            "overview trend report: summary.count must be a non-bool int"
        )
    if not count >= 2:
        raise ValueError("overview trend report: summary.count must be >= 2")

    changes = summary["changes"]
    if type(changes) is not int:
        raise ValueError(
            "overview trend report: summary.changes must be a non-bool int"
        )
    if changes != count - 1:
        raise ValueError(
            "overview trend report: summary.changes must equal count - 1"
        )

    regressed = summary["regressed"]
    if type(regressed) is not int:
        raise ValueError(
            "overview trend report: summary.regressed must be a non-bool int"
        )
    if not 0 <= regressed <= changes:
        raise ValueError(
            "overview trend report: summary.regressed must be in "
            "[0, changes]"
        )

    passed = summary["passed"]
    if type(passed) is not int:
        raise ValueError(
            "overview trend report: summary.passed must be a non-bool int"
        )
    if passed != changes - regressed:
        raise ValueError(
            "overview trend report: summary.passed must equal "
            "changes - regressed"
        )

    worst = report["worst"]
    _check_overview_trend_item(worst, "overview trend report: worst: ")
    if not 1 <= worst["index"] <= changes:
        raise ValueError(
            "overview trend report: worst.index must be in [1, changes]"
        )

    quality = report["quality"]
    if type(quality) is not str:
        raise ValueError("overview trend report: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "overview trend report: quality must be 'pass' or 'fail'"
        )
    expected = "pass" if regressed == 0 else "fail"
    if quality != expected:
        raise ValueError(
            "overview trend report: quality must be 'pass' exactly when "
            "summary.regressed is 0"
        )
    if quality != worst["quality"]:
        raise ValueError(
            "overview trend report: quality must equal worst.quality"
        )


def load_overview_trend_report(path) -> dict:
    """Load an :func:`export_overview_trend_report` JSON report from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`export_overview_trend_report` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``schema_version, source, summary, worst, quality``:
    ``schema_version`` is the non-bool int ``1``; ``source`` is an
    object with keys exactly in the order ``path, kind`` whose values
    are a non-empty ``str`` and the string ``"overview_trend"``;
    ``summary`` is an object with keys exactly in the order ``count,
    changes, regressed, passed`` whose values are non-bool ints with
    ``count >= 2``, ``changes == count - 1``, ``0 <= regressed <=
    changes`` and ``passed == changes - regressed``; ``worst`` is an
    object with keys exactly in the order ``index, qualities,
    regressions, quality`` where ``index`` is a non-bool int in
    ``[1, changes]``, ``qualities`` is an array of exactly four
    ``"pass"``/``"fail"`` strings, ``regressions`` is an array of
    exactly four ``bool`` flags and its ``quality`` is ``"pass"``
    exactly when every regression flag is ``false``; and the top-level
    ``quality`` is ``"pass"`` or ``"fail"``, ``"pass"`` exactly when
    ``regressed`` is ``0``, and must equal ``worst.quality``. Finally
    the file bytes must equal the canonical re-encoding of the decoded
    value byte for byte. Every key-order, type, range, relation, parse
    or canonical-byte mismatch raises ``ValueError``.

    Returns the report as a dict with the keys in the order above,
    where only the ``qualities`` and ``regressions`` arrays of
    ``worst`` are converted to tuples; the file is never modified.
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
        _check_overview_trend_report(parsed)
        canonical = _dump_overview_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid overview trend report: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "export_overview_trend_report output"
        )

    worst = parsed["worst"]
    return {
        "schema_version": parsed["schema_version"],
        "source": parsed["source"],
        "summary": parsed["summary"],
        "worst": {
            "index": worst["index"],
            "qualities": tuple(worst["qualities"]),
            "regressions": tuple(worst["regressions"]),
            "quality": worst["quality"],
        },
        "quality": parsed["quality"],
    }


def render_overview_trend_report(path) -> str:
    """Render a :func:`load_overview_trend_report`-loaded JSON report as three lines.

    :func:`load_overview_trend_report` is called exactly once with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_trend_report` therefore
    apply here verbatim. The file is not modified.

    Let ``R`` be the dict returned by that single call; returns three
    lines joined by ``"\\n"`` with no trailing newline::

        REPORT=<schema_version>,<JSON path>,<kind>,<quality>
        SUMMARY=<count>,<changes>,<regressed>,<passed>
        WORST=<index>;<qualities>;<regressions>;<quality>

    The REPORT values are ``R["schema_version"]``, the compact
    ``ensure_ascii=False`` JSON string of ``R["source"]["path"]``
    (``json.dumps(v, ensure_ascii=False, separators=(",", ":"))``),
    ``R["source"]["kind"]`` and ``R["quality"]``; the SUMMARY values
    are the ``count``, ``changes``, ``regressed`` and ``passed`` of
    ``R["summary"]`` in that order; in the WORST line ``index`` and the
    trailing ``quality`` come from ``R["worst"]`` and ``qualities`` and
    ``regressions`` are its four items in their original order each
    joined by commas. Values are copied directly from ``R`` with no
    recomputation or re-sorting: ints are formatted in decimal,
    strings are copied as-is and bools render strictly as
    ``"True"``/``"False"``, following :func:`render_overview_trend`.
    """
    report = load_overview_trend_report(path)
    source = report["source"]
    summary = report["summary"]
    worst = report["worst"]

    source_path = json.dumps(
        source["path"], ensure_ascii=False, separators=(",", ":")
    )
    first_line = (
        f"REPORT={_format_trend_value(report['schema_version'])},"
        f"{source_path},"
        f"{_format_trend_value(source['kind'])},"
        f"{_format_trend_value(report['quality'])}"
    )
    second_line = (
        f"SUMMARY={_format_trend_value(summary['count'])},"
        f"{_format_trend_value(summary['changes'])},"
        f"{_format_trend_value(summary['regressed'])},"
        f"{_format_trend_value(summary['passed'])}"
    )
    worst_qualities = ",".join(
        _format_trend_value(value) for value in worst["qualities"]
    )
    worst_regressions = ",".join(
        _format_trend_value(value) for value in worst["regressions"]
    )
    third_line = (
        f"WORST={_format_trend_value(worst['index'])};"
        f"{worst_qualities};{worst_regressions};"
        f"{_format_trend_value(worst['quality'])}"
    )

    return "\n".join((first_line, second_line, third_line))


def compare_overview_reports(paths) -> dict:
    """Compare successive :func:`load_overview_trend_report` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_overview_trend_report` is then called exactly once per
    path, in input order; any exception it raises is propagated
    unchanged. The input and the loaded files are not modified.

    Every loaded report must have the same ``summary.count`` value as
    the first one; otherwise a ``ValueError`` is raised.

    For each successive pair ``i = 1..n-1`` the deltas are
    ``dr = summary.regressed_i - summary.regressed_(i-1)`` and
    ``dp = summary.passed_i - summary.passed_(i-1)``; a comparison
    fails (``q`` is ``"fail"``) when ``dr > 0``, ``dp < 0`` or the
    top-level ``quality`` changes from ``"pass"`` to ``"fail"``, and is
    ``"pass"`` otherwise.

    Returns a dict with keys in the order ``changes, worst, quality``:
    ``changes`` is a tuple with one dict per pair (in ``i`` order), each
    with keys in the order ``index, regressed_delta, passed_delta,
    quality`` — ``index`` is the non-bool int ``i``,
    ``regressed_delta``/``passed_delta`` are the non-bool ints ``dr``
    and ``dp`` and ``quality`` is ``q``. ``worst`` is the ``changes``
    item minimizing the tuple ``(passed_delta, -regressed_delta,
    index)`` lexicographically (the same dict object, never a copy);
    ``quality`` is ``"pass"`` exactly when every ``q`` is ``"pass"`` and
    ``"fail"`` otherwise. Items are not sorted, values are not
    recomputed and no other keys are added.
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

    reports = [load_overview_trend_report(path) for path in paths]

    first_count = reports[0]["summary"]["count"]
    for i in range(1, len(reports)):
        count = reports[i]["summary"]["count"]
        if count != first_count:
            raise ValueError(
                f"overview trend report at paths[{i}] summary.count "
                f"{count} does not match {first_count}"
            )

    changes = []
    worst_item = None
    worst_key = None
    overall = "pass"
    for i in range(1, len(reports)):
        previous_summary = reports[i - 1]["summary"]
        current_summary = reports[i]["summary"]
        dr = int(current_summary["regressed"]) - int(previous_summary["regressed"])
        dp = int(current_summary["passed"]) - int(previous_summary["passed"])
        if (
            dr > 0
            or dp < 0
            or (
                reports[i - 1]["quality"] == "pass"
                and reports[i]["quality"] == "fail"
            )
        ):
            verdict = "fail"
            overall = "fail"
        else:
            verdict = "pass"

        item = {
            "index": int(i),
            "regressed_delta": int(dr),
            "passed_delta": int(dp),
            "quality": verdict,
        }
        changes.append(item)

        key = (dp, -dr, i)
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "changes": tuple(changes),
        "worst": worst_item,
        "quality": overall,
    }


def _dump_overview_comparison(comparison) -> bytes:
    try:
        text = json.dumps(
            _to_jsonable(comparison),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"overview comparison: could not be serialized to JSON: {exc}"
        ) from exc


def serialize_overview_comparison(paths) -> bytes:
    """Serialize the :func:`compare_overview_reports` comparison of ``paths``.

    Exactly one call to :func:`compare_overview_reports` is made with
    ``paths`` unchanged and no other work happens before it; the
    ``paths`` validation contract, the per-path
    :func:`load_overview_trend_report` behavior, every exception
    (propagated unchanged) and the input/file invariance of
    :func:`compare_overview_reports` therefore apply here verbatim.
    Neither ``paths`` nor the loaded files are modified.

    Let ``C`` be the dict returned by that single
    :func:`compare_overview_reports` call. It is encoded with keys
    exactly in the order ``changes, worst, quality``; the ``changes``
    tuple is converted to a JSON array and each item, like ``worst``,
    keeps its key order ``index, regressed_delta, passed_delta,
    quality``.

    The JSON byte specification follows :func:`serialize_overview_trend`:
    UTF-8, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; tuples are recursively converted to arrays. Any JSON or
    UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    comparison = compare_overview_reports(paths)
    return _dump_overview_comparison(comparison)


def serialize_overview_comparison_report(path) -> bytes:
    """Serialize a report derived from a :func:`load_overview_comparison` file.

    Exactly one call to :func:`load_overview_comparison` is made with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_comparison` therefore apply
    here verbatim. The file is not modified.

    Let ``C`` be the dict returned by that single call. The report is
    computed from ``C`` alone, without recomputing the worst item,
    sorting or modifying ``C``, and encoded with keys exactly in the
    order ``schema_version, source, summary, worst, quality``:

    - ``schema_version``: the non-bool int ``1``.
    - ``source``: keys in the order ``path, kind``, with ``path`` the
      original ``path`` argument and ``kind`` the fixed string
      ``"overview_comparison"``.
    - ``summary``: keys in the order ``count, failed,
      regressed_delta, passed_delta`` — ``count`` is the number of
      change items ``len(C["changes"])``, ``failed`` is the number of
      change items whose ``quality`` is ``"fail"`` and
      ``regressed_delta``/``passed_delta`` are the integer sums of the
      respective deltas over the change items.
    - ``worst``: an object with keys in the order ``index,
      regressed_delta, passed_delta, quality``, each value taken from
      ``C["worst"]`` in that order.
    - ``quality``: ``C["quality"]``.

    The JSON byte specification follows
    :func:`serialize_overview_comparison`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; every float is rounded with ``round(float(v), 6)`` and
    negative zero is normalized to ``0.0`` only at write time; tuples
    are recursively converted to arrays. Any JSON or UTF-8 encoding
    failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    comparison = load_overview_comparison(path)
    changes = comparison["changes"]
    worst = comparison["worst"]

    failed = 0
    regressed_delta = 0
    passed_delta = 0
    for item in changes:
        if item["quality"] == "fail":
            failed += 1
        regressed_delta += item["regressed_delta"]
        passed_delta += item["passed_delta"]

    report = {
        "schema_version": 1,
        "source": {
            "path": path,
            "kind": "overview_comparison",
        },
        "summary": {
            "count": len(changes),
            "failed": failed,
            "regressed_delta": regressed_delta,
            "passed_delta": passed_delta,
        },
        "worst": {name: worst[name] for name in _OVERVIEW_COMPARISON_ITEM_KEYS},
        "quality": comparison["quality"],
    }

    return _dump_overview_comparison(report)


def _check_overview_comparison_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(_OVERVIEW_COMPARISON_ITEM_KEYS):
        raise ValueError(
            prefix + "keys must be in the order index, regressed_delta, "
            "passed_delta, quality"
        )

    index = item["index"]
    if type(index) is not int:
        raise ValueError(prefix + "index must be a non-bool int")

    for name in ("regressed_delta", "passed_delta"):
        value = item[name]
        if type(value) is not int:
            raise ValueError(prefix + f"{name} must be a non-bool int")

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")


def _check_overview_comparison(comparison):
    if not isinstance(comparison, dict):
        raise ValueError("overview comparison must be a JSON object")
    if list(comparison.keys()) != list(_OVERVIEW_COMPARISON_KEYS):
        raise ValueError(
            "overview comparison keys must be in the order "
            "changes, worst, quality"
        )

    changes = comparison["changes"]
    if not isinstance(changes, list):
        raise ValueError("overview comparison: changes must be a JSON array")
    if len(changes) == 0:
        raise ValueError("overview comparison: changes must be non-empty")

    worst_item = None
    worst_key = None
    for i in range(len(changes)):
        prefix = f"overview comparison: changes[{i}]: "
        item = changes[i]
        _check_overview_comparison_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(
                prefix + "index must run consecutively from 1"
            )
        key = (item["passed_delta"], -item["regressed_delta"], item["index"])
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    worst = comparison["worst"]
    _check_overview_comparison_item(worst, "overview comparison: worst: ")
    if worst != worst_item:
        raise ValueError(
            "overview comparison: worst must be the changes item "
            "minimizing (passed_delta, -regressed_delta, index)"
        )

    quality = comparison["quality"]
    if type(quality) is not str:
        raise ValueError("overview comparison: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "overview comparison: quality must be 'pass' or 'fail'"
        )
    expected = (
        "pass"
        if all(item["quality"] == "pass" for item in changes)
        else "fail"
    )
    if quality != expected:
        raise ValueError(
            "overview comparison: quality must be 'pass' exactly when "
            "every changes item is 'pass'"
        )


def load_overview_comparison(path) -> dict:
    """Load a :func:`serialize_overview_comparison` JSON comparison from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_overview_comparison` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``changes, worst, quality``. ``changes`` must be a non-empty
    JSON array whose items, like ``worst``, are objects with keys
    exactly in the order ``index, regressed_delta, passed_delta,
    quality``: ``index`` a non-bool int running consecutively from
    ``1``; ``regressed_delta`` and ``passed_delta`` non-bool ints; and
    ``quality`` either ``"pass"`` or ``"fail"``. ``worst`` must equal
    the ``changes`` item minimizing the tuple ``(passed_delta,
    -regressed_delta, index)`` and the top-level ``quality`` must be
    ``"pass"`` exactly when every ``changes`` item is ``"pass"``.
    Finally the file bytes must equal the canonical re-encoding of the
    decoded value byte for byte. Every key-order, type, relation, parse
    or canonical-byte mismatch raises ``ValueError``.

    Returns the comparison as a dict with the keys in the order
    ``changes, worst, quality``, where ``changes`` is converted to a
    tuple and ``worst`` is the matching item of that tuple; the file is
    never modified.
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
        _check_overview_comparison(parsed)
        canonical = _dump_overview_comparison(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid overview comparison: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_overview_comparison output"
        )

    changes = tuple(parsed["changes"])
    worst_item = None
    worst_key = None
    for item in changes:
        key = (item["passed_delta"], -item["regressed_delta"], item["index"])
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "changes": changes,
        "worst": worst_item,
        "quality": parsed["quality"],
    }


def _check_overview_comparison_report(report):
    if not isinstance(report, dict):
        raise ValueError("overview comparison report must be a JSON object")
    if list(report.keys()) != list(_OVERVIEW_COMPARISON_REPORT_KEYS):
        raise ValueError(
            "overview comparison report keys must be in the order "
            "schema_version, source, summary, worst, quality"
        )

    schema_version = report["schema_version"]
    if type(schema_version) is not int:
        raise ValueError(
            "overview comparison report: schema_version must be a "
            "non-bool int"
        )
    if schema_version != 1:
        raise ValueError(
            "overview comparison report: schema_version must be 1"
        )

    source = report["source"]
    if not isinstance(source, dict):
        raise ValueError(
            "overview comparison report: source must be a JSON object"
        )
    if list(source.keys()) != list(_OVERVIEW_COMPARISON_REPORT_SOURCE_KEYS):
        raise ValueError(
            "overview comparison report: source keys must be in the "
            "order path, kind"
        )
    source_path = source["path"]
    if type(source_path) is not str:
        raise ValueError(
            "overview comparison report: source.path must be a str"
        )
    if source_path == "":
        raise ValueError(
            "overview comparison report: source.path must not be empty"
        )
    if source["kind"] != "overview_comparison":
        raise ValueError(
            "overview comparison report: source.kind must be "
            "'overview_comparison'"
        )

    summary = report["summary"]
    if not isinstance(summary, dict):
        raise ValueError(
            "overview comparison report: summary must be a JSON object"
        )
    if list(summary.keys()) != list(
        _OVERVIEW_COMPARISON_REPORT_SUMMARY_KEYS
    ):
        raise ValueError(
            "overview comparison report: summary keys must be in the "
            "order count, failed, regressed_delta, passed_delta"
        )

    count = summary["count"]
    if type(count) is not int:
        raise ValueError(
            "overview comparison report: summary.count must be a "
            "non-bool int"
        )
    if not count > 0:
        raise ValueError(
            "overview comparison report: summary.count must be > 0"
        )

    failed = summary["failed"]
    if type(failed) is not int:
        raise ValueError(
            "overview comparison report: summary.failed must be a "
            "non-bool int"
        )
    if not 0 <= failed <= count:
        raise ValueError(
            "overview comparison report: summary.failed must be in "
            "[0, count]"
        )

    for name in ("regressed_delta", "passed_delta"):
        value = summary[name]
        if type(value) is not int:
            raise ValueError(
                f"overview comparison report: summary.{name} must be a "
                "non-bool int"
            )

    worst = report["worst"]
    _check_overview_comparison_item(
        worst, "overview comparison report: worst: "
    )
    if not 1 <= worst["index"] <= count:
        raise ValueError(
            "overview comparison report: worst.index must be in [1, count]"
        )

    quality = report["quality"]
    if type(quality) is not str:
        raise ValueError("overview comparison report: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "overview comparison report: quality must be 'pass' or 'fail'"
        )
    expected = "pass" if failed == 0 else "fail"
    if quality != expected:
        raise ValueError(
            "overview comparison report: quality must be 'pass' exactly "
            "when summary.failed is 0"
        )
    if quality == "pass" and worst["quality"] != "pass":
        raise ValueError(
            "overview comparison report: worst.quality must be 'pass' "
            "when quality is 'pass'"
        )


def load_overview_comparison_report(path) -> dict:
    """Load a :func:`serialize_overview_comparison_report` JSON report from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_overview_comparison_report` for the same value:
    compact UTF-8 JSON with no BOM and no trailing newline. A BOM, a
    trailing newline, a UTF-8 decoding failure, a JSON parsing failure,
    a ``NaN``/``Infinity`` constant or a repeated JSON object key raises
    ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``schema_version, source, summary, worst, quality``:
    ``schema_version`` is the non-bool int ``1``; ``source`` is an
    object with keys exactly in the order ``path, kind`` whose values
    are a non-empty ``str`` and the fixed string
    ``"overview_comparison"``; ``summary`` is an object with keys
    exactly in the order ``count, failed, regressed_delta,
    passed_delta`` whose four values are non-bool ints with
    ``count > 0`` and ``0 <= failed <= count``; ``worst`` is an object
    with keys exactly in the order ``index, regressed_delta,
    passed_delta, quality`` where ``index``, ``regressed_delta`` and
    ``passed_delta`` are non-bool ints with ``1 <= index <= count`` and
    ``quality`` is ``"pass"`` or ``"fail"``; and the top-level
    ``quality`` is ``"pass"`` or ``"fail"``, ``"pass"`` exactly when
    ``failed`` is ``0``, in which case ``worst.quality`` must also be
    ``"pass"``. Finally the file bytes must equal the canonical
    re-encoding of the decoded value via
    :func:`serialize_overview_comparison_report` byte for byte. Every
    key-order, type, range, relation, parse or canonical-byte mismatch
    raises ``ValueError``.

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
        _check_overview_comparison_report(parsed)
        canonical = _dump_overview_comparison(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid overview comparison report: "
            f"{exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_overview_comparison_report output"
        )

    return parsed


def overview_comparison_report_trend(paths) -> dict:
    """Compare successive :func:`load_overview_comparison_report` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_overview_comparison_report` is then called exactly once
    per path, in input order; any exception it raises is propagated
    unchanged. The input and the loaded files are not modified.

    Every loaded report must have the same ``summary.count`` value as
    the first one; otherwise a ``ValueError`` is raised.

    For each successive pair ``i = 1..n-1`` the deltas are
    ``f = summary.failed_i - summary.failed_(i-1)``,
    ``r = summary.regressed_delta_i -
    summary.regressed_delta_(i-1)`` and
    ``p = summary.passed_delta_i - summary.passed_delta_(i-1)``; a
    comparison fails (``q`` is ``"fail"``) when ``f > 0``, ``r > 0``,
    ``p < 0`` or the top-level ``quality`` changes from ``"pass"`` to
    ``"fail"``, and is ``"pass"`` otherwise.

    Returns a dict with keys in the order ``count, changes, regressed,
    worst, quality``: ``count`` is the non-bool int ``n`` (the number of
    snapshots); ``changes`` is a tuple with one dict per pair (in ``i``
    order), each with keys in the order ``index, failed_delta,
    regressed_delta, passed_delta, quality`` — ``index`` is the
    non-bool int ``i``, ``failed_delta``/``regressed_delta``/
    ``passed_delta`` are the non-bool ints ``f``, ``r`` and ``p`` and
    ``quality`` is ``q``. ``regressed`` is the number of ``changes``
    items whose ``quality`` is ``"fail"``. ``worst`` is the ``changes``
    item minimizing the tuple ``(p, -f, -r, i)`` lexicographically (the
    same dict object, never a copy); the top-level ``quality`` is
    ``"pass"`` exactly when ``regressed`` is ``0`` and ``"fail"``
    otherwise. Items are not sorted, values are not recomputed and no
    other keys are added.
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

    reports = [load_overview_comparison_report(path) for path in paths]

    first_count = reports[0]["summary"]["count"]
    for i in range(1, len(reports)):
        count = reports[i]["summary"]["count"]
        if count != first_count:
            raise ValueError(
                f"overview comparison report at paths[{i}] summary.count "
                f"{count} does not match {first_count}"
            )

    changes = []
    regressed = 0
    worst_item = None
    worst_key = None
    for i in range(1, len(reports)):
        previous_summary = reports[i - 1]["summary"]
        current_summary = reports[i]["summary"]
        f = int(current_summary["failed"]) - int(previous_summary["failed"])
        r = (
            int(current_summary["regressed_delta"])
            - int(previous_summary["regressed_delta"])
        )
        p = (
            int(current_summary["passed_delta"])
            - int(previous_summary["passed_delta"])
        )
        if (
            f > 0
            or r > 0
            or p < 0
            or (
                reports[i - 1]["quality"] == "pass"
                and reports[i]["quality"] == "fail"
            )
        ):
            verdict = "fail"
            regressed += 1
        else:
            verdict = "pass"

        item = {
            "index": int(i),
            "failed_delta": int(f),
            "regressed_delta": int(r),
            "passed_delta": int(p),
            "quality": verdict,
        }
        changes.append(item)

        key = (p, -f, -r, i)
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "count": len(paths),
        "changes": tuple(changes),
        "regressed": regressed,
        "worst": worst_item,
        "quality": "pass" if regressed == 0 else "fail",
    }


def serialize_overview_comparison_report_trend(paths) -> bytes:
    """Serialize the :func:`overview_comparison_report_trend` comparison of ``paths`` to bytes.

    Exactly one call to :func:`overview_comparison_report_trend` is
    made with ``paths`` unchanged and no other work happens before it;
    the ``paths`` validation contract (container, length, then each
    item in index order), the per-path
    :func:`load_overview_comparison_report` behavior, every exception
    (propagated unchanged, including the ``"paths[i]: "`` index
    prefixes) and the input/file invariance of
    :func:`overview_comparison_report_trend` therefore apply here
    verbatim. Neither ``paths`` nor the loaded files are modified.

    Let ``T`` be the dict returned by that single
    :func:`overview_comparison_report_trend` call. It is encoded
    directly with keys exactly in the order ``count, changes,
    regressed, worst, quality``; the ``changes`` tuple is converted to
    a JSON array in its original order and each change item, as well
    as ``worst``, keeps its key order ``index, failed_delta,
    regressed_delta, passed_delta, quality`` — the first four values
    are ints written in decimal and ``quality`` is only ``"pass"`` or
    ``"fail"``. ``worst`` is written with its original value: it is
    neither recomputed nor re-sorted and no keys are added.

    The JSON byte specification follows
    :func:`serialize_overview_comparison`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; tuples are recursively converted to arrays and ints are
    written in decimal. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    trend = overview_comparison_report_trend(paths)
    return _dump_overview_comparison_report_trend(trend)


def _dump_overview_comparison_report_trend(trend) -> bytes:
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
            "overview comparison report trend: could not be "
            f"serialized to JSON: {exc}"
        ) from exc


def _check_overview_comparison_report_trend_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(
        _OVERVIEW_COMPARISON_REPORT_TREND_ITEM_KEYS
    ):
        raise ValueError(
            prefix + "keys must be in the order index, failed_delta, "
            "regressed_delta, passed_delta, quality"
        )

    for name in ("index", "failed_delta", "regressed_delta", "passed_delta"):
        value = item[name]
        if type(value) is not int:
            raise ValueError(prefix + f"{name} must be a non-bool int")

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")


def _check_overview_comparison_report_trend(trend):
    if not isinstance(trend, dict):
        raise ValueError(
            "overview comparison report trend must be a JSON object"
        )
    if list(trend.keys()) != list(_OVERVIEW_COMPARISON_REPORT_TREND_KEYS):
        raise ValueError(
            "overview comparison report trend keys must be in the order "
            "count, changes, regressed, worst, quality"
        )

    count = trend["count"]
    if type(count) is not int:
        raise ValueError(
            "overview comparison report trend: count must be a non-bool int"
        )
    if not count >= 2:
        raise ValueError(
            "overview comparison report trend: count must be >= 2"
        )

    changes = trend["changes"]
    if not isinstance(changes, list):
        raise ValueError(
            "overview comparison report trend: changes must be a JSON array"
        )
    if len(changes) != count - 1:
        raise ValueError(
            "overview comparison report trend: changes must have "
            "count - 1 elements"
        )

    regressed_count = 0
    worst_item = None
    worst_key = None
    for i in range(len(changes)):
        prefix = f"overview comparison report trend: changes[{i}]: "
        item = changes[i]
        _check_overview_comparison_report_trend_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(prefix + "index must run consecutively from 1")
        if item["quality"] == "fail":
            regressed_count += 1
        key = (
            item["passed_delta"],
            -item["failed_delta"],
            -item["regressed_delta"],
            item["index"],
        )
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    regressed = trend["regressed"]
    if type(regressed) is not int:
        raise ValueError(
            "overview comparison report trend: regressed must be a "
            "non-bool int"
        )
    if regressed != regressed_count:
        raise ValueError(
            "overview comparison report trend: regressed must equal the "
            "number of fail items"
        )

    worst = trend["worst"]
    _check_overview_comparison_report_trend_item(
        worst, "overview comparison report trend: worst: "
    )
    if worst != worst_item:
        raise ValueError(
            "overview comparison report trend: worst must be the changes "
            "item minimizing (passed_delta, -failed_delta, "
            "-regressed_delta, index)"
        )

    quality = trend["quality"]
    if type(quality) is not str:
        raise ValueError(
            "overview comparison report trend: quality must be a str"
        )
    if quality not in _QUALITY_VALUES:
        raise ValueError(
            "overview comparison report trend: quality must be 'pass' or "
            "'fail'"
        )
    expected_quality = "pass" if regressed == 0 else "fail"
    if quality != expected_quality:
        raise ValueError(
            "overview comparison report trend: quality must be 'pass' "
            "exactly when regressed is 0"
        )


def load_overview_comparison_report_trend(path) -> dict:
    """Load a :func:`serialize_overview_comparison_report_trend` JSON trend from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_overview_comparison_report_trend` for the same
    value: compact UTF-8 JSON with no BOM and no trailing newline. A
    BOM, a trailing newline, a UTF-8 decoding failure, a JSON parsing
    failure, a ``NaN``/``Infinity`` constant, a repeated JSON object
    key or any other non-canonical byte sequence raises ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``count, changes, regressed, worst, quality``. ``count`` must
    be a non-bool int ``>= 2`` and ``changes`` a JSON array of exactly
    ``count - 1`` items. Each item, like ``worst``, must be an object
    with keys exactly in the order ``index, failed_delta,
    regressed_delta, passed_delta, quality``: the first four values
    must be non-bool ints, with ``index`` running consecutively from
    ``1``, and ``quality`` must be ``"pass"`` or ``"fail"``.
    ``regressed`` must equal the number of ``changes`` items whose
    ``quality`` is ``"fail"``; ``worst`` must equal the ``changes``
    item minimizing the tuple ``(passed_delta, -failed_delta,
    -regressed_delta, index)`` lexicographically; and the top-level
    ``quality`` must be ``"pass"`` exactly when ``regressed`` is ``0``
    and ``"fail"`` otherwise. Finally the file bytes must equal the
    canonical re-encoding of the decoded value byte for byte. Every
    key-order, type, range, relation, parse or canonical-byte
    mismatch raises ``ValueError``.

    Returns the trend as a dict with the keys in the order ``count,
    changes, regressed, worst, quality``, where ``changes`` is
    converted to a tuple and ``worst`` is the matching item of that
    tuple (the same object, never a copy). The input and the file are
    never modified.
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
        _check_overview_comparison_report_trend(parsed)
        canonical = _dump_overview_comparison_report_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "file does not contain a valid overview comparison report "
            f"trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_overview_comparison_report_trend output"
        )

    changes = tuple(parsed["changes"])
    worst_item = changes[parsed["worst"]["index"] - 1]

    return {
        "count": parsed["count"],
        "changes": changes,
        "regressed": parsed["regressed"],
        "worst": worst_item,
        "quality": parsed["quality"],
    }


def export_overview_comparison_report_trend(paths, output) -> bytes:
    """Serialize the :func:`overview_comparison_report_trend` comparison of ``paths`` and write it.

    Exactly one call to
    :func:`serialize_overview_comparison_report_trend` is made with
    ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``count, changes,
    regressed, worst, quality`` and JSON byte specification all apply
    here as well; in particular a bad ``paths`` value is reported before
    ``output`` is inspected. Neither ``paths`` nor the loaded files are
    modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_overview_comparison_report_trend`, ``output`` is
    then validated: it must be a non-empty ``str`` (a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``), in that
    order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_overview_comparison_report_trend(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data


def export_overview_comparison(paths, output) -> bytes:
    """Serialize the :func:`compare_overview_reports` comparison of ``paths`` and write it.

    Exactly one call to :func:`serialize_overview_comparison` is made
    with ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``changes, worst,
    quality`` and JSON byte specification all apply here as well; in
    particular a bad ``paths`` value is reported before ``output`` is
    inspected. Neither ``paths`` nor the loaded files are modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_overview_comparison`, ``output`` is then
    validated: it must be a non-empty ``str`` (a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``), in that
    order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_overview_comparison(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data


def export_overview_comparison_report(path, output) -> bytes:
    """Serialize an overview comparison report for ``path`` and write it.

    Exactly one call to
    :func:`serialize_overview_comparison_report` is made with ``path``
    — before any other work and no second time — so its validation,
    first-error order, exceptions (propagated unchanged), read
    behavior, report key order ``schema_version, source, summary,
    worst, quality`` and JSON byte specification all apply here as
    well; in particular a bad ``path`` value is reported before
    ``output`` is inspected. The input file is not modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_overview_comparison_report`, ``output`` is then
    validated: it must be a non-empty ``str`` (a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``), in that
    order.

    ``output`` must not name the same file as ``path``: when both
    sides exist they are compared with ``os.path.samefile`` so soft and
    hard links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_overview_comparison_report(path)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, [path])
    _atomic_write_bytes(output, data)
    return data


def render_overview_comparison(path) -> str:
    """Render a :func:`load_overview_comparison`-loaded JSON comparison as text.

    :func:`load_overview_comparison` is called exactly once with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_comparison` therefore apply
    here verbatim. The file is not modified.

    Let ``C`` be the dict returned by that single call; returns one
    line per change plus a leading summary line, joined by ``"\\n"``
    with no trailing newline. The first line is::

        QUALITY=<C["quality"]>;COUNT=<len(C["changes"])>;WORST_INDEX=<C["worst"]["index"]>

    followed by, for every item of ``C["changes"]`` in its original
    order, a line::

        CHANGE[<index>]=<regressed_delta>,<passed_delta>,<quality>

    where the three values are taken in the item's key order ``index,
    regressed_delta, passed_delta, quality`` with no re-sorting. Values
    are copied directly from ``C``: ints are formatted in decimal and
    strings are copied as-is, following
    :func:`render_quality_report_trend`.
    """
    comparison = load_overview_comparison(path)
    changes = comparison["changes"]

    lines = [
        f"QUALITY={_format_trend_value(comparison['quality'])};"
        f"COUNT={len(changes)};"
        f"WORST_INDEX={_format_trend_value(comparison['worst']['index'])}"
    ]
    for item in changes:
        lines.append(
            f"CHANGE[{_format_trend_value(item['index'])}]="
            f"{_format_trend_value(item['regressed_delta'])},"
            f"{_format_trend_value(item['passed_delta'])},"
            f"{_format_trend_value(item['quality'])}"
        )

    return "\n".join(lines)


def render_overview_comparison_report(path) -> str:
    """Render a :func:`load_overview_comparison_report`-loaded JSON report as three lines.

    :func:`load_overview_comparison_report` is called exactly once with
    ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_comparison_report`
    therefore apply here verbatim. The file is not modified.

    Let ``R`` be the dict returned by that single call; returns three
    lines joined by ``"\\n"`` with no trailing newline::

        REPORT=<schema_version>,<JSON path>,<kind>,<quality>
        SUMMARY=<count>,<failed>,<regressed_delta>,<passed_delta>
        WORST=<index>,<regressed_delta>,<passed_delta>,<quality>

    The REPORT values are ``R["schema_version"]``, the compact
    ``ensure_ascii=False`` JSON string of ``R["source"]["path"]``
    (``json.dumps(v, ensure_ascii=False, separators=(",", ":"))``),
    ``R["source"]["kind"]`` and ``R["quality"]``; the SUMMARY values
    are the ``count``, ``failed``, ``regressed_delta`` and
    ``passed_delta`` of ``R["summary"]`` in that order; the WORST
    values are the ``index``, ``regressed_delta``, ``passed_delta``
    and ``quality`` of ``R["worst"]`` in that order. Values are copied
    directly from ``R`` with no recomputation or re-sorting: ints are
    formatted in decimal and strings are copied as-is, following
    :func:`render_overview_trend_report`.
    """
    report = load_overview_comparison_report(path)
    source = report["source"]
    summary = report["summary"]
    worst = report["worst"]

    source_path = json.dumps(
        source["path"], ensure_ascii=False, separators=(",", ":")
    )
    first_line = (
        f"REPORT={_format_trend_value(report['schema_version'])},"
        f"{source_path},"
        f"{_format_trend_value(source['kind'])},"
        f"{_format_trend_value(report['quality'])}"
    )
    second_line = (
        f"SUMMARY={_format_trend_value(summary['count'])},"
        f"{_format_trend_value(summary['failed'])},"
        f"{_format_trend_value(summary['regressed_delta'])},"
        f"{_format_trend_value(summary['passed_delta'])}"
    )
    third_line = (
        f"WORST={_format_trend_value(worst['index'])},"
        f"{_format_trend_value(worst['regressed_delta'])},"
        f"{_format_trend_value(worst['passed_delta'])},"
        f"{_format_trend_value(worst['quality'])}"
    )

    return "\n".join((first_line, second_line, third_line))


def render_overview_comparison_report_trend(path) -> str:
    """Render a :func:`load_overview_comparison_report_trend`-loaded JSON trend as text.

    :func:`load_overview_comparison_report_trend` is called exactly once
    with ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_comparison_report_trend`
    therefore apply here verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``C =
    T["changes"]`` and ``W = T["worst"]``; returns two header lines
    followed by one line per change, joined by ``"\\n"`` with no
    trailing newline::

        TREND=<count>,<len(C)>,<regressed>,<quality>
        WORST=<index>,<failed_delta>,<regressed_delta>,<passed_delta>,<quality>
        CHANGE[<index>]=<failed_delta>,<regressed_delta>,<passed_delta>,<quality>

    The TREND values are ``T["count"]``, ``len(C)``, ``T["regressed"]``
    and ``T["quality"]`` in that order; the WORST values are the
    ``index``, ``failed_delta``, ``regressed_delta``, ``passed_delta``
    and ``quality`` of ``W`` in that order. The CHANGE lines then follow
    for every item of ``C`` in its original order, with the values
    taken in the item's key order ``index, failed_delta,
    regressed_delta, passed_delta, quality`` with no re-sorting. Values
    are copied directly from ``T`` with no recomputation: ints are
    formatted in decimal and strings are copied as-is, following
    :func:`render_overview_comparison_report`.
    """
    trend = load_overview_comparison_report_trend(path)
    changes = trend["changes"]
    worst = trend["worst"]

    first_line = (
        f"TREND={_format_trend_value(trend['count'])},"
        f"{len(changes)},"
        f"{_format_trend_value(trend['regressed'])},"
        f"{_format_trend_value(trend['quality'])}"
    )
    second_line = (
        f"WORST={_format_trend_value(worst['index'])},"
        f"{_format_trend_value(worst['failed_delta'])},"
        f"{_format_trend_value(worst['regressed_delta'])},"
        f"{_format_trend_value(worst['passed_delta'])},"
        f"{_format_trend_value(worst['quality'])}"
    )

    lines = [first_line, second_line]
    for item in changes:
        lines.append(
            f"CHANGE[{_format_trend_value(item['index'])}]="
            f"{_format_trend_value(item['failed_delta'])},"
            f"{_format_trend_value(item['regressed_delta'])},"
            f"{_format_trend_value(item['passed_delta'])},"
            f"{_format_trend_value(item['quality'])}"
        )

    return "\n".join(lines)


def trend_dashboard(path) -> dict:
    """Summarize a :func:`load_overview_comparison_report_trend`-loaded JSON trend.

    :func:`load_overview_comparison_report_trend` is called exactly once
    with ``path`` unchanged and no other work happens before it; the
    ``path`` validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`load_overview_comparison_report_trend`
    therefore apply here verbatim. The file is not modified.

    Let ``T`` be the dict returned by that single call, ``W =
    T["worst"]``, ``n = len(T["changes"])``, ``r = T["regressed"]`` and
    ``p = n - r``.

    Returns a dict with keys in the order ``trend, summary, quality``:
    ``trend`` is the ``T`` object itself (identity preserved, not
    modified); ``summary`` is a dict with keys in the order ``reports,
    passed, regressed, ratio, worst`` and values ``T["count"]``, ``p``,
    ``r``, ``round(float(p / n), 6)`` (negative zero normalized to
    ``0.0``) and ``W["index"]``; ``quality`` is ``T["quality"]``.
    ``reports``, ``passed``, ``regressed`` and ``worst`` are ``int`` and
    ``ratio`` is a ``float``. ``worst`` is not recomputed and no other
    keys are added.
    """
    trend = load_overview_comparison_report_trend(path)
    worst = trend["worst"]

    n = len(trend["changes"])
    r = trend["regressed"]
    p = n - r
    ratio = round(float(p / n), 6)
    if ratio == 0:
        ratio = 0.0

    return {
        "trend": trend,
        "summary": {
            "reports": trend["count"],
            "passed": p,
            "regressed": r,
            "ratio": ratio,
            "worst": worst["index"],
        },
        "quality": trend["quality"],
    }


def serialize_trend_dashboard(path) -> bytes:
    """Serialize the :func:`trend_dashboard` summary of ``path`` to bytes.

    Exactly one call to :func:`trend_dashboard` is made with ``path``
    unchanged and no other work happens before it; the ``path``
    validation contract, the read behavior, every exception
    (``TypeError``/``ValueError``/``FileNotFoundError``/
    ``IsADirectoryError``/``OSError``, propagated unchanged) and the
    file invariance of :func:`trend_dashboard` therefore apply here
    verbatim. The file is not modified.

    Let ``D`` be the dict returned by that single
    :func:`trend_dashboard` call. It is encoded directly with keys
    exactly in the order ``trend, summary, quality`` and no keys are
    added: ``trend`` keeps the value returned by
    :func:`trend_dashboard` (its key order ``count, changes,
    regressed, worst, quality`` and each change item's order ``index,
    failed_delta, regressed_delta, passed_delta, quality``), and
    ``summary`` keeps its key order ``reports, passed, regressed,
    ratio, worst``.

    The JSON byte specification follows
    :func:`serialize_overview_comparison_report_trend`: UTF-8,
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation, no BOM and no trailing
    newline; tuples are recursively converted to arrays and ints are
    written in decimal. Every float is rounded with
    ``round(float(v), 6)`` and negative zero is normalized to ``0.0``
    only at write time. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    dashboard = trend_dashboard(path)
    return _dump_overview_comparison_report_trend(dashboard)


def _check_trend_dashboard_summary(summary, trend):
    if not isinstance(summary, dict):
        raise ValueError("trend dashboard: summary must be a JSON object")
    if list(summary.keys()) != list(_TREND_DASHBOARD_SUMMARY_KEYS):
        raise ValueError(
            "trend dashboard: summary keys must be in the order "
            "reports, passed, regressed, ratio, worst"
        )

    changes = trend["changes"]
    count = len(changes)
    regressed = trend["regressed"]
    passed = count - regressed

    reports = summary["reports"]
    if type(reports) is not int:
        raise ValueError(
            "trend dashboard: summary.reports must be a non-bool int"
        )
    if reports != trend["count"]:
        raise ValueError(
            "trend dashboard: summary.reports must equal trend.count"
        )

    passed_value = summary["passed"]
    if type(passed_value) is not int:
        raise ValueError(
            "trend dashboard: summary.passed must be a non-bool int"
        )
    if passed_value != passed:
        raise ValueError(
            "trend dashboard: summary.passed must equal "
            "len(trend.changes) - trend.regressed"
        )

    regressed_value = summary["regressed"]
    if type(regressed_value) is not int:
        raise ValueError(
            "trend dashboard: summary.regressed must be a non-bool int"
        )
    if regressed_value != regressed:
        raise ValueError(
            "trend dashboard: summary.regressed must equal trend.regressed"
        )

    ratio = summary["ratio"]
    if type(ratio) is not float:
        raise ValueError("trend dashboard: summary.ratio must be a float")
    if not math.isfinite(ratio):
        raise ValueError("trend dashboard: summary.ratio must be finite")
    if ratio == 0.0 and math.copysign(1.0, ratio) < 0:
        raise ValueError(
            "trend dashboard: summary.ratio must not be negative zero"
        )
    if ratio != round(float(passed / count), 6):
        raise ValueError(
            "trend dashboard: summary.ratio must equal "
            "round(float(passed / len(trend.changes)), 6)"
        )

    worst = summary["worst"]
    if type(worst) is not int:
        raise ValueError(
            "trend dashboard: summary.worst must be a non-bool int"
        )
    if worst != trend["worst"]["index"]:
        raise ValueError(
            "trend dashboard: summary.worst must equal trend.worst.index"
        )


def _check_trend_dashboard(dashboard):
    if not isinstance(dashboard, dict):
        raise ValueError("trend dashboard must be a JSON object")
    if list(dashboard.keys()) != list(_TREND_DASHBOARD_KEYS):
        raise ValueError(
            "trend dashboard keys must be in the order trend, summary, quality"
        )

    _check_overview_comparison_report_trend(dashboard["trend"])
    _check_trend_dashboard_summary(dashboard["summary"], dashboard["trend"])

    quality = dashboard["quality"]
    if type(quality) is not str:
        raise ValueError("trend dashboard: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("trend dashboard: quality must be 'pass' or 'fail'")
    if quality != dashboard["trend"]["quality"]:
        raise ValueError(
            "trend dashboard: quality must equal trend.quality"
        )


def load_trend_dashboard(path) -> dict:
    """Load a :func:`serialize_trend_dashboard` JSON dashboard from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_trend_dashboard` for the same value: compact UTF-8
    JSON with no BOM and no trailing newline. A BOM, a trailing newline,
    a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant, a repeated JSON object key or any
    other non-canonical byte sequence raises ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``trend, summary, quality``. ``trend`` must satisfy the full
    :func:`load_overview_comparison_report_trend` contract (key order
    ``count, changes, regressed, worst, quality`` and all of its
    type, range, relation and canonical-byte requirements). ``summary``
    must be an object with keys exactly in the order ``reports, passed,
    regressed, ratio, worst``: ``reports`` must equal ``trend.count``,
    ``passed`` must equal ``len(trend.changes) - trend.regressed`` and
    ``regressed`` must equal ``trend.regressed``; ``reports``,
    ``passed``, ``regressed`` and ``worst`` must be non-bool ints, with
    ``worst`` equal to ``trend.worst.index``; ``ratio`` must be a finite
    non-bool float with at most six decimals, not negative zero, equal
    to ``round(float(passed / len(trend.changes)), 6)``. The top-level
    ``quality`` must equal ``trend.quality``. Finally the file bytes
    must equal the canonical :func:`serialize_trend_dashboard`
    re-encoding of the decoded value byte for byte. Every key-order,
    type, range, relation, parse or canonical-byte mismatch raises
    ``ValueError``.

    Returns the dashboard as a dict with the keys in the order ``trend,
    summary, quality``; ``trend`` keeps the key order ``count, changes,
    regressed, worst, quality``, its ``changes`` is converted to a
    tuple and ``worst`` is the matching item of that tuple (the same
    object, never a copy), and ``summary`` keeps the key order
    ``reports, passed, regressed, ratio, worst``. The input and the
    file are never modified.
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
        _check_trend_dashboard(parsed)
        canonical = _dump_overview_comparison_report_trend(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid trend dashboard: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_trend_dashboard output"
        )

    parsed_trend = parsed["trend"]
    changes = tuple(parsed_trend["changes"])
    worst_item = changes[parsed_trend["worst"]["index"] - 1]
    trend = {
        "count": parsed_trend["count"],
        "changes": changes,
        "regressed": parsed_trend["regressed"],
        "worst": worst_item,
        "quality": parsed_trend["quality"],
    }

    parsed_summary = parsed["summary"]
    summary = {
        "reports": parsed_summary["reports"],
        "passed": parsed_summary["passed"],
        "regressed": parsed_summary["regressed"],
        "ratio": parsed_summary["ratio"],
        "worst": parsed_summary["worst"],
    }

    return {
        "trend": trend,
        "summary": summary,
        "quality": parsed["quality"],
    }


def export_trend_dashboard(path, output) -> bytes:
    """Serialize a :func:`trend_dashboard` summary for ``path`` and write it.

    Exactly one call to :func:`serialize_trend_dashboard` is made with
    ``path`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    read behavior, dashboard key order ``trend, summary, quality`` and
    JSON byte specification all apply here as well; in particular a
    bad ``path`` value is reported before ``output`` is inspected. The
    input file is not modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_trend_dashboard`, ``output`` is then validated:
    it must be a non-empty ``str`` (a non-str raises ``TypeError`` and
    an empty ``str`` raises ``ValueError``), in that order.

    ``output`` must not name the same file as ``path``: when both
    sides exist they are compared with ``os.path.samefile`` so soft
    and hard links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any
    failure before the replacement removes the temporary file and
    leaves an existing ``output`` byte for byte unchanged;
    ``OSError`` is propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_trend_dashboard(path)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, [path])
    _atomic_write_bytes(output, data)
    return data


def dashboard_history(paths) -> dict:
    """Compare successive :func:`load_trend_dashboard` snapshots along ``paths``.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_trend_dashboard` is then called exactly once per path,
    in input order; any exception it raises is propagated unchanged.
    The input and the loaded files are not modified.

    Every loaded dashboard must have the same ``summary.reports`` value
    as the first one; otherwise a ``ValueError`` is raised.

    For each successive pair ``i = 1..n-1`` the unrounded deltas are
    ``dp = summary.passed_i - summary.passed_(i-1)``,
    ``dr = summary.regressed_i - summary.regressed_(i-1)`` and
    ``dq = summary.ratio_i - summary.ratio_(i-1)``; a comparison fails
    (``q`` is ``"fail"``) when ``dp < 0``, ``dr > 0``, ``dq < 0`` or the
    top-level ``quality`` changes from ``"pass"`` to ``"fail"``, and is
    ``"pass"`` otherwise.

    Returns a dict with keys in the order ``count, changes, regressed,
    worst, quality``: ``count`` is the non-bool int ``n`` (the number of
    snapshots); ``changes`` is a tuple with one dict per pair (in ``i``
    order), each with keys in the order ``index, passed_delta,
    regressed_delta, ratio_delta, quality`` — ``index`` is the non-bool
    int ``i``, ``passed_delta``/``regressed_delta`` are the unrounded
    non-bool ints ``dp`` and ``dr``, ``ratio_delta`` is
    ``round(float(dq), 6)`` (negative zero normalized to ``0.0``) and
    ``quality`` is ``q``. ``regressed`` is the number of ``changes``
    items whose ``quality`` is ``"fail"``. ``worst`` is the ``changes``
    item minimizing the *unrounded* tuple ``(dq, dp, -dr, i)``
    lexicographically (the same dict object, never a copy); the
    top-level ``quality`` is ``"pass"`` exactly when ``regressed`` is
    ``0`` and ``"fail"`` otherwise. Items are not sorted, values are not
    recomputed and no other keys are added.
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

    dashboards = [load_trend_dashboard(path) for path in paths]

    first_reports = dashboards[0]["summary"]["reports"]
    for i in range(1, len(dashboards)):
        reports = dashboards[i]["summary"]["reports"]
        if reports != first_reports:
            raise ValueError(
                f"trend dashboard at paths[{i}] summary.reports "
                f"{reports} does not match {first_reports}"
            )

    changes = []
    regressed = 0
    worst_item = None
    worst_key = None
    for i in range(1, len(dashboards)):
        previous_summary = dashboards[i - 1]["summary"]
        current_summary = dashboards[i]["summary"]
        dp = int(current_summary["passed"]) - int(previous_summary["passed"])
        dr = (
            int(current_summary["regressed"])
            - int(previous_summary["regressed"])
        )
        dq = (
            float(current_summary["ratio"])
            - float(previous_summary["ratio"])
        )
        if (
            dp < 0
            or dr > 0
            or dq < 0
            or (
                dashboards[i - 1]["quality"] == "pass"
                and dashboards[i]["quality"] == "fail"
            )
        ):
            verdict = "fail"
            regressed += 1
        else:
            verdict = "pass"

        ratio_delta = round(float(dq), 6)
        if ratio_delta == 0:
            ratio_delta = 0.0

        item = {
            "index": int(i),
            "passed_delta": int(dp),
            "regressed_delta": int(dr),
            "ratio_delta": ratio_delta,
            "quality": verdict,
        }
        changes.append(item)

        key = (dq, dp, -dr, i)
        if worst_key is None or key < worst_key:
            worst_key = key
            worst_item = item

    return {
        "count": len(paths),
        "changes": tuple(changes),
        "regressed": regressed,
        "worst": worst_item,
        "quality": "pass" if regressed == 0 else "fail",
    }


def _dump_dashboard_history(history) -> bytes:
    try:
        text = json.dumps(
            _to_jsonable(history),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"dashboard history: could not be serialized to JSON: {exc}"
        ) from exc


def serialize_dashboard_history(paths) -> bytes:
    """Serialize the :func:`dashboard_history` comparison of ``paths`` to bytes.

    Exactly one call to :func:`dashboard_history` is made with ``paths``
    unchanged and no other work happens before it; the ``paths``
    validation contract, the per-path :func:`load_trend_dashboard`
    behavior, every exception (propagated unchanged) and the
    input/file invariance of :func:`dashboard_history` therefore apply
    here verbatim. Neither ``paths`` nor the loaded files are modified.

    Let ``H`` be the dict returned by that single
    :func:`dashboard_history` call. It is encoded directly with keys
    exactly in the order ``count, changes, regressed, worst, quality``
    and no keys are added: the ``changes`` tuple is recursively
    converted to a JSON array and each change item, like ``worst``,
    keeps its key order ``index, passed_delta, regressed_delta,
    ratio_delta, quality``.

    The JSON byte specification follows
    :func:`serialize_trend_dashboard`: UTF-8, ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline; tuples are recursively converted to
    arrays and ints are written in decimal. Every float is rounded
    with ``round(float(v), 6)`` and negative zero is normalized to
    ``0.0`` only at write time. Any JSON or UTF-8 encoding failure
    raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    history = dashboard_history(paths)
    return _dump_dashboard_history(history)


def _check_dashboard_history_item(item, prefix):
    if not isinstance(item, dict):
        raise ValueError(prefix + "must be a JSON object")
    if list(item.keys()) != list(_DASHBOARD_HISTORY_ITEM_KEYS):
        raise ValueError(
            prefix + "keys must be in the order index, passed_delta, "
            "regressed_delta, ratio_delta, quality"
        )

    for name in ("index", "passed_delta", "regressed_delta"):
        value = item[name]
        if type(value) is not int:
            raise ValueError(prefix + f"{name} must be a non-bool int")

    ratio_delta = item["ratio_delta"]
    if type(ratio_delta) is not float:
        raise ValueError(prefix + "ratio_delta must be a float")
    if not math.isfinite(ratio_delta):
        raise ValueError(prefix + "ratio_delta must be finite")
    if not -1.0 <= ratio_delta <= 1.0:
        raise ValueError(prefix + "ratio_delta must be in [-1, 1]")
    if ratio_delta != round(ratio_delta, 6):
        raise ValueError(prefix + "ratio_delta must have at most 6 decimals")
    if ratio_delta == 0.0 and math.copysign(1.0, ratio_delta) < 0:
        raise ValueError(prefix + "ratio_delta must not be negative zero")

    quality = item["quality"]
    if type(quality) is not str:
        raise ValueError(prefix + "quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")


def _check_dashboard_history(history):
    if not isinstance(history, dict):
        raise ValueError("dashboard history must be a JSON object")
    if list(history.keys()) != list(_DASHBOARD_HISTORY_KEYS):
        raise ValueError(
            "dashboard history keys must be in the order count, changes, "
            "regressed, worst, quality"
        )

    count = history["count"]
    if type(count) is not int:
        raise ValueError("dashboard history: count must be a non-bool int")
    if not count >= 2:
        raise ValueError("dashboard history: count must be >= 2")

    changes = history["changes"]
    if not isinstance(changes, list):
        raise ValueError("dashboard history: changes must be a JSON array")
    if len(changes) != count - 1:
        raise ValueError(
            "dashboard history: changes must have count - 1 elements"
        )

    for i in range(len(changes)):
        prefix = f"dashboard history: changes[{i}]: "
        item = changes[i]
        _check_dashboard_history_item(item, prefix)
        if item["index"] != i + 1:
            raise ValueError(prefix + "index must run consecutively from 1")

    regressed = history["regressed"]
    if type(regressed) is not int:
        raise ValueError(
            "dashboard history: regressed must be a non-bool int"
        )
    fail_count = sum(1 for item in changes if item["quality"] == "fail")
    if regressed != fail_count:
        raise ValueError(
            "dashboard history: regressed must equal the number of "
            "fail items"
        )

    worst = history["worst"]
    _check_dashboard_history_item(worst, "dashboard history: worst: ")
    if worst not in changes:
        raise ValueError(
            "dashboard history: worst must equal one of the changes items"
        )

    quality = history["quality"]
    if type(quality) is not str:
        raise ValueError("dashboard history: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("dashboard history: quality must be 'pass' or 'fail'")
    if quality != ("pass" if regressed == 0 else "fail"):
        raise ValueError(
            "dashboard history: quality must be 'pass' exactly when "
            "regressed is 0"
        )


def load_dashboard_history(path) -> dict:
    """Load a :func:`serialize_dashboard_history` JSON history from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises ``TypeError``
    and an empty ``str`` raises ``ValueError``. The file is opened in
    binary mode (``"rb"``) and read in full; a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError`` and
    every other ``OSError`` is propagated unchanged. The file is not
    modified.

    The bytes must be exactly those produced by
    :func:`serialize_dashboard_history` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure, a JSON parsing failure, a
    ``NaN``/``Infinity`` constant, a repeated JSON object key or any
    other non-canonical byte sequence raises ``ValueError``.

    The decoded value must be a JSON object with keys exactly in the
    order ``count, changes, regressed, worst, quality``. ``count`` must
    be a non-bool int ``>= 2`` and ``changes`` a JSON array of exactly
    ``count - 1`` items. Each item, like ``worst``, must be an object
    with keys exactly in the order ``index, passed_delta,
    regressed_delta, ratio_delta, quality``: ``index`` a non-bool int
    running consecutively from ``1``; ``passed_delta`` and
    ``regressed_delta`` non-bool ints; ``ratio_delta`` a finite
    non-bool float in ``[-1, 1]`` with at most six decimals and not
    negative zero; ``quality`` either ``"pass"`` or ``"fail"``.
    ``regressed`` must be a non-bool int equal to the number of
    ``changes`` items whose ``quality`` is ``"fail"``; ``worst`` must
    equal one of the ``changes`` items; and the top-level ``quality``
    must be ``"pass"`` exactly when ``regressed`` is ``0``. Finally the
    file bytes must equal the canonical
    :func:`serialize_dashboard_history` re-encoding of the decoded
    value byte for byte. Every key-order, type, range, relation, parse
    or canonical-byte mismatch raises ``ValueError``.

    Returns the history as a dict with the keys in the order ``count,
    changes, regressed, worst, quality``; ``changes`` is converted to a
    tuple and ``worst`` is the matching item of that tuple (the same
    object, never a copy). The input and the file are never modified.
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
        _check_dashboard_history(parsed)
        canonical = _dump_dashboard_history(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid dashboard history: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_dashboard_history output"
        )

    changes = tuple(parsed["changes"])
    worst = parsed["worst"]
    matched = next(item for item in changes if item == worst)

    return {
        "count": parsed["count"],
        "changes": changes,
        "regressed": parsed["regressed"],
        "worst": matched,
        "quality": parsed["quality"],
    }


def export_dashboard_history(paths, output) -> bytes:
    """Serialize the :func:`dashboard_history` comparison of ``paths`` and write it.

    Exactly one call to :func:`serialize_dashboard_history` is made with
    ``paths`` — before any other work and no second time — so its
    validation, first-error order, exceptions (propagated unchanged),
    ``"paths[i]: "`` index prefixes, key order ``count, changes,
    regressed, worst, quality`` and JSON byte specification all apply
    here as well; in particular a bad ``paths`` value is reported before
    ``output`` is inspected. Neither ``paths`` nor the loaded files are
    modified.

    With ``B`` the ``bytes`` returned by
    :func:`serialize_dashboard_history`, ``output`` is then validated:
    it must be a non-empty ``str`` (a non-str raises ``TypeError`` and
    an empty ``str`` raises ``ValueError``), in that order.

    ``output`` must not name the same file as any of the ``paths``
    items: when both sides exist they are compared with
    ``os.path.samefile`` so soft and hard links are recognized, and
    otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in
    ``output``'s directory, ``B`` is written to it in binary mode,
    ``flush()`` and ``os.fsync()`` are called and the temporary file
    then atomically replaces ``output`` via ``os.replace``. Any failure
    before the replacement removes the temporary file and leaves an
    existing ``output`` byte for byte unchanged; ``OSError`` is
    propagated unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    data = serialize_dashboard_history(paths)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    _reject_export_output_overlap(output, paths)
    _atomic_write_bytes(output, data)
    return data
