"""Combined crosspoint, terrain-quality and substrate report generation.

Aggregates the dicts/tuples returned by
:func:`ocean_sonar.crosspoint.evaluate`,
:func:`ocean_sonar.quality.assess` and
:func:`ocean_sonar.substrate.classify` into reports with an overall
pass/fail verdict. :func:`generate` runs ``evaluate``/``assess`` itself,
while :func:`summarize` validates and combines their already-computed
results together with a ``classify`` result.
"""

from __future__ import annotations

import json
import math

from .crosspoint import evaluate
from .quality import assess

__all__ = ["generate", "summarize", "serialize"]

_CROSSPOINT_KEYS = (
    "count",
    "bias",
    "rmse",
    "max_abs",
    "within_tolerance",
    "quality",
)
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

    return {
        "crosspoint": crosspoint,
        "terrain": terrain,
        "substrate": substrate,
        "overall": overall,
    }


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
