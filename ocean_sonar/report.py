"""Combined crosspoint, terrain-quality and substrate report generation.

Aggregates the dicts/tuples returned by
:func:`ocean_sonar.crosspoint.evaluate`,
:func:`ocean_sonar.quality.assess` and
:func:`ocean_sonar.substrate.classify` into reports with an overall
pass/fail verdict. :func:`generate` runs ``evaluate``/``assess`` itself,
while :func:`summarize` validates and combines their already-computed
results together with a ``classify`` result. :func:`generate_full` runs
all three of ``evaluate``/``assess``/``classify`` itself and adds a
numeric score to the combined summary. :func:`dashboard` combines
:func:`ocean_sonar.crosspoint.dashboard` with ``assess``/``classify``
and adds a per-tolerance quality tuple; :func:`dashboard_summary` wraps
:func:`dashboard` with a compact scoring summary,
:func:`serialize_dashboard_summary` computes that summary once and
encodes it as UTF-8 JSON bytes, :func:`load_dashboard_summary`
reads such a JSON document back from a file, and
:func:`render_dashboard_summary` renders the summary as plain text.
"""

from __future__ import annotations

import json
import math

from .crosspoint import dashboard as crosspoint_dashboard
from .crosspoint import evaluate
from .quality import assess
from .substrate import classify

__all__ = [
    "generate",
    "generate_full",
    "dashboard",
    "dashboard_summary",
    "serialize_dashboard_summary",
    "summarize",
    "serialize",
    "serialize_summary",
    "render",
    "render_dashboard_summary",
    "write",
    "load",
    "load_dashboard_summary",
]

