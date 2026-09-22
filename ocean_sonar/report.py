"""Combined crosspoint and terrain-quality report generation.

Aggregates :func:`ocean_sonar.crosspoint.evaluate` and
:func:`ocean_sonar.quality.assess` into a single report with an
overall pass/fail verdict.
"""

from __future__ import annotations

from .crosspoint import evaluate
from .quality import assess

__all__ = ["generate"]


def generate(crossings, layers, tolerance=0.5, slope_limit=5.0, roughness_limit=1.0):
    """Generate the combined crosspoint and terrain report.

    Calls :func:`evaluate` (validating ``crossings`` then
    ``tolerance``) followed by :func:`assess` (validating ``layers``
    then ``slope_limit`` then ``roughness_limit``), so the first-error
    order is crossings → tolerance → layers → slope_limit →
    roughness_limit. Every exception from either function is
    propagated unchanged and inputs are not modified.

    Returns a dict with keys in the order
    ``crosspoint, terrain, overall``: ``crosspoint`` is the dict
    returned by :func:`evaluate`, ``terrain`` is the tuple returned by
    :func:`assess` (nested key order, tuple levels, numeric types and
    rounding unchanged). ``overall`` is ``"pass"`` only when
    ``crosspoint["quality"] == "pass"`` and every terrain item has
    ``slope_exceed`` and ``roughness_exceed`` equal to ``0``;
    otherwise it is ``"fail"``.
    """
    crosspoint = evaluate(crossings, tolerance)
    terrain = assess(layers, slope_limit, roughness_limit)

    overall = "pass"
    if crosspoint["quality"] != "pass":
        overall = "fail"
    else:
        for item in terrain:
            if item["slope_exceed"] != 0 or item["roughness_exceed"] != 0:
                overall = "fail"
                break

    return {
        "crosspoint": crosspoint,
        "terrain": terrain,
        "overall": overall,
    }
