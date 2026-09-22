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

from . import crosspoint, grid, quality, report, substrate, terrain

__all__ = ["build"]


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
