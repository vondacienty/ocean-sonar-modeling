"""Plain-text rendering for aggregated batch quality summaries.

Provides :func:`render`, which validates the batch summary dict
returned by :func:`ocean_sonar.report.aggregate_dashboard_summaries`
and renders it as three plain-text lines. Only this module is added;
existing interfaces are unchanged.
"""

from __future__ import annotations

import math

__all__ = ["render"]

_BATCH_KEYS = (
    "batch_count",
    "tolerance_count",
    "pass_count",
    "fail_count",
    "first_pass_summary",
    "terrain_total",
    "terrain_valid",
    "terrain_coverage",
    "quality_score",
)


def render(summary) -> str:
    """Render a batch summary dict as plain text.

    ``summary`` must be a dict with keys exactly in the order
    ``batch_count, tolerance_count, pass_count, fail_count,
    first_pass_summary, terrain_total, terrain_valid,
    terrain_coverage, quality_score`` (indices K0..K8). Validation
    stops at the first error, in the order container → key order →
    fields in key order:

    - K0, K1, K2, K3, K5 and K6 must be non-bool ints;
    - K0 > 0, K1 > 0, K5 > 0, ``0 <= K2 <= K1``,
      ``K3 == K1 - K2`` and ``0 <= K6 <= K5``;
    - K4 must be ``None`` when K2 is 0, otherwise a non-bool int with
      ``0 <= K4 < K0``;
    - K7 and K8 must be finite floats equal respectively to
      ``round(K6 / K5, 6)`` and
      ``round(100 * (K2 / K1) * (K6 / K5), 6)``, with negative zero
      normalized to ``0.0``.

    A non-dict container, wrong key order or wrong field type raises
    ``TypeError``; every other violation raises ``ValueError``. The
    input is not modified.

    On success returns a ``str`` of three ``"\\n"``-joined lines with
    no trailing newline: a ``BATCH=`` line with K0..K4 and a
    ``TERRAIN=`` line with K5..K7, each as semicolon-joined
    ``key=value`` fields, and a ``QUALITY_SCORE=`` line with K8. Ints
    render in decimal, ``None`` renders as ``None`` and floats with
    ``format(v, ".6f")``; negative zero renders as ``0.000000``.
    """
    if not isinstance(summary, dict):
        raise TypeError("summary must be a dict")
    if list(summary.keys()) != list(_BATCH_KEYS):
        raise TypeError(
            "summary keys must be in the order "
            "batch_count, tolerance_count, pass_count, fail_count, "
            "first_pass_summary, terrain_total, terrain_valid, "
            "terrain_coverage, quality_score"
        )

    batch_count = summary["batch_count"]
    if type(batch_count) is not int:
        raise TypeError("batch_count must be a non-bool int")
    if not batch_count > 0:
        raise ValueError("batch_count must be > 0")

    tolerance_count = summary["tolerance_count"]
    if type(tolerance_count) is not int:
        raise TypeError("tolerance_count must be a non-bool int")
    if not tolerance_count > 0:
        raise ValueError("tolerance_count must be > 0")

    pass_count = summary["pass_count"]
    if type(pass_count) is not int:
        raise TypeError("pass_count must be a non-bool int")
    if not 0 <= pass_count <= tolerance_count:
        raise ValueError("pass_count must be in [0, tolerance_count]")

    fail_count = summary["fail_count"]
    if type(fail_count) is not int:
        raise TypeError("fail_count must be a non-bool int")
    if fail_count != tolerance_count - pass_count:
        raise ValueError("fail_count must equal tolerance_count - pass_count")

    first_pass_summary = summary["first_pass_summary"]
    if pass_count == 0:
        if first_pass_summary is not None:
            raise ValueError(
                "first_pass_summary must be None when pass_count is 0"
            )
    else:
        if type(first_pass_summary) is not int:
            raise TypeError(
                "first_pass_summary must be None or a non-bool int"
            )
        if not 0 <= first_pass_summary < batch_count:
            raise ValueError(
                "first_pass_summary must be in [0, batch_count)"
            )

    terrain_total = summary["terrain_total"]
    if type(terrain_total) is not int:
        raise TypeError("terrain_total must be a non-bool int")
    if not terrain_total > 0:
        raise ValueError("terrain_total must be > 0")

    terrain_valid = summary["terrain_valid"]
    if type(terrain_valid) is not int:
        raise TypeError("terrain_valid must be a non-bool int")
    if not 0 <= terrain_valid <= terrain_total:
        raise ValueError("terrain_valid must be in [0, terrain_total]")

    terrain_coverage = summary["terrain_coverage"]
    if type(terrain_coverage) is not float:
        raise TypeError("terrain_coverage must be a float")
    if not math.isfinite(terrain_coverage):
        raise ValueError("terrain_coverage must be finite")
    expected_coverage = round(terrain_valid / terrain_total, 6)
    if expected_coverage == 0:
        expected_coverage = 0.0
    if terrain_coverage != expected_coverage:
        raise ValueError(
            "terrain_coverage must equal round(terrain_valid / "
            "terrain_total, 6)"
        )

    quality_score = summary["quality_score"]
    if type(quality_score) is not float:
        raise TypeError("quality_score must be a float")
    if not math.isfinite(quality_score):
        raise ValueError("quality_score must be finite")
    expected_score = round(
        100
        * (pass_count / tolerance_count)
        * (terrain_valid / terrain_total),
        6,
    )
    if expected_score == 0:
        expected_score = 0.0
    if quality_score != expected_score:
        raise ValueError(
            "quality_score must equal round(100 * (pass_count / "
            "tolerance_count) * (terrain_valid / terrain_total), 6)"
        )

    batch_fields = ";".join(
        f"{key}={_format_value(summary[key])}" for key in _BATCH_KEYS[:5]
    )
    terrain_fields = ";".join(
        f"{key}={_format_value(summary[key])}" for key in _BATCH_KEYS[5:8]
    )

    return "\n".join(
        [
            f"BATCH={batch_fields}",
            f"TERRAIN={terrain_fields}",
            f"QUALITY_SCORE={_format_value(summary['quality_score'])}",
        ]
    )


def _format_value(value):
    if type(value) is float:
        return format(0.0 if value == 0 else value, ".6f")
    if value is None:
        return "None"
    return str(value)
