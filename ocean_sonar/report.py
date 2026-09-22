"""Combined crosspoint and terrain quality report.

Aggregates :func:`ocean_sonar.crosspoint.evaluate` and
:func:`ocean_sonar.quality.assess` into a single report whose
``overall`` verdict passes only when both the crosspoint check and
every terrain layer pass.
"""

from __future__ import annotations

from .crosspoint import evaluate
from .quality import assess

__all__ = ["generate"]


def generate(crossings, layers, tolerance=0.5, slope_limit=5.0, roughness_limit=1.0):
    """Generate the combined crosspoint/terrain quality report.

    Crosspoints are evaluated first with ``tolerance``; terrain layers
    are assessed afterwards with ``slope_limit``/``roughness_limit``.
    Input structures, finiteness/range checks, exception types,
    messages and prefixes are exactly those of
    :func:`ocean_sonar.crosspoint.evaluate` and
    :func:`ocean_sonar.quality.assess`; the first error wins in the
    order ``crossings`` → ``tolerance`` → ``layers`` → ``slope_limit``
    → ``roughness_limit``. Any exception propagates unchanged and the
    inputs are not modified.

    Returns a dict with keys in the fixed order
    ``crosspoint, terrain, overall``: ``crosspoint`` is the dict
    returned by ``evaluate`` and ``terrain`` is the tuple returned by
    ``assess`` (nested key order, tuple levels, numeric types and
    rounding unchanged). ``overall`` is ``"pass"`` only when the
    crosspoint ``quality`` is ``"pass"`` and every terrain item has
    ``slope_exceed`` and ``roughness_exceed`` equal to 0; otherwise it
    is ``"fail"``.
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