_CROSSPOINT_KEYS = (
    "count",
    "bias",
    "rmse",
    "max_abs",
    "within_tolerance",
    "quality",
)
_SUMMARY_KEYS = ("crosspoint", "terrain", "substrate", "overall")
_TERRAIN_KEYS = (
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
_DASHBOARD_SUMMARY_KEYS = (
    "tolerance_count",
    "pass_count",
    "fail_count",
    "first_pass_index",
    "terrain_total",
    "terrain_valid",
    "terrain_coverage",
    "quality_score",
)


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


def _check_crosspoint(crosspoint):
    if not isinstance(crosspoint, dict):
        raise TypeError("crosspoint must be a dict")
    if list(crosspoint.keys()) != list(_CROSSPOINT_KEYS):
        raise TypeError(
            "crosspoint keys must be in the order "
            "count, bias, rmse, max_abs, within_tolerance, quality"
        )

    count = crosspoint["count"]
    if type(count) is not int:
        raise TypeError("crosspoint: count must be a non-bool int")
    if not count > 0:
        raise ValueError("crosspoint: count must be > 0")

    for name in ("bias", "rmse", "max_abs"):
        value = crosspoint[name]
        if type(value) is not float:
            raise TypeError(f"crosspoint: {name} must be a float")
        if not math.isfinite(value):
            raise ValueError(f"crosspoint: {name} must be finite")
    if not crosspoint["rmse"] >= 0:
        raise ValueError("crosspoint: rmse must be >= 0")
    if not crosspoint["max_abs"] >= 0:
        raise ValueError("crosspoint: max_abs must be >= 0")

    within_tolerance = crosspoint["within_tolerance"]
    if type(within_tolerance) is not int:
        raise TypeError("crosspoint: within_tolerance must be a non-bool int")
    if not 0 <= within_tolerance <= count:
        raise ValueError("crosspoint: within_tolerance must be in [0, count]")

    quality = crosspoint["quality"]
    if type(quality) is not str:
        raise TypeError("crosspoint: quality must be a str")
    if quality not in _QUALITY_VALUES:
        raise ValueError("crosspoint: quality must be 'pass' or 'fail'")


def _check_nonempty_tuple(value, name):
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if len(value) == 0:
        raise ValueError(f"{name} must be non-empty")


def _check_terrain_item(index, item):
    prefix = f"terrain[{index}]: "
    if not isinstance(item, dict):
        raise TypeError(prefix + "must be a dict")
    if list(item.keys()) != list(_TERRAIN_KEYS):
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


def _check_substrate_item(index, item):
    prefix = f"substrate[{index}]: "
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
        cell_prefix = f"substrate[{index}].classes[{j}]: "
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


def _check_summary(crosspoint, terrain, substrate):
    _check_crosspoint(crosspoint)
    _check_nonempty_tuple(terrain, "terrain")
    _check_nonempty_tuple(substrate, "substrate")

    if len(terrain) != len(substrate):
        raise ValueError(
            "terrain and substrate must have the same number of layers"
        )

    for i in range(len(terrain)):
        terrain_item = terrain[i]
        substrate_item = substrate[i]
        if not isinstance(terrain_item, dict):
            raise TypeError(f"terrain[{i}] must be a dict")
        if not isinstance(substrate_item, dict):
            raise TypeError(f"substrate[{i}] must be a dict")
        if "resolution" not in terrain_item:
            raise TypeError(f"terrain[{i}] missing 'resolution'")
        if "resolution" not in substrate_item:
            raise TypeError(f"substrate[{i}] missing 'resolution'")
        if terrain_item["resolution"] != substrate_item["resolution"]:
            raise ValueError(
                f"layer {i}: terrain and substrate resolution must be equal"
            )

    for i in range(len(terrain)):
        _check_terrain_item(i, terrain[i])
    for i in range(len(substrate)):
        _check_substrate_item(i, substrate[i])

    return crosspoint, terrain, substrate


def _check_summary_container(summary):
    if not isinstance(summary, dict):
        raise TypeError("summary must be a dict")
    if list(summary.keys()) != list(_SUMMARY_KEYS):
        raise TypeError(
            "summary keys must be in the order crosspoint, terrain, substrate, overall"
        )


def _overall_verdict(crosspoint, terrain, substrate):
    overall = "pass"
    if crosspoint["quality"] != "pass":
        overall = "fail"
    else:
        for item in terrain:
            if item["slope_exceed"] != 0 or item["roughness_exceed"] != 0:
                overall = "fail"
                break
        if overall == "pass":
            for item in substrate:
                if "unknown" in item["classes"]:
                    overall = "fail"
                    break
    return overall


def summarize(crosspoint, terrain, substrate):
    """Combine ``evaluate``/``assess``/``classify`` results into one report.

    ``crosspoint`` must be the dict returned by
    :func:`ocean_sonar.crosspoint.evaluate`, with keys exactly in the
    order ``count, bias, rmse, max_abs, within_tolerance, quality``.
    ``terrain`` and ``substrate`` must be the non-empty tuples returned
    by :func:`ocean_sonar.quality.assess` and
    :func:`ocean_sonar.substrate.classify`; they must contain the same
    number of layers and the per-layer ``resolution`` values must be
    numerically equal. Each terrain item must have keys in the order
    ``resolution, total, valid, coverage, slope_exceed,
    roughness_exceed`` and each substrate item ``resolution, nx, ny,
    classes, counts`` (``classes`` a tuple of known class-name strings,
    ``counts`` a dict keyed ``unknown, mud, sand, gravel, rock``).

    Validation order, stopping at the first error: ``crosspoint``
    (container, key order, then each field in key order), ``terrain``
    container, ``substrate`` container, layer-count equality,
    per-layer resolution equality, then per-item structure (terrain
    items in index order, then substrate items). Container, key-order,
    field-type and tuple-level mismatches raise ``TypeError``;
    length, finiteness, range, consistency and unknown-class errors
    raise ``ValueError``. Inputs are not modified.

    Returns a dict with keys in the order
    ``crosspoint, terrain, substrate, overall``; the first three are
    passed through unchanged. ``overall`` is ``"pass"`` only when
    ``crosspoint["quality"] == "pass"``, every terrain item has
    ``slope_exceed`` and ``roughness_exceed`` equal to ``0`` and no
    substrate item's ``classes`` contains ``"unknown"``; otherwise it
    is ``"fail"``.
    """
    crosspoint, terrain, substrate = _check_summary(crosspoint, terrain, substrate)
    overall = _overall_verdict(crosspoint, terrain, substrate)

    return {
        "crosspoint": crosspoint,
        "terrain": terrain,
        "substrate": substrate,
        "overall": overall,
    }


def generate_full(crossings, layers, tolerance=0.5, slope_limit=5.0, roughness_limit=1.0):
    """Generate the combined report with a numeric score.

    Calls :func:`evaluate`, :func:`assess` and :func:`classify` strictly
    in that order, exactly once each and with no interleaving, then
    passes the three results unchanged to :func:`summarize`
    (``evaluate`` validates ``crossings`` then ``tolerance``;
    ``assess`` and ``classify`` each validate ``layers`` then
    ``slope_limit`` then ``roughness_limit``; ``summarize`` applies its
    own contract). The first-error order is therefore crossings →
    tolerance → layers → slope_limit → roughness_limit → the
    :func:`summarize` validation order, and every exception from any of
    the four functions short-circuits and is propagated unchanged.
    Inputs are not modified.

    With ``T`` the sum of the terrain ``total`` values, ``V`` the sum of
    the terrain ``valid`` values, ``C`` equal to
    ``within_tolerance / count`` from the crosspoint result, ``G`` the
    number of layers whose terrain item has ``slope_exceed`` and
    ``roughness_exceed`` both equal to ``0`` and whose substrate
    ``classes`` contain no ``"unknown"``, and ``L`` equal to ``G``
    divided by the number of layers, the score is
    ``round(100 * (V / T) * C * L, 6)`` as a float with negative zero
    normalized to ``0.0``.

    Returns a dict with keys in the order ``crosspoint, terrain,
    substrate, overall, score``; the first four are the objects from
    the :func:`summarize` result (identities preserved) and ``score``
    is the value described above.
    """
    crosspoint = evaluate(crossings, tolerance)
    terrain = assess(layers, slope_limit, roughness_limit)
    substrate = classify(layers, slope_limit, roughness_limit)
    summary = summarize(crosspoint, terrain, substrate)

    total = 0
    valid = 0
    good = 0
    for i in range(len(terrain)):
        item = terrain[i]
        total += item["total"]
        valid += item["valid"]
        if (
            item["slope_exceed"] == 0
            and item["roughness_exceed"] == 0
            and "unknown" not in substrate[i]["classes"]
        ):
            good += 1

    score = round(
        100
        * (valid / total)
        * (crosspoint["within_tolerance"] / crosspoint["count"])
        * (good / len(terrain)),
        6,
    )
    if score == 0:
        score = 0.0

    return {
        "crosspoint": summary["crosspoint"],
        "terrain": summary["terrain"],
        "substrate": summary["substrate"],
        "overall": summary["overall"],
        "score": score,
    }


def dashboard(crossings, tolerances, layers, slope_limit=5.0, roughness_limit=1.0):
    """Combine the crosspoint dashboard with terrain and substrate results.

    Calls :func:`ocean_sonar.crosspoint.dashboard` with ``crossings``
    and ``tolerances``, then :func:`ocean_sonar.quality.assess` and
    :func:`ocean_sonar.substrate.classify`, each with ``layers``,
    ``slope_limit`` and ``roughness_limit``, strictly in that order,
    exactly once each. No other combining function is called and the
    inputs are neither modified nor reordered; every exception from any
    of the three functions short-circuits and is propagated unchanged.
    The first-error order is therefore the ``crosspoint.dashboard``
    validation order (the full ``crossings`` validation, then
    ``tolerances``), then ``layers`` → ``slope_limit`` →
    ``roughness_limit`` as validated by ``assess``, then the same order
    again as validated by ``classify``.

    Returns a dict with keys in the order
    ``crosspoint, terrain, substrate, quality``; ``crosspoint`` is the
    tuple returned by :func:`~ocean_sonar.crosspoint.dashboard`,
    ``terrain`` the tuple returned by
    :func:`~ocean_sonar.quality.assess` and ``substrate`` the tuple
    returned by :func:`~ocean_sonar.substrate.classify` (identities,
    nested key order, tuple levels, numeric types and rounding all
    unchanged).

    With ``R`` the first element of the ``crosspoint`` tuple (the
    :func:`~ocean_sonar.crosspoint.audit` report tuple, one entry per
    tolerance in input order), ``quality`` is a tuple of ``str`` of
    length ``len(R)`` in ``tolerances`` order. Its ``i``-th item is
    ``"pass"`` only when ``R[i]["quality"] == "pass"``, every terrain
    item has ``slope_exceed`` and ``roughness_exceed`` equal to ``0``
    and no substrate item's ``classes`` contains ``"unknown"``;
    otherwise it is ``"fail"``.
    """
    crosspoint = crosspoint_dashboard(crossings, tolerances)
    terrain = assess(layers, slope_limit, roughness_limit)
    substrate = classify(layers, slope_limit, roughness_limit)

    layers_ok = True
    for item in terrain:
        if item["slope_exceed"] != 0 or item["roughness_exceed"] != 0:
            layers_ok = False
            break
    if layers_ok:
        for item in substrate:
            if "unknown" in item["classes"]:
                layers_ok = False
                break

    reports = crosspoint[0]
    quality = tuple(
        "pass" if item["quality"] == "pass" and layers_ok else "fail"
        for item in reports
    )

    return {
        "crosspoint": crosspoint,
        "terrain": terrain,
        "substrate": substrate,
        "quality": quality,
    }


def dashboard_summary(
    crossings, tolerances, layers, slope_limit=5.0, roughness_limit=1.0
):
    """Return the :func:`dashboard` result together with a compact summary.

    Calls :func:`dashboard` exactly once with the given arguments (so
    its validation, first-error order, exception messages and index
    prefixes all apply unchanged) and propagates every exception
    unchanged; inputs are not modified.

    Returns a dict with keys in the order ``dashboard, summary``;
    ``dashboard`` is the dict returned by :func:`dashboard` (the same
    object, identity preserved). With ``Q`` the dashboard ``quality``
    tuple and ``T`` the dashboard ``terrain`` tuple, ``summary`` is a
    dict with keys in the order ``tolerance_count, pass_count,
    fail_count, first_pass_index, terrain_total, terrain_valid,
    terrain_coverage, quality_score``:

    - ``tolerance_count`` is ``len(Q)``;
    - ``pass_count`` is the number of ``"pass"`` entries in ``Q``;
    - ``fail_count`` is ``tolerance_count`` minus ``pass_count``;
    - ``first_pass_index`` is the index of the first ``"pass"`` entry
      in ``Q``, or ``None`` if there is none;
    - ``terrain_total`` is the sum of ``T[i]["total"]``;
    - ``terrain_valid`` is the sum of ``T[i]["valid"]``;
    - ``terrain_coverage`` is ``round(terrain_valid / terrain_total,
      6)``;
    - ``quality_score`` is
      ``round(100 * (pass_count / tolerance_count) *
      (terrain_valid / terrain_total), 6)``.

    Counts and indices are non-bool ints (the index may also be
    ``None``); both ratios are non-bool floats with negative zero
    normalized to ``0.0``.
    """
    dashboard_result = dashboard(
        crossings, tolerances, layers, slope_limit, roughness_limit
    )

    quality = dashboard_result["quality"]
    terrain = dashboard_result["terrain"]

    tolerance_count = len(quality)
    pass_count = 0
    first_pass_index = None
    for i, verdict in enumerate(quality):
        if verdict == "pass":
            pass_count += 1
            if first_pass_index is None:
                first_pass_index = i
    fail_count = tolerance_count - pass_count

    terrain_total = 0
    terrain_valid = 0
    for item in terrain:
        terrain_total += item["total"]
        terrain_valid += item["valid"]

    terrain_coverage = round(terrain_valid / terrain_total, 6)
    if terrain_coverage == 0:
        terrain_coverage = 0.0

    quality_score = round(
        100 * (pass_count / tolerance_count) * (terrain_valid / terrain_total),
        6,
    )
    if quality_score == 0:
        quality_score = 0.0

    return {
        "dashboard": dashboard_result,
        "summary": {
            "tolerance_count": tolerance_count,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "first_pass_index": first_pass_index,
            "terrain_total": terrain_total,
            "terrain_valid": terrain_valid,
            "terrain_coverage": terrain_coverage,
            "quality_score": quality_score,
        },
    }


def serialize_dashboard_summary(
    crossings, tolerances, layers, slope_limit=5.0, roughness_limit=1.0
) -> bytes:
    """Compute the dashboard summary once and encode it as UTF-8 JSON bytes.

    Calls :func:`dashboard_summary` exactly once with the given
    arguments, so its validation order, first-error order, exception
    messages and index prefixes all apply unchanged; every exception
    from that call is propagated unchanged and the inputs are neither
    modified nor reordered. Only the ``"summary"`` dict of the returned
    value is encoded (the ``"dashboard"`` entry is not).

    The encoded object has keys exactly in the order
    ``tolerance_count, pass_count, fail_count, first_pass_index,
    terrain_total, terrain_valid, terrain_coverage, quality_score``:
    the first five count fields are non-bool ints — ``m`` tolerance
    count, ``p`` pass count, ``m - p`` fail count, and ``n`` and ``v``
    the respective sums of the terrain ``total`` and ``valid`` values
    —, ``first_pass_index`` is a non-bool int or ``None`` when no
    quality entry is ``"pass"``, ``terrain_coverage`` is
    ``round(v / n, 6)`` and ``quality_score`` is
    ``round(100 * (p / m) * (v / n), 6)``, both non-bool floats with
    negative zero normalized to ``0.0``. All values, types, rounding
    and key order are exactly those produced by
    :func:`dashboard_summary`.

    The summary is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation and
    no trailing newline. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    result = dashboard_summary(
        crossings, tolerances, layers, slope_limit, roughness_limit
    )
    return _dump_dashboard_summary(result["summary"])


def _dump_dashboard_summary(summary):
    try:
        text = json.dumps(
            summary,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"dashboard summary: could not be serialized to JSON: {exc}"
        ) from exc


def _check_dashboard_summary(summary):
    if not isinstance(summary, dict):
        raise TypeError("dashboard summary must be a dict")
    if list(summary.keys()) != list(_DASHBOARD_SUMMARY_KEYS):
        raise TypeError(
            "dashboard summary keys must be in the order "
            "tolerance_count, pass_count, fail_count, first_pass_index, "
            "terrain_total, terrain_valid, terrain_coverage, quality_score"
        )

    prefix = "dashboard summary: "

    tolerance_count = summary["tolerance_count"]
    if type(tolerance_count) is not int:
        raise TypeError(prefix + "tolerance_count must be a non-bool int")
    if not tolerance_count > 0:
        raise ValueError(prefix + "tolerance_count must be > 0")

    pass_count = summary["pass_count"]
    if type(pass_count) is not int:
        raise TypeError(prefix + "pass_count must be a non-bool int")
    if not 0 <= pass_count <= tolerance_count:
        raise ValueError(prefix + "pass_count must be in [0, tolerance_count]")

    fail_count = summary["fail_count"]
    if type(fail_count) is not int:
        raise TypeError(prefix + "fail_count must be a non-bool int")
    if fail_count != tolerance_count - pass_count:
        raise ValueError(
            prefix + "fail_count must equal tolerance_count - pass_count"
        )

    first_pass_index = summary["first_pass_index"]
    if first_pass_index is not None:
        if type(first_pass_index) is not int:
            raise TypeError(
                prefix + "first_pass_index must be None or a non-bool int"
            )
        if not 0 <= first_pass_index < tolerance_count:
            raise ValueError(
                prefix + "first_pass_index must be in [0, tolerance_count)"
            )

    terrain_total = summary["terrain_total"]
    if type(terrain_total) is not int:
        raise TypeError(prefix + "terrain_total must be a non-bool int")
    if not terrain_total > 0:
        raise ValueError(prefix + "terrain_total must be > 0")

    terrain_valid = summary["terrain_valid"]
    if type(terrain_valid) is not int:
        raise TypeError(prefix + "terrain_valid must be a non-bool int")
    if not 0 <= terrain_valid <= terrain_total:
        raise ValueError(prefix + "terrain_valid must be in [0, terrain_total]")

    terrain_coverage = summary["terrain_coverage"]
    if type(terrain_coverage) is not float:
        raise TypeError(prefix + "terrain_coverage must be a float")
    if not math.isfinite(terrain_coverage):
        raise ValueError(prefix + "terrain_coverage must be finite")
    expected_coverage = round(terrain_valid / terrain_total, 6)
    if expected_coverage == 0:
        expected_coverage = 0.0
    if terrain_coverage != expected_coverage:
        raise ValueError(
            prefix + "terrain_coverage must equal "
            "round(terrain_valid / terrain_total, 6)"
        )

    quality_score = summary["quality_score"]
    if type(quality_score) is not float:
        raise TypeError(prefix + "quality_score must be a float")
    if not math.isfinite(quality_score):
        raise ValueError(prefix + "quality_score must be finite")
    expected_score = round(
        100 * (pass_count / tolerance_count) * (terrain_valid / terrain_total),
        6,
    )
    if expected_score == 0:
        expected_score = 0.0
    if quality_score != expected_score:
        raise ValueError(
            prefix + "quality_score must equal round(100 * (pass_count / "
            "tolerance_count) * (terrain_valid / terrain_total), 6)"
        )


def _format_dashboard_value(value):
    if type(value) is float:
        return format(0.0 if value == 0 else value, ".6f")
    if value is None:
        return "None"
    return str(value)


def render_dashboard_summary(summary) -> str:
    """Render a :func:`dashboard_summary` ``summary`` dict as plain text.

    ``summary`` must be the ``"summary"`` dict returned by
    :func:`dashboard_summary` (or one accepted by
    :func:`load_dashboard_summary`), with keys exactly in the order
    ``tolerance_count, pass_count, fail_count, first_pass_index,
    terrain_total, terrain_valid, terrain_coverage, quality_score``.
    It is validated with the same checks as
    :func:`load_dashboard_summary`: a non-dict container, wrong key
    order or a field of the wrong type raises ``TypeError``; writing
    ``m`` for ``tolerance_count``, ``p`` for ``pass_count``, ``n`` for
    ``terrain_total`` and ``v`` for ``terrain_valid``, any violation of
    ``m > 0``, ``0 <= p <= m``, ``fail_count == m - p``, ``n > 0``,
    ``0 <= v <= n``, ``first_pass_index`` in ``[0, m)``,
    ``terrain_coverage == round(v / n, 6)`` or ``quality_score ==
    round(100 * (p / m) * (v / n), 6)`` raises ``ValueError``. The
    input is not modified.

    On success returns a ``str`` of three ``"\\n"``-joined lines with
    no trailing newline: a ``TOLERANCE=`` line with the first four
    fields (``tolerance_count, pass_count, fail_count,
    first_pass_index``) as semicolon-joined ``key=value`` fields; a
    ``TERRAIN=`` line with the next three fields (``terrain_total,
    terrain_valid, terrain_coverage``) in the same form; and a
    ``QUALITY_SCORE=<quality_score>`` line. Ints render in decimal,
    ``None`` renders as ``None`` and floats with
    ``format(v, ".6f")``; negative zero renders as ``0.000000``.
    """
    _check_dashboard_summary(summary)

    tolerance_fields = ";".join(
        f"{key}={_format_dashboard_value(summary[key])}"
        for key in _DASHBOARD_SUMMARY_KEYS[:4]
    )
    terrain_fields = ";".join(
        f"{key}={_format_dashboard_value(summary[key])}"
        for key in _DASHBOARD_SUMMARY_KEYS[4:7]
    )

    return "\n".join(
        [
            f"TOLERANCE={tolerance_fields}",
            f"TERRAIN={terrain_fields}",
            f"QUALITY_SCORE={_format_dashboard_value(summary['quality_score'])}",
        ]
    )


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


def serialize(crosspoint):
    """Serialize a crosspoint result dict to UTF-8 JSON bytes.

    ``crosspoint`` must be the dict returned by
    :func:`ocean_sonar.crosspoint.evaluate`, with keys exactly in the
    order ``count, bias, rmse, max_abs, within_tolerance, quality``:
    ``count`` and ``within_tolerance`` non-bool ints with
    ``count > 0`` and ``0 <= within_tolerance <= count``; ``bias``,
    ``rmse`` and ``max_abs`` finite non-bool floats with ``rmse`` and
    ``max_abs`` non-negative; ``quality`` the string ``"pass"`` or
    ``"fail"``.

    Validation order, stopping at the first error: container, key
    order, then each field in key order. Container, key-order and
    field-type errors raise ``TypeError``; finiteness, range and
    enum errors raise ``ValueError``. Validation exceptions are
    propagated unchanged and the input is not modified.

    On success the crosspoint structure is encoded as UTF-8 JSON with
    the key order preserved, ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation and
    no trailing newline. Floats are first rounded with
    ``round(float(v), 6)`` and negative zero is normalized to ``0.0``;
    tuples are recursively converted to arrays. Any JSON or UTF-8
    encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    _check_crosspoint(crosspoint)
    try:
        text = json.dumps(
            _to_jsonable(crosspoint),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"crosspoint: could not be serialized to JSON: {exc}"
        ) from exc


def serialize_summary(summary):
    """Serialize a :func:`summarize` result dict to UTF-8 JSON bytes.

    ``summary`` must be the dict returned by :func:`summarize`, with
    keys exactly in the order ``crosspoint, terrain, substrate,
    overall``. ``crosspoint`` is validated exactly as in
    :func:`serialize`; ``terrain`` and ``substrate`` must be the same
    non-empty, equally-sized layer tuples accepted by
    :func:`summarize`, with the same per-layer key order, field types,
    ranges and consistency constraints (including equal per-layer
    ``resolution`` values and ``counts`` matching ``classes``).
    ``overall`` must be the string ``"pass"`` or ``"fail"`` and is
    recomputed from the other three entries: ``"pass"`` only when
    ``crosspoint["quality"] == "pass"``, every terrain item has
    ``slope_exceed`` and ``roughness_exceed`` equal to ``0`` and no
    substrate item's ``classes`` contains ``"unknown"``.

    Validation order, stopping at the first error: container, key
    order, ``crosspoint``, the terrain layer items, the substrate
    layer items (the tuple/container, layer-count and per-layer
    resolution gates keep their :func:`summarize` order within those
    stages), then ``overall``. Container, key-order, field-type and
    tuple-level mismatches raise ``TypeError``; finiteness, range,
    enum, layer-count and consistency errors (including an ``overall``
    value that disagrees with the recomputed verdict) raise
    ``ValueError``. The input is not modified.

    On success the summary is encoded as UTF-8 JSON with the key order
    preserved, ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no indentation and no trailing newline.
    Floats are first rounded with ``round(float(v), 6)`` and negative
    zero is normalized to ``0.0``; tuples are recursively converted to
    arrays. Any JSON or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    _check_summary_container(summary)

    crosspoint, terrain, substrate = _check_summary(
        summary["crosspoint"], summary["terrain"], summary["substrate"]
    )

    overall = summary["overall"]
    if type(overall) is not str:
        raise TypeError("overall must be a str")
    if overall not in _QUALITY_VALUES:
        raise ValueError("overall must be 'pass' or 'fail'")

    recomputed = _overall_verdict(crosspoint, terrain, substrate)
    if overall != recomputed:
        raise ValueError(
            "overall is inconsistent with crosspoint, terrain and substrate"
        )

    document = {
        "crosspoint": crosspoint,
        "terrain": terrain,
        "substrate": substrate,
        "overall": recomputed,
    }
    try:
        text = json.dumps(
            _to_jsonable(document),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"summary: could not be serialized to JSON: {exc}") from exc


def _format_number(value):
    if isinstance(value, float):
        return format(value, ".6f")
    return str(value)


def render(summary):
    """Render a :func:`summarize` result dict as a plain-text report.

    ``summary`` is first validated with :func:`serialize_summary`, so
    it must satisfy that function's full contract; every validation
    exception is propagated unchanged and the input is not modified.

    On success returns a ``str`` of ``"\\n"``-joined lines with no
    trailing newline: an ``OVERALL=<overall>`` line; a
    ``CROSSPOINT=`` line with ``count, bias, rmse, max_abs,
    within_tolerance, quality`` as semicolon-joined ``key=value``
    fields; one ``TERRAIN[i]=`` line per terrain layer (``i`` from 0)
    with the fields ``resolution, total, valid, coverage,
    slope_exceed, roughness_exceed``; and one ``SUBSTRATE[i]=`` line
    per substrate layer with the fields ``resolution, nx, ny, classes,
    counts``. ``classes`` is the class names joined by commas with no
    spaces; ``counts`` lists ``unknown, mud, sand, gravel, rock`` in
    that order joined by commas. Layers and fields keep input order;
    floats are formatted with ``format(v, ".6f")`` and ints in
    decimal.
    """
    serialize_summary(summary)

    crosspoint = summary["crosspoint"]
    terrain = summary["terrain"]
    substrate = summary["substrate"]

    lines = [f"OVERALL={summary['overall']}"]

    cp_fields = ";".join(
        f"{key}={_format_number(crosspoint[key])}" for key in _CROSSPOINT_KEYS
    )
    lines.append(f"CROSSPOINT={cp_fields}")

    for i, item in enumerate(terrain):
        fields = ";".join(
            f"{key}={_format_number(item[key])}" for key in _TERRAIN_KEYS
        )
        lines.append(f"TERRAIN[{i}]={fields}")

    for i, item in enumerate(substrate):
        fields = ";".join(
            (
                f"resolution={format(item['resolution'], '.6f')}",
                f"nx={item['nx']}",
                f"ny={item['ny']}",
                f"classes={','.join(item['classes'])}",
                "counts="
                + ",".join(str(item["counts"][name]) for name in _COUNT_KEYS),
            )
        )
        lines.append(f"SUBSTRATE[{i}]={fields}")

    return "\n".join(lines)


def write(summary, path):
    """Serialize a :func:`summarize` result and overwrite ``path`` with it.

    The bytes written are exactly those returned by
    :func:`serialize_summary` (compact UTF-8 JSON, key order preserved,
    no trailing newline); ``summary`` must therefore satisfy the full
    :func:`serialize_summary` contract and is not modified.

    Validation order, stopping at the first error: ``summary`` is
    serialized first, so every :func:`serialize_summary` exception is
    propagated unchanged; only then is ``path`` validated — a non-str
    ``path`` raises ``TypeError`` and an empty ``str`` raises
    ``ValueError``.

    On success the bytes are written by overwriting ``path`` opened in
    binary mode (``"wb"``), with no added newline. A missing parent
    directory raises ``FileNotFoundError``, an existing directory at
    ``path`` raises ``IsADirectoryError`` and every other ``OSError``
    is propagated unchanged.

    Returns the JSON document as ``bytes``.
    """
    data = serialize_summary(summary)

    if not isinstance(path, str):
        raise TypeError("path must be a str")
    if path == "":
        raise ValueError("path must not be empty")

    with open(path, "wb") as handle:
        handle.write(data)

    return data


def _from_jsonable(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(float(value), 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, list):
        return tuple(_from_jsonable(item) for item in value)
    if isinstance(value, dict):
        return {key: _from_jsonable(item) for key, item in value.items()}
    return value


def _reject_json_constant(name):
    raise ValueError(f"invalid JSON constant {name!r}")


def load(path):
    """Load a :func:`write`-produced JSON summary from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_summary` for the same value: compact UTF-8 JSON
    with no BOM and no trailing newline. A BOM, a trailing newline, a
    UTF-8 decoding failure or a JSON parsing failure raises
    ``ValueError``. The decoded value must satisfy the full
    :func:`serialize_summary` contract — top-level key order
    ``crosspoint, terrain, substrate, overall`` and the nested key
    orders, non-empty equally-sized layer arrays, equal per-layer
    ``resolution`` values, ``classes`` containing only
    ``unknown/mud/sand/gravel/rock``, ``counts`` matching ``classes``
    and an ``overall`` consistent with the recomputed verdict — and
    the file bytes must equal the canonical re-serialization of the
    decoded value byte for byte; any key-order, type, range,
    consistency or normalization-byte mismatch raises ``ValueError``.

    JSON arrays are recursively converted to tuples (including
    ``classes``) and floats are rounded with ``round(float(v), 6)``
    with negative zero normalized to ``0.0``, mirroring
    :func:`serialize_summary`.

    Returns the summary as a dict with keys in the order
    ``crosspoint, terrain, substrate, overall``.
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

    summary = _from_jsonable(parsed)
    try:
        canonical = serialize_summary(summary)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"file does not contain a valid summary: {exc}") from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize_summary output"
        )

    return summary


def load_dashboard_summary(path) -> dict:
    """Load a :func:`serialize_dashboard_summary`-produced JSON summary.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_dashboard_summary` for the same value: compact
    UTF-8 JSON with no BOM and no trailing newline. A BOM, a trailing
    newline, a UTF-8 decoding failure or a JSON parsing failure raises
    ``ValueError``; the ``NaN``/``Infinity`` constants and any other
    non-finite token are rejected.

    The decoded value must be a JSON object with top-level keys
    exactly in the order ``tolerance_count, pass_count, fail_count,
    first_pass_index, terrain_total, terrain_valid, terrain_coverage,
    quality_score``; writing ``m`` for ``tolerance_count``, ``p`` for
    ``pass_count``, ``n`` for ``terrain_total`` and ``v`` for
    ``terrain_valid``, every field except ``first_pass_index`` that is
    a count must be a non-bool int, with ``m > 0``, ``0 <= p <= m``,
    ``fail_count == m - p``, ``n > 0`` and ``0 <= v <= n``;
    ``first_pass_index`` must be ``None`` or a non-bool int in
    ``[0, m)``; and ``terrain_coverage`` and ``quality_score`` must be
    finite non-bool floats equal respectively to ``round(v / n, 6)``
    and ``round(100 * (p / m) * (v / n), 6)``, with negative zero
    normalized to ``0.0``. Any key-order, type, range, relation, parse
    or canonical-byte mismatch raises ``ValueError``.

    Returns the summary as a dict with the keys in the order above;
    the file is never modified.
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

    summary = _from_jsonable(parsed)
    try:
        _check_dashboard_summary(summary)
        canonical = _dump_dashboard_summary(summary)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid dashboard summary: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_dashboard_summary output"
        )

    return summary
