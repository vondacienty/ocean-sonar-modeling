"""Seabed substrate classification from slope/roughness analysis grids.

Each layer pairs a regular per-cell ``(slope, roughness)`` analysis grid
(as produced by :func:`ocean_sonar.terrain.analyze`) with its cell size
and classifies every cell into a substrate class by thresholding slope
and roughness.
"""

from __future__ import annotations

import json
import math
import os
import tempfile

from .svp import _is_real_number

__all__ = [
    "aggregate",
    "aggregate_report_trend",
    "batch",
    "classify",
    "dump_aggregate",
    "export",
    "export_aggregate",
    "load",
    "load_aggregate",
    "load_aggregate_report",
    "load_aggregate_report_trend",
    "render",
    "render_aggregate",
    "serialize_aggregate_report",
    "serialize_aggregate_report_trend",
]

_CLASSES = ("mud", "sand", "gravel", "rock")


def _round6(value):
    result = round(float(value), 6)
    if result == 0:
        result = 0.0
    return result


def _check_limit(name, value):
    if not _is_real_number(value):
        raise TypeError(f"{name} must be a non-bool int or float")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not value > 0:
        raise ValueError(f"{name} must be > 0")


def classify(layers, slope_limit=5.0, roughness_limit=1.0):
    """Classify analysis grids into seabed substrate classes.

    ``layers`` is a non-empty list/tuple of four-element list/tuples
    ``(r, nx, ny, analysis)``: ``r`` is the cell size, a finite non-bool
    int/float with ``r > 0``; ``nx``/``ny`` are non-bool positive ints;
    ``analysis`` is a list/tuple of length ``nx * ny`` ordered by ``y``
    then ``x``. Each cell is a two-element list/tuple ``(slope,
    roughness)``; ``(None, None)``, ``(None, q)`` and ``(p, q)`` are
    legal (``None`` marks unknown), ``(p, None)`` with non-``None``
    ``p`` is not. Non-``None`` values must be finite non-bool
    int/float ``>= 0``. ``slope_limit``/``roughness_limit`` are finite
    non-bool int/float ``> 0``.

    A cell with ``slope`` equal to ``None`` is ``unknown``. Otherwise
    the bit pair ``(slope > slope_limit, roughness > roughness_limit)``
    selects the class: ``00`` mud, ``01`` sand, ``10`` gravel,
    ``11`` rock.

    Validation order: ``layers`` container, non-emptiness, then per
    layer (container, 4 elements, ``r``, ``nx``, ``ny``, ``analysis``
    container/length), then per cell (container, 2 elements, ``slope``,
    ``roughness``), then ``slope_limit``, then ``roughness_limit``;
    checking stops at the first error. Type mismatches (including bool)
    raise ``TypeError``, all other constraint errors raise
    ``ValueError``. Layer errors are prefixed with ``"layers[i]: "``
    and cell errors with ``"layers[i].analysis[j]: "``.

    Returns a tuple with one dict per layer, keys in order
    ``resolution``, ``nx``, ``ny``, ``classes``, ``counts``.
    ``resolution`` is ``round(float(r), 6)`` (negative zero normalized
    to ``0.0``); ``classes`` is a tuple of class name strings in grid
    order (``y`` then ``x``); ``counts`` maps ``unknown``, ``mud``,
    ``sand``, ``gravel``, ``rock`` (in that key order) to int counts.
    Inputs are not modified.
    """
    if not isinstance(layers, (list, tuple)):
        raise TypeError("layers must be a list or tuple")
    if len(layers) == 0:
        raise ValueError("layers must be non-empty")

    for i in range(len(layers)):
        prefix = f"layers[{i}]: "
        layer = layers[i]
        if not isinstance(layer, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(layer) != 4:
            raise ValueError(prefix + "must have 4 elements")
        r, nx, ny, analysis = layer
        if not _is_real_number(r):
            raise TypeError(prefix + "r must be a non-bool int or float")
        if not math.isfinite(r):
            raise ValueError(prefix + "r must be finite")
        if not r > 0:
            raise ValueError(prefix + "r must be > 0")
        for name, value in (("nx", nx), ("ny", ny)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(prefix + f"{name} must be a non-bool int")
            if not value > 0:
                raise ValueError(prefix + f"{name} must be > 0")
        if not isinstance(analysis, (list, tuple)):
            raise TypeError(prefix + "analysis must be a list or tuple")
        if len(analysis) != nx * ny:
            raise ValueError(prefix + "analysis must have nx * ny elements")
        for j in range(len(analysis)):
            cell_prefix = f"layers[{i}].analysis[{j}]: "
            cell = analysis[j]
            if not isinstance(cell, (list, tuple)):
                raise TypeError(cell_prefix + "must be a list or tuple")
            if len(cell) != 2:
                raise ValueError(cell_prefix + "must have 2 elements")
            slope, roughness = cell
            if slope is not None:
                if not _is_real_number(slope):
                    raise TypeError(
                        cell_prefix + "slope must be a non-bool int or float"
                    )
                if not math.isfinite(slope):
                    raise ValueError(cell_prefix + "slope must be finite")
                if not slope >= 0:
                    raise ValueError(cell_prefix + "slope must be >= 0")
            if roughness is None:
                if slope is not None:
                    raise ValueError(
                        cell_prefix
                        + "roughness must not be None when slope is not None"
                    )
            else:
                if not _is_real_number(roughness):
                    raise TypeError(
                        cell_prefix + "roughness must be a non-bool int or float"
                    )
                if not math.isfinite(roughness):
                    raise ValueError(cell_prefix + "roughness must be finite")
                if not roughness >= 0:
                    raise ValueError(cell_prefix + "roughness must be >= 0")

    _check_limit("slope_limit", slope_limit)
    _check_limit("roughness_limit", roughness_limit)

    result = []
    for layer in layers:
        r, nx, ny, analysis = layer
        classes = []
        counts = {"unknown": 0, "mud": 0, "sand": 0, "gravel": 0, "rock": 0}
        for cell in analysis:
            slope, roughness = cell
            if slope is None:
                name = "unknown"
            else:
                index = (
                    2 * (slope > slope_limit) + (roughness > roughness_limit)
                )
                name = _CLASSES[index]
            classes.append(name)
            counts[name] += 1
        result.append(
            {
                "resolution": _round6(r),
                "nx": nx,
                "ny": ny,
                "classes": tuple(classes),
                "counts": counts,
            }
        )
    return tuple(result)


def _check_grid_value(prefix, name, value):
    if not _is_real_number(value):
        raise TypeError(prefix + f"{name} must be a non-bool int or float")
    if not math.isfinite(value):
        raise ValueError(prefix + f"{name} must be finite")
    if not value >= 0:
        raise ValueError(prefix + f"{name} must be >= 0")


def batch(analysis, intensities) -> bytes:
    """Classify analysis grids against acoustic intensities as JSON bytes.

    ``analysis`` is a non-empty list/tuple of two-element list/tuples
    ``(p, q)``: when ``p`` is ``None``, ``q`` is ``None`` or a finite
    non-bool int/float ``>= 0``; otherwise ``p`` and ``q`` are both
    finite non-bool ints/floats ``>= 0``. ``intensities`` is a
    list/tuple of the same length whose items are ``None`` or finite
    non-bool ints/floats in ``[0, 1]``.

    Validation order: the ``analysis`` container, non-emptiness, then
    per grid (container, 2 elements, ``p``, ``q``), then the
    ``intensities`` container, its length and finally each item in
    order; checking stops at the first error. Type mismatches
    (including bool) raise ``TypeError``, all other constraint errors
    raise ``ValueError``. Grid errors are prefixed with
    ``"analysis[i]: "`` and item errors with ``"intensities[i]: "``.

    A grid whose ``p`` is ``None`` or whose intensity is ``None``
    yields ``["unknown", 0.0]``. Otherwise, with
    ``g = p > 5 or q > 1`` and ``a = intensity >= 0.5``, the bit pair
    ``(g, a)`` selects the class: ``00`` mud, ``01`` sand, ``10``
    gravel, ``11`` rock, with confidence ``1.0``.

    The returned document has top-level keys exactly in the order
    ``results, summary``. ``results`` is an array in input order of
    ``[class, confidence]`` arrays. ``summary`` has keys exactly in the
    order ``count, unknown, quality``: ``count`` and ``unknown`` are
    ints and ``quality`` is ``"pass"`` only when ``unknown == 0``, and
    ``"fail"`` otherwise.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, as in ``terrain.batch``. Any JSON or
    UTF-8 encoding failure raises ``ValueError``. Inputs are not
    modified.

    Returns the JSON document as ``bytes``.
    """
    if not isinstance(analysis, (list, tuple)):
        raise TypeError("analysis must be a list or tuple")
    if len(analysis) == 0:
        raise ValueError("analysis must be non-empty")

    for i in range(len(analysis)):
        prefix = f"analysis[{i}]: "
        cell = analysis[i]
        if not isinstance(cell, (list, tuple)):
            raise TypeError(prefix + "must be a list or tuple")
        if len(cell) != 2:
            raise ValueError(prefix + "must have 2 elements")
        p, q = cell
        if p is None:
            if q is not None:
                _check_grid_value(prefix, "q", q)
        else:
            _check_grid_value(prefix, "p", p)
            _check_grid_value(prefix, "q", q)

    if not isinstance(intensities, (list, tuple)):
        raise TypeError("intensities must be a list or tuple")
    if len(intensities) != len(analysis):
        raise ValueError("intensities must have the same length as analysis")

    for i in range(len(intensities)):
        prefix = f"intensities[{i}]: "
        intensity = intensities[i]
        if intensity is None:
            continue
        if not _is_real_number(intensity):
            raise TypeError(prefix + "must be a non-bool int or float")
        if not math.isfinite(intensity):
            raise ValueError(prefix + "must be finite")
        if not 0 <= intensity <= 1:
            raise ValueError(prefix + "must be in [0, 1]")

    results = []
    unknown = 0
    for i in range(len(analysis)):
        p, q = analysis[i]
        intensity = intensities[i]
        if p is None or intensity is None:
            results.append(["unknown", 0.0])
            unknown += 1
        else:
            g = p > 5 or q > 1
            a = intensity >= 0.5
            results.append([_CLASSES[2 * g + a], 1.0])

    document = {
        "results": results,
        "summary": {
            "count": int(len(analysis)),
            "unknown": int(unknown),
            "quality": "pass" if unknown == 0 else "fail",
        },
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"batch: could not be serialized to JSON: {exc}") from exc


_BATCH_KEYS = ("results", "summary")
_BATCH_RESULT_CLASSES = ("unknown", "mud", "sand", "gravel", "rock")
_BATCH_SUMMARY_KEYS = ("count", "unknown", "quality")


def _reject_json_constant(name):
    raise ValueError(f"invalid JSON constant {name!r}")


def _reject_duplicate_json_pairs(pairs):
    """``object_pairs_hook`` that rejects duplicate JSON object keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _dump_batch_document(document):
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"batch: could not be serialized to JSON: {exc}"
        ) from exc


def _check_batch_document(document):
    prefix = "batch: "
    if not isinstance(document, dict):
        raise TypeError("batch must be a dict")
    if list(document.keys()) != list(_BATCH_KEYS):
        raise TypeError("batch keys must be in the order results, summary")

    results = document["results"]
    if not isinstance(results, list):
        raise TypeError(prefix + "results must be a list")
    if len(results) == 0:
        raise ValueError(prefix + "results must be non-empty")

    unknown = 0
    for i in range(len(results)):
        item = results[i]
        item_prefix = f"{prefix}results[{i}]: "
        if not isinstance(item, list):
            raise TypeError(item_prefix + "must be a list")
        if len(item) != 2:
            raise ValueError(item_prefix + "must have 2 elements")
        name, confidence = item
        if type(name) is not str:
            raise TypeError(item_prefix + "class must be a str")
        if name not in _BATCH_RESULT_CLASSES:
            raise ValueError(
                item_prefix
                + "class must be one of unknown, mud, sand, gravel, rock"
            )
        if type(confidence) is not float:
            raise TypeError(item_prefix + "confidence must be a float")
        if not math.isfinite(confidence):
            raise ValueError(item_prefix + "confidence must be finite")
        if confidence == 0 and math.copysign(1.0, confidence) < 0:
            raise ValueError(item_prefix + "confidence must not be negative zero")
        expected = 0.0 if name == "unknown" else 1.0
        if confidence != expected:
            raise ValueError(
                item_prefix
                + "confidence must be 0.0 for unknown and 1.0 otherwise"
            )
        if name == "unknown":
            unknown += 1

    summary = document["summary"]
    summary_prefix = prefix + "summary: "
    if not isinstance(summary, dict):
        raise TypeError(summary_prefix + "must be a dict")
    if list(summary.keys()) != list(_BATCH_SUMMARY_KEYS):
        raise TypeError(
            summary_prefix + "keys must be in the order count, unknown, quality"
        )

    count = summary["count"]
    if type(count) is not int:
        raise TypeError(summary_prefix + "count must be a non-bool int")
    if count != len(results):
        raise ValueError(summary_prefix + "count must equal the number of results")

    unknown_count = summary["unknown"]
    if type(unknown_count) is not int:
        raise TypeError(summary_prefix + "unknown must be a non-bool int")
    if unknown_count != unknown:
        raise ValueError(
            summary_prefix + "unknown must equal the number of unknown results"
        )

    quality = summary["quality"]
    if type(quality) is not str:
        raise TypeError(summary_prefix + "quality must be a str")
    expected_quality = "pass" if unknown == 0 else "fail"
    if quality != expected_quality:
        raise ValueError(
            summary_prefix
            + "quality must be 'pass' if and only if unknown is 0"
        )


def load(path) -> dict:
    """Load a :func:`batch`-produced JSON document from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by :func:`batch` for the
    same value: compact UTF-8 JSON (``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``) with no BOM and no
    trailing newline. A BOM, a trailing newline, a UTF-8 decoding
    failure or a JSON parsing failure raises ``ValueError``; the
    ``NaN``/``Infinity`` constants, any other non-finite token and
    duplicate object keys are rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``results, summary``. ``results`` must be a non-empty
    array of two-element arrays ``[class, confidence]``: ``class`` must
    be one of ``unknown``, ``mud``, ``sand``, ``gravel``, ``rock`` and
    ``confidence`` must be a finite float, exactly ``0.0`` for
    ``unknown`` and exactly ``1.0`` for every other class (negative
    zero is rejected). ``summary`` must have keys exactly in the order
    ``count, unknown, quality``: ``count`` and ``unknown`` must be
    non-bool ints with ``count`` equal to the number of results and
    ``unknown`` equal to the number of ``unknown`` results, and
    ``quality`` must be ``"pass"`` if and only if ``unknown`` is ``0``
    (``"fail"`` otherwise). The file bytes must also equal the
    canonical re-serialization of the decoded value byte for byte; any
    key-order, type, enum, relation, parse or canonical-byte mismatch
    raises ``ValueError``.

    Returns the document as a dict with the keys in the order above;
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
        parsed = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        _check_batch_document(parsed)
        canonical = _dump_batch_document(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid batch: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError("file bytes do not match the canonical batch output")

    return parsed


def aggregate(paths) -> dict:
    """Aggregate several :func:`load`-loaded substrate batches into one report.

    ``paths`` must be a list/tuple of at least two non-empty ``str``
    paths. Validation order: the ``paths`` container, its length, then
    each item in order; checking stops at the first error. Type
    mismatches raise ``TypeError``, all other constraint errors raise
    ``ValueError``. Item errors are prefixed with ``"paths[i]: "``.

    After validation, :func:`load` is called exactly once per path, in
    input order; its exceptions are propagated unchanged. Neither
    ``paths`` nor any file is modified.

    Returns a dict with keys exactly in the order ``batches, summary``.
    ``batches`` is a tuple of the dicts returned by :func:`load`, in
    input order. ``summary`` has keys exactly in the order
    ``batch_count, result_count, unknown, counts, unknown_ratio,
    worst_batch_index, quality``:

    - ``batch_count``: the number of batches (int).
    - ``result_count``: the total number of results across all batches
      (int).
    - ``unknown``: the total number of ``unknown`` results (int).
    - ``counts``: a dict mapping ``unknown``, ``mud``, ``sand``,
      ``gravel``, ``rock`` (in that key order) to the total int count
      of each class across all batches.
    - ``unknown_ratio``: ``round(float(unknown / result_count), 6)``
      as a float, with negative zero normalized to ``0.0``.
    - ``worst_batch_index``: the index (int) of the batch maximizing
      ``(batch_unknown / batch_result_count, batch_unknown, -index)``
      computed from unrounded values, so ties in ratio and unknown
      count resolve to the earliest batch.
    - ``quality``: ``"pass"`` when every batch's ``summary.quality``
      is ``"pass"``, ``"fail"`` otherwise.
    """
    if not isinstance(paths, (list, tuple)):
        raise TypeError("paths must be a list or tuple")
    if len(paths) < 2:
        raise ValueError("paths must have at least 2 items")

    for i in range(len(paths)):
        prefix = f"paths[{i}]: "
        path = paths[i]
        if not isinstance(path, str):
            raise TypeError(prefix + "must be a str")
        if path == "":
            raise ValueError(prefix + "must not be empty")

    batches = tuple(load(path) for path in paths)

    counts = {"unknown": 0, "mud": 0, "sand": 0, "gravel": 0, "rock": 0}
    result_count = 0
    worst_key = None
    worst_batch_index = 0
    quality = "pass"
    for i, document in enumerate(batches):
        batch_unknown = 0
        batch_result_count = 0
        for item in document["results"]:
            name = item[0]
            counts[name] += 1
            batch_result_count += 1
            if name == "unknown":
                batch_unknown += 1
        result_count += batch_result_count
        key = (batch_unknown / batch_result_count, batch_unknown, -i)
        if worst_key is None or key > worst_key:
            worst_key = key
            worst_batch_index = i
        if document["summary"]["quality"] != "pass":
            quality = "fail"

    unknown = counts["unknown"]
    summary = {
        "batch_count": int(len(batches)),
        "result_count": int(result_count),
        "unknown": int(unknown),
        "counts": counts,
        "unknown_ratio": _round6(unknown / result_count),
        "worst_batch_index": int(worst_batch_index),
        "quality": quality,
    }
    return {"batches": batches, "summary": summary}


_AGGREGATE_KEYS = ("batches", "summary")
_AGGREGATE_SUMMARY_KEYS = (
    "batch_count",
    "result_count",
    "unknown",
    "counts",
    "unknown_ratio",
    "worst_batch_index",
    "quality",
)
_AGGREGATE_COUNT_KEYS = ("unknown", "mud", "sand", "gravel", "rock")


def _aggregate_to_jsonable(value):
    """Recursively convert tuples to JSON arrays, preserving everything else."""
    if isinstance(value, (list, tuple)):
        return [_aggregate_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _aggregate_to_jsonable(item) for key, item in value.items()}
    return value


def _dump_aggregate_document(document):
    try:
        text = json.dumps(
            _aggregate_to_jsonable(document),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"aggregate: could not be serialized to JSON: {exc}"
        ) from exc


def dump_aggregate(paths) -> bytes:
    """Serialize an :func:`aggregate` result as JSON bytes.

    Calls :func:`aggregate` exactly once with ``paths`` — and no other
    combining function — so its validation, first-error order,
    exception messages and ``paths[i]: `` index prefixes all apply
    unchanged; every exception from that call is propagated unchanged
    and neither ``paths`` nor any file is modified.

    With ``A`` the dict returned by :func:`aggregate`, the encoded
    object is ``A`` itself: keys stay in the order ``batches, summary``
    and every value is kept unchanged; the only structural conversion
    is that tuples (the top-level ``batches`` tuple) are recursively
    encoded as JSON arrays, while every other container remains an
    object or array.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline, exactly as in :func:`batch`; the
    ``unknown_ratio`` float produced by :func:`aggregate` is already
    rounded with ``round(float(v), 6)`` with negative zero normalized
    to ``0.0``. Any JSON or UTF-8 encoding failure raises
    ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    return _dump_aggregate_document(aggregate(paths))


def _check_aggregate_document(document):
    prefix = "aggregate: "
    if not isinstance(document, dict):
        raise TypeError("aggregate must be a dict")
    if list(document.keys()) != list(_AGGREGATE_KEYS):
        raise TypeError("aggregate keys must be in the order batches, summary")

    batches = document["batches"]
    if not isinstance(batches, list):
        raise TypeError(prefix + "batches must be a list")
    if len(batches) < 2:
        raise ValueError(prefix + "batches must have at least 2 items")

    counts = {"unknown": 0, "mud": 0, "sand": 0, "gravel": 0, "rock": 0}
    result_count = 0
    worst_key = None
    worst_batch_index = 0
    quality = "pass"
    for i in range(len(batches)):
        item_prefix = f"{prefix}batches[{i}]: "
        try:
            _check_batch_document(batches[i])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                item_prefix + f"must be a valid batch: {exc}"
            ) from exc
        batch = batches[i]
        batch_unknown = 0
        batch_result_count = 0
        for item in batch["results"]:
            name = item[0]
            counts[name] += 1
            batch_result_count += 1
            if name == "unknown":
                batch_unknown += 1
        result_count += batch_result_count
        key = (batch_unknown / batch_result_count, batch_unknown, -i)
        if worst_key is None or key > worst_key:
            worst_key = key
            worst_batch_index = i
        if batch["summary"]["quality"] != "pass":
            quality = "fail"

    unknown = counts["unknown"]
    unknown_ratio = _round6(unknown / result_count)

    summary = document["summary"]
    summary_prefix = prefix + "summary: "
    if not isinstance(summary, dict):
        raise TypeError(summary_prefix + "must be a dict")
    if list(summary.keys()) != list(_AGGREGATE_SUMMARY_KEYS):
        raise TypeError(
            summary_prefix
            + "keys must be in the order batch_count, result_count, unknown, "
            "counts, unknown_ratio, worst_batch_index, quality"
        )

    batch_count = summary["batch_count"]
    if type(batch_count) is not int:
        raise TypeError(summary_prefix + "batch_count must be a non-bool int")
    if batch_count != len(batches):
        raise ValueError(
            summary_prefix + "batch_count must equal the number of batches"
        )

    total = summary["result_count"]
    if type(total) is not int:
        raise TypeError(summary_prefix + "result_count must be a non-bool int")
    if total != result_count:
        raise ValueError(
            summary_prefix
            + "result_count must equal the total number of results"
        )

    unknown_total = summary["unknown"]
    if type(unknown_total) is not int:
        raise TypeError(summary_prefix + "unknown must be a non-bool int")
    if unknown_total != unknown:
        raise ValueError(
            summary_prefix
            + "unknown must equal the total number of unknown results"
        )

    summary_counts = summary["counts"]
    counts_prefix = summary_prefix + "counts: "
    if not isinstance(summary_counts, dict):
        raise TypeError(counts_prefix + "must be a dict")
    if list(summary_counts.keys()) != list(_AGGREGATE_COUNT_KEYS):
        raise TypeError(
            counts_prefix
            + "keys must be in the order unknown, mud, sand, gravel, rock"
        )
    for name in _AGGREGATE_COUNT_KEYS:
        value = summary_counts[name]
        if type(value) is not int:
            raise TypeError(counts_prefix + f"{name} must be a non-bool int")
        if value != counts[name]:
            raise ValueError(
                counts_prefix
                + f"{name} must equal the total number of {name} results"
            )

    ratio = summary["unknown_ratio"]
    if type(ratio) is not float:
        raise TypeError(summary_prefix + "unknown_ratio must be a float")
    if not math.isfinite(ratio):
        raise ValueError(summary_prefix + "unknown_ratio must be finite")
    if ratio == 0 and math.copysign(1.0, ratio) < 0:
        raise ValueError(summary_prefix + "unknown_ratio must not be negative zero")
    if ratio != unknown_ratio:
        raise ValueError(
            summary_prefix
            + "unknown_ratio must equal round(float(unknown / result_count), 6)"
        )

    worst = summary["worst_batch_index"]
    if type(worst) is not int:
        raise TypeError(summary_prefix + "worst_batch_index must be a non-bool int")
    if worst != worst_batch_index:
        raise ValueError(
            summary_prefix
            + "worst_batch_index must be the index of the batch maximizing "
            "(batch_unknown / batch_result_count, batch_unknown, -index)"
        )

    summary_quality = summary["quality"]
    if type(summary_quality) is not str:
        raise TypeError(summary_prefix + "quality must be a str")
    if summary_quality != quality:
        raise ValueError(
            summary_prefix
            + "quality must be 'pass' if and only if every batch quality "
            "is 'pass'"
        )


def load_aggregate(path) -> dict:
    """Load a :func:`dump_aggregate`-produced JSON aggregate from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by :func:`dump_aggregate`
    for the same value: compact UTF-8 JSON (``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``) with no BOM and no
    trailing newline. A BOM, a trailing newline, a UTF-8 decoding
    failure or a JSON parsing failure raises ``ValueError``; the
    ``NaN``/``Infinity`` constants, any other non-finite token and
    duplicate object keys are rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``batches, summary``. ``batches`` must be an array of
    at least two items, each satisfying the full :func:`load` return
    structure (keys ``results, summary`` with all of its per-result and
    per-summary rules). ``summary`` must have keys exactly in the order
    ``batch_count, result_count, unknown, counts, unknown_ratio,
    worst_batch_index, quality`` and, recomputed from the batches and
    their ``results`` in their original order: ``batch_count`` must
    equal the number of batches, ``result_count`` the total number of
    results, ``unknown`` the total number of ``unknown`` results,
    ``counts`` a dict with keys exactly in the order ``unknown, mud,
    sand, gravel, rock`` mapping to the total non-bool int count of
    each class, ``unknown_ratio`` the float
    ``round(float(unknown / result_count), 6)`` (negative zero
    normalized to ``0.0``), ``worst_batch_index`` the non-bool int
    index of the batch maximizing ``(batch_unknown /
    batch_result_count, batch_unknown, -index)`` computed from
    unrounded values, and ``quality`` ``"pass"`` if and only if every
    batch's ``summary.quality`` is ``"pass"``. The file bytes must also
    equal the canonical re-serialization of the decoded value byte for
    byte; any key-order, type, relation, parse or canonical-byte
    mismatch raises ``ValueError``.

    Returns the aggregate as a dict with the keys in the order above;
    only the top-level ``batches`` array is restored to a tuple, every
    other container stays a dict or list. The file is never modified.
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
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        _check_aggregate_document(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid aggregate: {exc}"
        ) from exc

    document = {
        "batches": tuple(parsed["batches"]),
        "summary": parsed["summary"],
    }
    canonical = _dump_aggregate_document(document)
    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical dump_aggregate output"
        )

    return document


def _resolved_export_path(path):
    """Normalized absolute path with symlinks resolved, for non-existing files."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _is_same_file(output, path):
    """Whether ``output`` and ``path`` name the same file.

    Existing files are compared with ``os.path.samefile`` so soft and hard
    links are recognized; when either side does not exist, the normalized
    ``realpath`` strings are compared instead.
    """
    if os.path.exists(output) and os.path.exists(path):
        return os.path.samefile(output, path)
    return _resolved_export_path(output) == _resolved_export_path(path)


def _atomic_write_bytes(output, data):
    """Write ``data`` to ``output`` via a fsynced temp file and ``os.replace``.

    The temporary file lives in ``output``'s directory. On any failure before
    the replacement the temporary file is removed and an existing ``output``
    is left untouched.
    """
    directory = os.path.dirname(os.path.abspath(output)) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix="." + os.path.basename(output) + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, output)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def export(path, output) -> bytes:
    """Load a substrate batch and atomically write its canonical bytes to disk.

    Calls :func:`load` exactly once with ``path`` — before any other work
    and no second time — so its validation, first-error order, exceptions
    (propagated unchanged), canonical-byte checks and file non-modification
    contract all apply here as well; in particular a bad ``path`` value is
    reported before ``output`` is inspected.

    With ``D`` the dict returned by :func:`load`, the bytes ``B`` are the
    canonical :func:`batch` re-serialization of ``D`` (its original key
    order and the same UTF-8 JSON settings: ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no BOM and no trailing
    newline). ``output`` is then validated: it must be a non-empty ``str``
    (a non-str raises ``TypeError`` and an empty ``str`` raises
    ``ValueError``), in that order.

    ``output`` must not name the same file as ``path``: when both sides
    exist they are compared with ``os.path.samefile`` so soft and hard
    links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in ``output``'s
    directory, ``B`` is written to it in binary mode, ``flush()`` and
    ``os.fsync()`` are called and the temporary file then atomically
    replaces ``output`` via ``os.replace``. Any failure before the
    replacement removes the temporary file and leaves an existing
    ``output`` byte for byte unchanged; ``OSError`` is propagated
    unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    document = load(path)
    data = _dump_batch_document(document)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    if _is_same_file(output, path):
        raise ValueError(
            f"output must not be the same file as an input: "
            f"{output!r} and {path!r}"
        )
    _atomic_write_bytes(output, data)
    return data


def _format_rendered_value(value):
    """Format one value for :func:`render`."""
    if isinstance(value, float):
        return format(0.0 if value == 0 else value, ".6f")
    if isinstance(value, int):
        return str(value)
    return value


def render(path) -> str:
    """Render a :func:`load`-loaded substrate batch as one header plus result lines.

    Calls :func:`load` exactly once with ``path`` — and no other loading or
    combining function — so its validation, exceptions (propagated
    unchanged), canonical-byte checks and file non-modification contract
    all apply here as well: a non-``str`` path raises ``TypeError``, an
    empty ``str`` raises ``ValueError``, a missing file raises
    ``FileNotFoundError``, a directory raises ``IsADirectoryError``, every
    other ``OSError`` is propagated unchanged and any parse, structure or
    canonical-byte violation raises ``ValueError``.

    With ``D`` the dict returned by :func:`load`, returns lines joined by
    ``"\\n"`` with no trailing newline. The first line is::

        SUBSTRATE=<count>,<unknown>,<quality>

    with the three values taken from ``D["summary"]`` in its key order
    (``count``, ``unknown``, ``quality``), followed by one line per result
    in the original order of ``D["results"]``::

        RESULT[i]=<class>,<confidence>

    where ``i`` is the decimal zero-based result index and the two values
    are the ``[class, confidence]`` pair copied directly from ``D``.
    Values are taken with no recomputation or re-sorting: ints are
    formatted in decimal, strings are copied as-is and floats use
    ``format(v, ".6f")`` (negative zero rendered as ``"0.000000"``).
    """
    document = load(path)
    summary = document["summary"]
    lines = [
        "SUBSTRATE="
        + ",".join(
            (
                _format_rendered_value(summary["count"]),
                _format_rendered_value(summary["unknown"]),
                _format_rendered_value(summary["quality"]),
            )
        )
    ]
    for i, item in enumerate(document["results"]):
        lines.append(
            f"RESULT[{i}]="
            + ",".join(_format_rendered_value(value) for value in item)
        )
    return "\n".join(lines)


def render_aggregate(path) -> str:
    """Render a :func:`load_aggregate`-loaded substrate aggregate as two lines.

    Calls :func:`load_aggregate` exactly once with ``path`` — and no other
    loading or combining function — so its validation, exceptions
    (propagated unchanged), canonical-byte checks and file
    non-modification contract all apply here as well: a non-``str`` path
    raises ``TypeError``, an empty ``str`` raises ``ValueError``, a
    missing file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError``, every other ``OSError`` is propagated
    unchanged and any parse, structure or canonical-byte violation
    raises ``ValueError``.

    With ``A`` the dict returned by :func:`load_aggregate`, returns two
    lines joined by ``"\\n"`` with no trailing newline. The first line
    is::

        AGGREGATE=<batch_count>,<result_count>,<unknown>,<unknown_ratio>,<quality>

    with the five values taken from ``A["summary"]`` (``batch_count``,
    ``result_count``, ``unknown``, ``unknown_ratio``, ``quality``). The
    second line is::

        WORST=<index>,<count>,<unknown>,<quality>

    where ``index`` is ``A["summary"]["worst_batch_index"]`` and
    ``count``, ``unknown`` and ``quality`` are taken from the
    ``summary`` of ``A["batches"][index]``. Values are taken with no
    recomputation or re-sorting: ints are formatted in decimal, strings
    are copied as-is and floats use ``format(v, ".6f")`` (negative zero
    rendered as ``"0.000000"``).
    """
    document = load_aggregate(path)
    summary = document["summary"]
    worst = document["batches"][summary["worst_batch_index"]]["summary"]
    lines = [
        "AGGREGATE="
        + ",".join(
            (
                _format_rendered_value(summary["batch_count"]),
                _format_rendered_value(summary["result_count"]),
                _format_rendered_value(summary["unknown"]),
                _format_rendered_value(summary["unknown_ratio"]),
                _format_rendered_value(summary["quality"]),
            )
        ),
        "WORST="
        + ",".join(
            (
                _format_rendered_value(summary["worst_batch_index"]),
                _format_rendered_value(worst["count"]),
                _format_rendered_value(worst["unknown"]),
                _format_rendered_value(worst["quality"]),
            )
        ),
    ]
    return "\n".join(lines)


def serialize_aggregate_report(path) -> bytes:
    """Serialize a :func:`load_aggregate`-loaded aggregate as a report in bytes.

    Calls :func:`load_aggregate` exactly once with ``path`` — and no other
    loading or combining function — so its validation, first-error order,
    exceptions (propagated unchanged), canonical-byte checks and file
    non-modification contract all apply here as well: a non-``str`` path
    raises ``TypeError``, an empty ``str`` raises ``ValueError``, a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError``, every other ``OSError`` is propagated unchanged
    and any parse, structure or canonical-byte violation raises
    ``ValueError``. The file is not modified.

    With ``A`` the dict returned by :func:`load_aggregate`, the encoded
    object has top-level keys exactly in the order ``schema_version,
    source, summary, worst, quality``:

    - ``schema_version``: the non-bool int ``1``.
    - ``source``: a dict with keys exactly in the order ``path, kind`` —
      ``path`` is the original ``path`` argument and ``kind`` is the
      fixed string ``"substrate_aggregate"``.
    - ``summary``: ``A["summary"]`` itself, not copied, recomputed or
      reordered.
    - ``worst``: with ``i = A["summary"]["worst_batch_index"]``, a dict
      with keys exactly in the order ``index, count, unknown, quality``
      whose values are ``i`` and the ``count``, ``unknown`` and
      ``quality`` of ``A["batches"][i]["summary"]``.
    - ``quality``: ``A["summary"]["quality"]``.

    No other keys are added and neither ``A`` nor the input is modified.

    The object is encoded as UTF-8 JSON exactly as in
    :func:`dump_aggregate`: tuples are recursively encoded as JSON
    arrays, floats keep their ``round(float(v), 6)`` six-decimal rounding
    with negative zero normalized to ``0.0``, and the settings are
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, with no indentation, no BOM and no trailing
    newline. Any JSON or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    document = load_aggregate(path)
    summary = document["summary"]
    index = summary["worst_batch_index"]
    worst = document["batches"][index]["summary"]
    report = {
        "schema_version": 1,
        "source": {"path": path, "kind": "substrate_aggregate"},
        "summary": summary,
        "worst": {
            "index": index,
            "count": worst["count"],
            "unknown": worst["unknown"],
            "quality": worst["quality"],
        },
        "quality": summary["quality"],
    }
    return _dump_aggregate_document(report)


_AGGREGATE_REPORT_KEYS = ("schema_version", "source", "summary", "worst", "quality")
_AGGREGATE_REPORT_SOURCE_KEYS = ("path", "kind")
_AGGREGATE_REPORT_WORST_KEYS = ("index", "count", "unknown", "quality")


def _check_aggregate_report(report):
    """Validate a decoded substrate aggregate report; return its normalized dict."""
    prefix = "aggregate report: "
    if not isinstance(report, dict):
        raise TypeError("aggregate report must be a dict")
    if list(report.keys()) != list(_AGGREGATE_REPORT_KEYS):
        raise TypeError(
            "aggregate report keys must be in the order "
            "schema_version, source, summary, worst, quality"
        )

    schema_version = report["schema_version"]
    if type(schema_version) is not int:
        raise TypeError(prefix + "schema_version must be a non-bool int")
    if schema_version != 1:
        raise ValueError(prefix + "schema_version must be 1")

    source = report["source"]
    source_prefix = prefix + "source: "
    if not isinstance(source, dict):
        raise TypeError(source_prefix + "must be an object")
    if list(source.keys()) != list(_AGGREGATE_REPORT_SOURCE_KEYS):
        raise TypeError(source_prefix + "keys must be in the order path, kind")
    source_path = source["path"]
    if type(source_path) is not str:
        raise TypeError(source_prefix + "path must be a str")
    if source_path == "":
        raise ValueError(source_prefix + "path must not be empty")
    kind = source["kind"]
    if type(kind) is not str:
        raise TypeError(source_prefix + "kind must be a str")
    if kind != "substrate_aggregate":
        raise ValueError(source_prefix + "kind must be 'substrate_aggregate'")

    summary = report["summary"]
    summary_prefix = prefix + "summary: "
    if not isinstance(summary, dict):
        raise TypeError(summary_prefix + "must be a dict")
    if list(summary.keys()) != list(_AGGREGATE_SUMMARY_KEYS):
        raise TypeError(
            summary_prefix
            + "keys must be in the order batch_count, result_count, unknown, "
            "counts, unknown_ratio, worst_batch_index, quality"
        )

    batch_count = summary["batch_count"]
    if type(batch_count) is not int:
        raise TypeError(summary_prefix + "batch_count must be a non-bool int")
    if batch_count < 2:
        raise ValueError(summary_prefix + "batch_count must be >= 2")

    result_count = summary["result_count"]
    if type(result_count) is not int:
        raise TypeError(summary_prefix + "result_count must be a non-bool int")
    if result_count < batch_count:
        raise ValueError(
            summary_prefix
            + "result_count must be >= batch_count"
        )

    unknown_total = summary["unknown"]
    if type(unknown_total) is not int:
        raise TypeError(summary_prefix + "unknown must be a non-bool int")
    if not 0 <= unknown_total <= result_count:
        raise ValueError(summary_prefix + "unknown must be in [0, result_count]")

    summary_counts = summary["counts"]
    counts_prefix = summary_prefix + "counts: "
    if not isinstance(summary_counts, dict):
        raise TypeError(counts_prefix + "must be a dict")
    if list(summary_counts.keys()) != list(_AGGREGATE_COUNT_KEYS):
        raise TypeError(
            counts_prefix
            + "keys must be in the order unknown, mud, sand, gravel, rock"
        )
    normalized_counts = {}
    for name in _AGGREGATE_COUNT_KEYS:
        value = summary_counts[name]
        if type(value) is not int:
            raise TypeError(counts_prefix + f"{name} must be a non-bool int")
        if value < 0:
            raise ValueError(counts_prefix + f"{name} must be >= 0")
        normalized_counts[name] = value
    if normalized_counts["unknown"] != unknown_total:
        raise ValueError(
            counts_prefix + "unknown must equal summary.unknown"
        )
    if sum(normalized_counts.values()) != result_count:
        raise ValueError(
            counts_prefix + "counts must sum to result_count"
        )

    ratio = summary["unknown_ratio"]
    if type(ratio) is not float:
        raise TypeError(summary_prefix + "unknown_ratio must be a float")
    if not math.isfinite(ratio):
        raise ValueError(summary_prefix + "unknown_ratio must be finite")
    if ratio == 0 and math.copysign(1.0, ratio) < 0:
        raise ValueError(summary_prefix + "unknown_ratio must not be negative zero")
    if ratio != _round6(unknown_total / result_count):
        raise ValueError(
            summary_prefix
            + "unknown_ratio must equal round(float(unknown / result_count), 6)"
        )

    worst_batch_index = summary["worst_batch_index"]
    if type(worst_batch_index) is not int:
        raise TypeError(summary_prefix + "worst_batch_index must be a non-bool int")
    if not 0 <= worst_batch_index < batch_count:
        raise ValueError(
            summary_prefix + "worst_batch_index must be in [0, batch_count)"
        )

    summary_quality = summary["quality"]
    if type(summary_quality) is not str:
        raise TypeError(summary_prefix + "quality must be a str")
    expected_summary_quality = "pass" if unknown_total == 0 else "fail"
    if summary_quality != expected_summary_quality:
        raise ValueError(
            summary_prefix
            + "quality must be 'pass' if and only if unknown is 0"
        )

    worst = report["worst"]
    worst_prefix = prefix + "worst: "
    if not isinstance(worst, dict):
        raise TypeError(worst_prefix + "must be an object")
    if list(worst.keys()) != list(_AGGREGATE_REPORT_WORST_KEYS):
        raise TypeError(
            worst_prefix + "keys must be in the order index, count, unknown, quality"
        )

    index = worst["index"]
    if type(index) is not int:
        raise TypeError(worst_prefix + "index must be a non-bool int")
    if index != worst_batch_index:
        raise ValueError(
            worst_prefix + "index must equal summary.worst_batch_index"
        )

    count = worst["count"]
    if type(count) is not int:
        raise TypeError(worst_prefix + "count must be a non-bool int")
    if count <= 0:
        raise ValueError(worst_prefix + "count must be > 0")

    worst_unknown = worst["unknown"]
    if type(worst_unknown) is not int:
        raise TypeError(worst_prefix + "unknown must be a non-bool int")
    if not 0 <= worst_unknown <= count:
        raise ValueError(worst_prefix + "unknown must be in [0, count]")

    worst_quality = worst["quality"]
    if type(worst_quality) is not str:
        raise TypeError(worst_prefix + "quality must be a str")
    if worst_quality not in ("pass", "fail"):
        raise ValueError(worst_prefix + "quality must be 'pass' or 'fail'")
    expected_worst_quality = "pass" if worst_unknown == 0 else "fail"
    if worst_quality != expected_worst_quality:
        raise ValueError(
            worst_prefix + "quality must be 'pass' if and only if unknown is 0"
        )

    quality = report["quality"]
    if type(quality) is not str:
        raise TypeError(prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    if quality != summary_quality:
        raise ValueError(prefix + "quality must equal summary.quality")

    return {
        "schema_version": int(schema_version),
        "source": {"path": source_path, "kind": kind},
        "summary": {
            "batch_count": int(batch_count),
            "result_count": int(result_count),
            "unknown": int(unknown_total),
            "counts": normalized_counts,
            "unknown_ratio": ratio,
            "worst_batch_index": int(worst_batch_index),
            "quality": summary_quality,
        },
        "worst": {
            "index": int(index),
            "count": int(count),
            "unknown": int(worst_unknown),
            "quality": worst_quality,
        },
        "quality": quality,
    }


def load_aggregate_report(path) -> dict:
    """Load a :func:`serialize_aggregate_report`-produced JSON report from ``path``.

    ``path`` must be a non-empty ``str``: a non-str raises
    ``TypeError`` and an empty ``str`` raises ``ValueError``. The file
    is opened in binary mode (``"rb"``) and read in full; a missing
    file raises ``FileNotFoundError``, a directory raises
    ``IsADirectoryError`` and every other ``OSError`` is propagated
    unchanged. The file is not modified.

    The bytes must be exactly those produced by
    :func:`serialize_aggregate_report` for the same value: compact
    UTF-8 JSON (``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``) with no BOM and no trailing newline. A BOM, a
    trailing newline, a UTF-8 decoding failure or a JSON parsing
    failure raises ``ValueError``; the ``NaN``/``Infinity`` constants,
    any other non-finite token and duplicate object keys are rejected.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``schema_version, source, summary, worst, quality`` —
    duplicated, missing or extra keys are rejected.

    ``schema_version`` must be the non-bool int ``1``. ``source`` must
    be an object with keys exactly in the order ``path, kind``:
    ``path`` a non-empty ``str`` and ``kind`` the fixed string
    ``"substrate_aggregate"``.

    ``summary`` must satisfy the same key order, types, ranges, counts,
    ratio and quality relations as the ``summary`` object returned by
    :func:`load_aggregate`: keys exactly in the order
    ``batch_count, result_count, unknown, counts, unknown_ratio,
    worst_batch_index, quality``; ``batch_count`` a non-bool int
    ``>= 2``; ``result_count`` a non-bool int ``>= batch_count``;
    ``unknown`` a non-bool int in ``[0, result_count]``; ``counts`` an
    object with keys exactly in the order ``unknown, mud, sand,
    gravel, rock`` of non-bool ints ``>= 0`` whose ``unknown`` value
    equals ``summary.unknown`` and whose values sum to
    ``result_count``; ``unknown_ratio`` a finite float equal to
    ``round(float(unknown / result_count), 6)`` with negative zero
    forbidden; ``worst_batch_index`` a non-bool int in
    ``[0, batch_count)``; and ``quality`` ``"pass"`` if and only if
    ``unknown`` is ``0``.

    ``worst`` must be an object with keys exactly in the order
    ``index, count, unknown, quality``: ``index``, ``count`` and
    ``unknown`` must be non-bool ints with ``index`` equal to
    ``summary.worst_batch_index``, ``count > 0`` and
    ``0 <= unknown <= count``; ``quality`` must be ``"pass"`` or
    ``"fail"`` and ``"pass"`` if and only if ``unknown`` is ``0``. The
    top-level ``quality`` must equal ``summary.quality``. Every float
    must be finite, equal to ``round(float(v), 6)`` and must not be
    negative zero. The file bytes must also equal the canonical
    re-serialization of the decoded value byte for byte; any
    key-order, type, enum, range, relation, parse or canonical-byte
    mismatch raises ``ValueError``.

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
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        result = _check_aggregate_report(parsed)
        canonical = _dump_aggregate_document(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid aggregate report: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical serialize_aggregate_report output"
        )

    return result


def aggregate_report_trend(paths) -> dict:
    """Compare successive :func:`load_aggregate_report` snapshots along one path set.

    ``paths`` must be a list/tuple of at least two items; each item,
    checked in index order, must be a non-empty ``str``. Validation
    order (first error wins): the ``paths`` container, its length, then
    each item in index order (type, then emptiness). A non-list/tuple
    container or a non-str item raises ``TypeError``; fewer than two
    items or an empty ``str`` raises ``ValueError``. Item errors are
    prefixed with ``"paths[i]: "``.

    :func:`load_aggregate_report` is then called exactly once per path,
    in input order; any exception it raises is propagated unchanged.
    Inputs and the loaded files are not modified.

    Every loaded report's ``summary.batch_count`` and
    ``summary.result_count`` must equal those of the first report;
    otherwise a ``ValueError`` is raised.

    For each snapshot pair ``i = 1..n-1`` the unrounded deltas are
    ``du = unknown_i - unknown_(i-1)`` and
    ``dr = unknown_ratio_i - unknown_ratio_(i-1)``, taken from the
    reports' ``summary`` values; a change is regressed when ``du > 0``,
    ``dr > 0`` or the summary quality changes from ``"pass"`` to
    ``"fail"``. With ``n`` the number of reports, ``K = n - 1`` is the
    number of changes and ``E`` the number of regressed changes. The
    worst change ``w`` minimizes the *unrounded* tuple
    ``(-dr, -du, i)`` lexicographically. Changes are not sorted,
    deduplicated or augmented, and no loaded value is recomputed.

    Returns a dict with keys in the order
    ``count, changes, regressed, unknown_delta, unknown_ratio_delta,
    worst, quality``: ``count`` is the snapshot count ``n``,
    ``changes`` is ``K``, ``regressed`` is ``E`` and ``unknown_delta``
    is the sum of all ``du`` values, all ints; ``unknown_ratio_delta``
    is the float ``round(float(math.fsum(dr) / K), 6)``; and ``worst``
    is the tuple ``(i, du, round(float(dr), 6), q)`` whose first two
    items are ints, whose third item is the rounded ``dr`` float and
    whose ``q`` is ``"fail"`` when that change is regressed and
    ``"pass"`` otherwise. Every float is ``round(float(v), 6)`` with
    negative zero normalized to ``0.0``. ``quality`` is ``"pass"`` only
    when no change is regressed and ``"fail"`` otherwise.
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

    reports = [load_aggregate_report(path) for path in paths]

    first_summary = reports[0]["summary"]
    batch_count = first_summary["batch_count"]
    result_count = first_summary["result_count"]
    for i in range(1, len(reports)):
        summary = reports[i]["summary"]
        if summary["batch_count"] != batch_count:
            raise ValueError(
                f"aggregate report at paths[{i}] has batch_count "
                f"{summary['batch_count']}, expected {batch_count}"
            )
        if summary["result_count"] != result_count:
            raise ValueError(
                f"aggregate report at paths[{i}] has result_count "
                f"{summary['result_count']}, expected {result_count}"
            )

    unknown_delta = 0
    ratio_deltas = []
    worst_position = None
    worst_du = None
    worst_dr = None
    worst_quality = None
    regressed = 0
    for i in range(1, len(reports)):
        previous = reports[i - 1]["summary"]
        current = reports[i]["summary"]
        du = current["unknown"] - previous["unknown"]
        dr = current["unknown_ratio"] - previous["unknown_ratio"]
        unknown_delta += du
        ratio_deltas.append(dr)
        change_quality = "pass"
        if (
            du > 0
            or dr > 0
            or (previous["quality"] == "pass" and current["quality"] == "fail")
        ):
            regressed += 1
            change_quality = "fail"
        position = (-dr, -du, i)
        if worst_position is None or position < worst_position:
            worst_position = position
            worst_du = du
            worst_dr = dr
            worst_quality = change_quality

    changes = len(ratio_deltas)
    unknown_ratio_delta = round(float(math.fsum(ratio_deltas) / changes), 6)
    if unknown_ratio_delta == 0:
        unknown_ratio_delta = 0.0

    worst_dr = round(float(worst_dr), 6)
    if worst_dr == 0:
        worst_dr = 0.0
    worst = (int(worst_position[2]), int(worst_du), worst_dr, worst_quality)

    return {
        "count": int(len(reports)),
        "changes": int(changes),
        "regressed": int(regressed),
        "unknown_delta": int(unknown_delta),
        "unknown_ratio_delta": unknown_ratio_delta,
        "worst": worst,
        "quality": "pass" if regressed == 0 else "fail",
    }


def serialize_aggregate_report_trend(paths) -> bytes:
    """Serialize an :func:`aggregate_report_trend` result as UTF-8 JSON bytes.

    Calls :func:`aggregate_report_trend` exactly once with ``paths`` —
    and no other combining function, without pre-reading or reordering
    the paths — so its validation (container, at-least-two length, then
    each item as a non-empty ``str``, in that order), first-error order,
    ``TypeError``/``ValueError`` split, ``"paths[i]: "`` index prefixes,
    loading exceptions (propagated unchanged) and file non-modification
    contract all apply here as well. Inputs and the loaded files are not
    modified.

    With ``T`` the dict returned by :func:`aggregate_report_trend`, the
    encoded object is taken directly from ``T``: top-level keys exactly
    in the order ``count, changes, regressed, unknown_delta,
    unknown_ratio_delta, worst, quality``. The first four values are the
    ints ``T["count"]``, ``T["changes"]``, ``T["regressed"]`` and
    ``T["unknown_delta"]``; ``worst`` is the four-item JSON array
    ``[i, du, dr, quality]`` converted in original order from the tuple
    ``T["worst"]``; and ``quality`` is the string ``T["quality"]``
    copied as-is. Nothing is recomputed, re-sorted or added.

    The object is encoded as UTF-8 JSON with ``ensure_ascii=False``,
    ``separators=(",", ":")``, ``allow_nan=False``, no indentation, no
    BOM and no trailing newline. The two floats
    (``unknown_ratio_delta`` and the ``dr`` item of ``worst``) are
    rounded with ``round(float(v), 6)`` only at write time, with
    negative zero normalized to ``0.0``; ints are written in decimal.
    Any JSON or UTF-8 encoding failure raises ``ValueError``.

    Returns the JSON document as ``bytes``.
    """
    result = aggregate_report_trend(paths)
    worst = result["worst"]

    def rounded_float(value):
        value = round(float(value), 6)
        return 0.0 if value == 0 else value

    document = {
        "count": int(result["count"]),
        "changes": int(result["changes"]),
        "regressed": int(result["regressed"]),
        "unknown_delta": int(result["unknown_delta"]),
        "unknown_ratio_delta": rounded_float(result["unknown_ratio_delta"]),
        "worst": [
            int(worst[0]),
            int(worst[1]),
            rounded_float(worst[2]),
            worst[3],
        ],
        "quality": result["quality"],
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"aggregate report trend: could not be serialized to JSON: {exc}"
        ) from exc


_AGGREGATE_REPORT_TREND_KEYS = (
    "count",
    "changes",
    "regressed",
    "unknown_delta",
    "unknown_ratio_delta",
    "worst",
    "quality",
)


def _check_aggregate_report_trend_float(value, name, prefix):
    if type(value) is not float:
        raise TypeError(prefix + f"{name} must be a float")
    if not math.isfinite(value):
        raise ValueError(prefix + f"{name} must be finite")
    if not -1 <= value <= 1:
        raise ValueError(prefix + f"{name} must be in [-1, 1]")
    if value == 0 and math.copysign(1.0, value) < 0:
        raise ValueError(prefix + f"{name} must not be negative zero")
    if value != round(float(value), 6):
        raise ValueError(prefix + f"{name} must equal round(float({name}), 6)")


def _check_aggregate_report_trend(result):
    """Validate a decoded aggregate report trend; return its normalized dict."""
    prefix = "aggregate report trend: "
    if not isinstance(result, dict):
        raise TypeError("aggregate report trend must be a dict")
    if list(result.keys()) != list(_AGGREGATE_REPORT_TREND_KEYS):
        raise TypeError(
            "aggregate report trend keys must be in the order "
            "count, changes, regressed, unknown_delta, "
            "unknown_ratio_delta, worst, quality"
        )

    count = result["count"]
    if type(count) is not int:
        raise TypeError(prefix + "count must be a non-bool int")
    if count < 2:
        raise ValueError(prefix + "count must be >= 2")

    changes = result["changes"]
    if type(changes) is not int:
        raise TypeError(prefix + "changes must be a non-bool int")
    if changes != count - 1:
        raise ValueError(prefix + "changes must equal count - 1")

    regressed = result["regressed"]
    if type(regressed) is not int:
        raise TypeError(prefix + "regressed must be a non-bool int")
    if not 0 <= regressed <= changes:
        raise ValueError(prefix + "regressed must be in [0, changes]")

    unknown_delta = result["unknown_delta"]
    if type(unknown_delta) is not int:
        raise TypeError(prefix + "unknown_delta must be a non-bool int")

    _check_aggregate_report_trend_float(
        result["unknown_ratio_delta"], "unknown_ratio_delta", prefix
    )

    worst = result["worst"]
    worst_prefix = prefix + "worst: "
    if not isinstance(worst, list):
        raise TypeError(worst_prefix + "must be a list")
    if len(worst) != 4:
        raise ValueError(worst_prefix + "must have 4 elements")

    index = worst[0]
    if type(index) is not int:
        raise TypeError(worst_prefix + "i must be a non-bool int")
    if not 1 <= index < count:
        raise ValueError(worst_prefix + "i must be in [1, count)")

    du = worst[1]
    if type(du) is not int:
        raise TypeError(worst_prefix + "du must be a non-bool int")

    _check_aggregate_report_trend_float(worst[2], "dr", worst_prefix)

    worst_quality = worst[3]
    if type(worst_quality) is not str:
        raise TypeError(worst_prefix + "quality must be a str")
    if worst_quality not in ("pass", "fail"):
        raise ValueError(worst_prefix + "quality must be 'pass' or 'fail'")

    quality = result["quality"]
    if type(quality) is not str:
        raise TypeError(prefix + "quality must be a str")
    if quality not in ("pass", "fail"):
        raise ValueError(prefix + "quality must be 'pass' or 'fail'")
    if (quality == "pass") != (regressed == 0):
        raise ValueError(
            prefix + "quality must be 'pass' if and only if regressed is 0"
        )

    return {
        "count": int(count),
        "changes": int(changes),
        "regressed": int(regressed),
        "unknown_delta": int(unknown_delta),
        "unknown_ratio_delta": result["unknown_ratio_delta"],
        "worst": (int(index), int(du), worst[2], worst_quality),
        "quality": quality,
    }


def _dump_aggregate_report_trend(result):
    document = {
        "count": int(result["count"]),
        "changes": int(result["changes"]),
        "regressed": int(result["regressed"]),
        "unknown_delta": int(result["unknown_delta"]),
        "unknown_ratio_delta": result["unknown_ratio_delta"],
        "worst": [
            int(result["worst"][0]),
            int(result["worst"][1]),
            result["worst"][2],
            result["worst"][3],
        ],
        "quality": result["quality"],
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(
            f"aggregate report trend: could not be serialized to JSON: {exc}"
        ) from exc


def load_aggregate_report_trend(path) -> dict:
    """Load a :func:`serialize_aggregate_report_trend`-produced JSON trend from ``path``.

    ``path`` validation, binary (``"rb"``) reading and system
    exceptions (a missing file raises ``FileNotFoundError``, a directory
    raises ``IsADirectoryError`` and every other ``OSError`` is
    propagated unchanged), the BOM and trailing-newline rejection,
    UTF-8/JSON decoding, the rejection of ``NaN``/``Infinity`` and
    duplicate keys, the canonical byte-for-byte re-serialization check
    and the file non-modification contract all follow
    :func:`load_aggregate`; a non-``str`` path raises ``TypeError``, an
    empty ``str`` raises ``ValueError`` and any parse, decoding,
    structure or canonical-byte violation raises ``ValueError``. The
    file is not modified.

    The decoded value must be a JSON object with top-level keys exactly
    in the order ``count, changes, regressed, unknown_delta,
    unknown_ratio_delta, worst, quality`` — duplicated, missing or extra
    keys are rejected. The first four values must be non-bool ints:
    ``count`` must be ``>= 2``, ``changes`` must equal ``count - 1`` and
    ``regressed`` must be in ``[0, changes]``.
    ``unknown_ratio_delta`` must be a finite float in ``[-1, 1]``, equal
    to ``round(float(v), 6)`` and must not be negative zero. ``worst``
    must be the four-item array ``[i, du, dr, q]``: ``i`` and ``du``
    must be non-bool ints with ``1 <= i < count``; ``dr`` must be a
    finite float in ``[-1, 1]``, equal to ``round(float(v), 6)`` and
    must not be negative zero; ``q`` must be ``"pass"`` or ``"fail"``.
    The top-level ``quality`` must be ``"pass"`` or ``"fail"`` and
    ``"pass"`` if and only if ``regressed`` is ``0``. Any key-order,
    type, range or relation mismatch raises ``ValueError``.

    Returns the trend as a dict with the keys in the order above; only
    the ``worst`` array is restored to a tuple, every other value stays
    as decoded. The file is never modified.
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
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ValueError as exc:
        raise ValueError(f"file is not valid JSON: {exc}") from exc

    try:
        result = _check_aggregate_report_trend(parsed)
        canonical = _dump_aggregate_report_trend(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"file does not contain a valid aggregate report trend: {exc}"
        ) from exc

    if data != canonical:
        raise ValueError(
            "file bytes do not match the canonical "
            "serialize_aggregate_report_trend output"
        )

    return result


def export_aggregate(path, output) -> bytes:
    """Load a substrate aggregate and atomically write its canonical bytes.

    Calls :func:`load_aggregate` exactly once with ``path`` — before any
    other work and no second time — so its validation, first-error
    order, exceptions (propagated unchanged), canonical-byte checks and
    file non-modification contract all apply here as well; in particular
    a bad ``path`` value is reported before ``output`` is inspected.

    With ``A`` the dict returned by :func:`load_aggregate`, the bytes
    ``B`` are the canonical :func:`dump_aggregate` re-serialization of
    ``A`` (its original key order and the same UTF-8 JSON settings:
    ``ensure_ascii=False``, ``separators=(",", ":")``,
    ``allow_nan=False``, no BOM and no trailing newline, with tuples
    recursively encoded as JSON arrays). ``output`` is then validated:
    it must be a non-empty ``str`` (a non-str raises ``TypeError`` and
    an empty ``str`` raises ``ValueError``), in that order.

    ``output`` must not name the same file as ``path``: when both sides
    exist they are compared with ``os.path.samefile`` so soft and hard
    links are recognized, and otherwise the normalized paths
    ``os.path.normcase(os.path.realpath(os.path.abspath(path)))`` are
    compared; an overlap raises ``ValueError``.

    When there is no overlap, a temporary file is created in ``output``'s
    directory, ``B`` is written to it in binary mode, ``flush()`` and
    ``os.fsync()`` are called and the temporary file then atomically
    replaces ``output`` via ``os.replace``. Any failure before the
    replacement removes the temporary file and leaves an existing
    ``output`` byte for byte unchanged; ``OSError`` is propagated
    unchanged.

    Returns the same ``bytes`` ``B`` that were written.
    """
    document = load_aggregate(path)
    data = _dump_aggregate_document(document)

    if not isinstance(output, str):
        raise TypeError("output must be a str")
    if output == "":
        raise ValueError("output must not be empty")

    if _is_same_file(output, path):
        raise ValueError(
            f"output must not be the same file as an input: "
            f"{output!r} and {path!r}"
        )
    _atomic_write_bytes(output, data)
    return data
