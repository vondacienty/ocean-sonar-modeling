"""Combined crosspoint, terrain and substrate report generation.

Aggregates :func:`ocean_sonar.crosspoint.evaluate`,
:func:`ocean_sonar.quality.assess` and
:func:`ocean_sonar.substrate.classify` into reports with an overall
pass/fail verdict.
"""

from __future__ import annotations

import math

from .crosspoint import evaluate
from .quality import assess
from .svp import _is_real_number

__all__ = ["generate", "summarize"]

_CROSSPOINT_KEYS = (
    "count",
    "bias",
    "rmse",
    "max_abs",
    "within_tolerance",
    "quality",
)
_TERRAIN_ITEM_KEYS = (
    "resolution",
    "total",
    "valid",
    "coverage",
    "slope_exceed",
    "roughness_exceed",
)
_SUBSTRATE_ITEM_KEYS = ("resolution", "nx", "ny", "classes", "counts")
_COUNT_KEYS = ("unknown", "mud", "sand", "gravel", "rock")
_CLASS_NAMES = _COUNT_KEYS


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


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_float(value):
    return isinstance(value, float) and not isinstance(value, bool)


def _check_keys(obj, expected, what):
    keys = list(obj)
    if len(keys) != len(expected):
        raise ValueError(f"{what} must have {len(expected)} keys")
    if keys != list(expected):
        raise TypeError(f"{what} keys must be in order {', '.join(expected)}")


def _check_crosspoint(crosspoint):
    if not isinstance(crosspoint, dict):
        raise TypeError("crosspoint must be a dict")
    _check_keys(crosspoint, _CROSSPOINT_KEYS, "crosspoint")

    if not _is_int(crosspoint["count"]):
        raise TypeError("crosspoint: count must be a non-bool int")
    if not crosspoint["count"] > 0:
        raise ValueError("crosspoint: count must be > 0")

    if not _is_float(crosspoint["bias"]):
        raise TypeError("crosspoint: bias must be a float")
    if not math.isfinite(crosspoint["bias"]):
        raise ValueError("crosspoint: bias must be finite")

    if not _is_float(crosspoint["rmse"]):
        raise TypeError("crosspoint: rmse must be a float")
    if not math.isfinite(crosspoint["rmse"]):
        raise ValueError("crosspoint: rmse must be finite")
    if crosspoint["rmse"] < 0:
        raise ValueError("crosspoint: rmse must be >= 0")

    if not _is_float(crosspoint["max_abs"]):
        raise TypeError("crosspoint: max_abs must be a float")
    if not math.isfinite(crosspoint["max_abs"]):
        raise ValueError("crosspoint: max_abs must be finite")
    if crosspoint["max_abs"] < 0:
        raise ValueError("crosspoint: max_abs must be >= 0")

    if not _is_int(crosspoint["within_tolerance"]):
        raise TypeError("crosspoint: within_tolerance must be a non-bool int")
    if not 0 <= crosspoint["within_tolerance"] <= crosspoint["count"]:
        raise ValueError("crosspoint: within_tolerance must be in [0, count]")

    quality = crosspoint["quality"]
    if not isinstance(quality, str):
        raise TypeError("crosspoint: quality must be a string")
    if quality not in ("pass", "fail"):
        raise ValueError("crosspoint: quality must be 'pass' or 'fail'")


def _check_terrain_items(terrain):
    for i, item in enumerate(terrain):
        prefix = f"terrain[{i}]: "
        if not isinstance(item, dict):
            raise TypeError(prefix + "must be a dict")
        _check_keys(item, _TERRAIN_ITEM_KEYS, f"terrain[{i}]")

        resolution = item["resolution"]
        if not _is_float(resolution):
            raise TypeError(prefix + "resolution must be a float")
        if not math.isfinite(resolution):
            raise ValueError(prefix + "resolution must be finite")
        if not resolution > 0:
            raise ValueError(prefix + "resolution must be > 0")

        total = item["total"]
        if not _is_int(total):
            raise TypeError(prefix + "total must be a non-bool int")
        if not total > 0:
            raise ValueError(prefix + "total must be > 0")

        valid = item["valid"]
        if not _is_int(valid):
            raise TypeError(prefix + "valid must be a non-bool int")
        if not 0 <= valid <= total:
            raise ValueError(prefix + "valid must be in [0, total]")

        coverage = item["coverage"]
        if not _is_float(coverage):
            raise TypeError(prefix + "coverage must be a float")
        if not math.isfinite(coverage):
            raise ValueError(prefix + "coverage must be finite")
        if not 0 <= coverage <= 1:
            raise ValueError(prefix + "coverage must be in [0, 1]")

        for name in ("slope_exceed", "roughness_exceed"):
            value = item[name]
            if not _is_int(value):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not 0 <= value <= total:
                raise ValueError(prefix + f"{name} must be in [0, total]")


