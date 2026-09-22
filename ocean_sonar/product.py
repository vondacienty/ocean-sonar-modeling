"""End-to-end sonar product pipeline.

Runs the complete modelling chain in one call: grid binning
(:func:`ocean_sonar.grid.build`), terrain analysis
(:func:`ocean_sonar.terrain.analyze_layers`), quality assessment
(:func:`ocean_sonar.quality.assess`), substrate classification
(:func:`ocean_sonar.substrate.classify`), crosspoint evaluation
(:func:`ocean_sonar.crosspoint.evaluate`) and the combined report
(:func:`ocean_sonar.report.summarize`), bundling the per-layer results
into a single product dict.
"""

from __future__ import annotations

from . import crosspoint, grid, quality, report, substrate, terrain

__all__ = ["build"]


def build(points, bounds, resolutions, crossings, tolerance=0.5, slope_limit=5.0, roughness_limit=1.0):
    """Build the full crosspoint/per-layer/overall sonar product.

    The pipeline runs strictly in this order, exactly once each:
    :func:`grid.build <ocean_sonar.grid.build>` on
    ``points``/``bounds``/``resolutions``, then
    :func:`terrain.analyze_layers <ocean_sonar.terrain.analyze_layers>`
    on the grid tuple, then :func:`quality.assess
    <ocean_sonar.quality.assess>` and :func:`substrate.classify
    <ocean_sonar.substrate.classify>` (both on
    ``(resolution, nx, ny, analysis)`` tuples taken from the
    analysis results, and both given ``slope_limit``/
    ``roughness_limit``), then :func:`crosspoint.evaluate
    <ocean_sonar.crosspoint.evaluate>` on ``crossings`` with
    ``tolerance``, and finally :func:`report.summarize
    <ocean_sonar.report.summarize>` on the three results. Any exception
    from a stage short-circuits the pipeline and is propagated
    unchanged; every stage keeps its own validation, rounding and
    key-order contract. Inputs are not modified.

    Returns a dict with keys in the order ``crosspoint, layers,
    overall``: ``crosspoint`` is the dict returned by
    :func:`~ocean_sonar.crosspoint.evaluate`, ``layers`` is a tuple
    with one dict per grid layer (resolution order) and ``overall`` is
    the ``overall`` value of the :func:`~ocean_sonar.report.summarize`
    result. Each layer dict has keys in the order ``resolution, nx, ny,
    cells, analysis, quality, substrate``: the first four values come
    straight from the corresponding :func:`~ocean_sonar.grid.build`
    layer ``(r, nx, ny, cells)``, ``analysis`` is the tuple from
    :func:`~ocean_sonar.terrain.analyze_layers`, and ``quality``/
    ``substrate`` are the matching items returned by
    :func:`~ocean_sonar.quality.assess` and
    :func:`~ocean_sonar.substrate.classify`.
    """
    grids = grid.build(points, bounds, resolutions)
    analyses = terrain.analyze_layers(grids)

    analysis_layers = tuple(
        (item["resolution"], item["nx"], item["ny"], item["analysis"])
        for item in analyses
    )
    qualities = quality.assess(
        analysis_layers, slope_limit, roughness_limit
    )
    substrates = substrate.classify(
        analysis_layers, slope_limit, roughness_limit
    )

    crosspoint_result = crosspoint.evaluate(crossings, tolerance)
    summary = report.summarize(crosspoint_result, qualities, substrates)

    layers = tuple(
        {
            "resolution": grids[i][0],
            "nx": grids[i][1],
            "ny": grids[i][2],
            "cells": grids[i][3],
            "analysis": analyses[i]["analysis"],
            "quality": qualities[i],
            "substrate": substrates[i],
        }
        for i in range(len(grids))
    )

    return {
        "crosspoint": crosspoint_result,
        "layers": layers,
        "overall": summary["overall"],
    }