def _check_substrate_items(substrate):
    for i, item in enumerate(substrate):
        prefix = f"substrate[{i}]: "
        if not isinstance(item, dict):
            raise TypeError(prefix + "must be a dict")
        _check_keys(item, _SUBSTRATE_ITEM_KEYS, f"substrate[{i}]")

        resolution = item["resolution"]
        if not _is_float(resolution):
            raise TypeError(prefix + "resolution must be a float")
        if not math.isfinite(resolution):
            raise ValueError(prefix + "resolution must be finite")
        if not resolution > 0:
            raise ValueError(prefix + "resolution must be > 0")

        for name in ("nx", "ny"):
            value = item[name]
            if not _is_int(value):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not value > 0:
                raise ValueError(prefix + f"{name} must be > 0")

        nx, ny = item["nx"], item["ny"]
        classes = item["classes"]
        if not isinstance(classes, tuple):
            raise TypeError(prefix + "classes must be a tuple")
        if len(classes) != nx * ny:
            raise ValueError(prefix + "classes must have nx * ny elements")
        for j, name in enumerate(classes):
            if not isinstance(name, str):
                raise TypeError(prefix + f"classes[{j}] must be a string")
            if name not in _CLASS_NAMES:
                raise ValueError(prefix + f"classes[{j}] is not a recognized class")

        counts = item["counts"]
        counts_what = f"substrate[{i}].counts"
        if not isinstance(counts, dict):
            raise TypeError(prefix + "counts must be a dict")
        _check_keys(counts, _COUNT_KEYS, counts_what)
        for name in _COUNT_KEYS:
            value = counts[name]
            if not _is_int(value):
                raise TypeError(prefix + f"counts.{name} must be a non-bool int")
            if value < 0:
                raise ValueError(prefix + f"counts.{name} must be >= 0")
        expected = dict.fromkeys(_COUNT_KEYS, 0)
        for name in classes:
            expected[name] += 1
        if counts != expected:
            raise ValueError(prefix + "counts must match classes")


def summarize(crosspoint, terrain, substrate):
    """Summarize crosspoint, terrain and substrate results.

    ``crosspoint`` must be the dict returned by
    :func:`ocean_sonar.crosspoint.evaluate`, with keys in the order
    ``count, bias, rmse, max_abs, within_tolerance, quality``.
    ``terrain`` and ``substrate`` must be the non-empty tuples returned
    by :func:`ocean_sonar.quality.assess` and
    :func:`ocean_sonar.substrate.classify`; they must cover the same
    number of layers and every layer's terrain ``resolution`` must be
    numerically equal to its substrate ``resolution``.

    Validation order, stopping at the first error: the crosspoint
    dict, the terrain container, the substrate container, the layer
    count, the per-layer resolutions, and then the per-item structure
    (terrain items in index order followed by substrate items).
    Container, key-order, field-type and tuple-level mismatches raise
    ``TypeError``; length, finiteness, range, consistency and
    unrecognized-class errors raise ``ValueError``. The literal class
    ``"unknown"`` is structurally valid but forces an overall
    ``"fail"``.

    Returns a dict with keys in the order
    ``crosspoint, terrain, substrate, overall``; the first three are
    the original inputs, passed through unchanged. ``overall`` is
    ``"pass"`` only when ``crosspoint["quality"] == "pass"``, every
    terrain item has ``slope_exceed`` and ``roughness_exceed`` equal
    to ``0`` and no substrate item's ``classes`` contains
    ``"unknown"``; otherwise it is ``"fail"``. Inputs are not
    modified.
    """
    _check_crosspoint(crosspoint)

    if not isinstance(terrain, tuple):
        raise TypeError("terrain must be a tuple")
    if len(terrain) == 0:
        raise ValueError("terrain must be non-empty")

    if not isinstance(substrate, tuple):
        raise TypeError("substrate must be a tuple")
    if len(substrate) == 0:
        raise ValueError("substrate must be non-empty")

    if len(terrain) != len(substrate):
        raise ValueError(
            "terrain and substrate must have the same number of layers"
        )

    for i in range(len(terrain)):
        terrain_item = terrain[i]
        substrate_item = substrate[i]
        if not isinstance(terrain_item, dict) or not isinstance(substrate_item, dict):
            continue
        if "resolution" not in terrain_item or "resolution" not in substrate_item:
            continue
        terrain_resolution = terrain_item["resolution"]
        substrate_resolution = substrate_item["resolution"]
        if not (
            _is_real_number(terrain_resolution)
            and _is_real_number(substrate_resolution)
        ):
            continue
        # Defer non-finite values to the per-item structure checks;
        # only compare well-formed resolutions here.
        if not (
            math.isfinite(terrain_resolution)
            and math.isfinite(substrate_resolution)
        ):
            continue
        if terrain_resolution != substrate_resolution:
            raise ValueError(
                f"terrain[{i}] and substrate[{i}] resolution must be equal"
            )

    _check_terrain_items(terrain)
    _check_substrate_items(substrate)

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
