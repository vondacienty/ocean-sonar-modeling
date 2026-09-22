"""Tests for report.serialize_summary."""

import copy
import json

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.crosspoint import evaluate
from ocean_sonar.quality import assess
from ocean_sonar.report import serialize_summary, summarize
from ocean_sonar.substrate import classify

CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]
LAYERS = [
    (1.0, 2, 2, [(1.0, 0.5), (2.0, 0.0), (4.0, 1.0), (0.0, 0.0)]),
]
CROSSINGS_FAIL = [(0.0, 0.0, 10.0, 9.0)]

CP = evaluate(CROSSINGS)
TER = assess(LAYERS)
SUB = classify(LAYERS)
SUMMARY = summarize(CP, TER, SUB)


def _summary(**changes):
    value = copy.deepcopy(SUMMARY)
    value.update(changes)
    return value


def test_serialize_summary_exported():
    assert "serialize_summary" in report_mod.__all__
    assert report_mod.serialize_summary is serialize_summary


def test_returns_bytes_without_trailing_newline():
    data = serialize_summary(SUMMARY)
    assert isinstance(data, bytes)
    assert data == data.rstrip(b"\n")
    data.decode("utf-8")


def test_json_is_compact_and_key_order_preserved():
    data = serialize_summary(SUMMARY)
    assert b", " not in data
    assert b": " not in data
    parsed = json.loads(data)
    assert list(parsed.keys()) == [
        "crosspoint",
        "terrain",
        "substrate",
        "overall",
    ]
    assert list(parsed["crosspoint"].keys()) == [
        "count",
        "bias",
        "rmse",
        "max_abs",
        "within_tolerance",
        "quality",
    ]
    assert list(parsed["terrain"][0].keys()) == [
        "resolution",
        "total",
        "valid",
        "coverage",
        "slope_exceed",
        "roughness_exceed",
    ]
    assert list(parsed["substrate"][0].keys()) == [
        "resolution",
        "nx",
        "ny",
        "classes",
        "counts",
    ]
    assert list(parsed["substrate"][0]["counts"].keys()) == [
        "unknown",
        "mud",
        "sand",
        "gravel",
        "rock",
    ]


def test_tuples_become_arrays():
    parsed = json.loads(serialize_summary(SUMMARY))
    assert isinstance(parsed["terrain"], list)
    assert isinstance(parsed["substrate"], list)
    assert parsed["substrate"][0]["classes"] == ["mud", "mud", "mud", "mud"]


def test_pass_content_roundtrip():
    parsed = json.loads(serialize_summary(SUMMARY))
    assert parsed["overall"] == "pass"
    assert parsed["crosspoint"]["count"] == 2
    assert parsed["crosspoint"]["quality"] == "pass"


def test_fail_content_roundtrip():
    layers = [(1.0, 1, 1, [(None, 0.5)])]
    summary = summarize(evaluate(CROSSINGS), assess(layers), classify(layers))
    parsed = json.loads(serialize_summary(summary))
    assert parsed["overall"] == "fail"
    assert parsed["substrate"][0]["classes"] == ["unknown"]


def test_floats_rounded_to_six_and_negative_zero_normalized():
    summary = _summary()
    summary["crosspoint"]["bias"] = 0.123456789
    summary["crosspoint"]["quality"] = "fail"
    summary["overall"] = "fail"
    token = serialize_summary(summary).decode("utf-8")
    assert '"bias":0.123457' in token

    summary = _summary()
    summary["crosspoint"]["bias"] = -1e-12
    token = serialize_summary(summary).decode("utf-8")
    assert '"bias":0.0' in token
    assert '"bias":-0.0' not in token


def test_input_not_modified():
    summary = copy.deepcopy(SUMMARY)
    snapshot = copy.deepcopy(summary)
    serialize_summary(summary)
    assert summary == snapshot


def test_container_type_error_first():
    with pytest.raises(TypeError) as excinfo:
        serialize_summary(42)
    assert str(excinfo.value) == "summary must be a dict"
    with pytest.raises(TypeError):
        serialize_summary([])


def test_key_order_error():
    reordered = {
        key: SUMMARY[key]
        for key in ("overall", "crosspoint", "terrain", "substrate")
    }
    with pytest.raises(TypeError) as excinfo:
        serialize_summary(reordered)
    assert "keys must be in the order" in str(excinfo.value)


def test_missing_and_extra_keys():
    missing = {key: SUMMARY[key] for key in SUMMARY if key != "overall"}
    with pytest.raises(TypeError):
        serialize_summary(missing)
    extra = dict(SUMMARY, extra=1)
    with pytest.raises(TypeError):
        serialize_summary(extra)


def test_crosspoint_validation_uses_serialize_rules():
    summary = _summary()
    summary["crosspoint"]["count"] = 0
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "count must be > 0" in str(excinfo.value)

    summary = _summary()
    summary["crosspoint"]["bias"] = 1
    with pytest.raises(TypeError):
        serialize_summary(summary)


def test_terrain_validation_rules():
    summary = _summary()
    summary["terrain"] = ()
    with pytest.raises(ValueError):
        serialize_summary(summary)

    summary = _summary()
    summary["terrain"] = []
    with pytest.raises(TypeError):
        serialize_summary(summary)

    summary = _summary()
    summary["terrain"][0]["coverage"] = 1.5
    with pytest.raises(ValueError):
        serialize_summary(summary)


def test_substrate_validation_rules():
    summary = _summary()
    summary["substrate"] = ()
    with pytest.raises(ValueError):
        serialize_summary(summary)

    summary = _summary()
    summary["substrate"][0]["classes"] = ["mud", "mud", "mud", "mud"]
    with pytest.raises(TypeError):
        serialize_summary(summary)


def test_layer_count_mismatch():
    summary = _summary()
    summary["terrain"] = summary["terrain"] + copy.deepcopy(summary["terrain"])
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "same number of layers" in str(excinfo.value)


def test_resolution_consistency():
    summary = _summary()
    summary["substrate"][0]["resolution"] = 2.0
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "resolution must be equal" in str(excinfo.value)


def test_overall_type_error():
    summary = _summary()
    summary["overall"] = False
    with pytest.raises(TypeError) as excinfo:
        serialize_summary(summary)
    assert str(excinfo.value) == "overall must be a str"


def test_overall_enum_error():
    summary = _summary()
    summary["overall"] = "maybe"
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert str(excinfo.value) == "overall must be 'pass' or 'fail'"


def test_stale_overall_pass_rejected():
    summary = _summary(overall="fail")
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "inconsistent" in str(excinfo.value)


def test_stale_overall_fail_rejected():
    layers = [(1.0, 1, 1, [(None, None)])]
    honest = summarize(evaluate(CROSSINGS), assess(layers), classify(layers))
    summary = copy.deepcopy(honest)
    summary["overall"] = "pass"
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "inconsistent" in str(excinfo.value)


def test_overall_recomputed_from_crosspoint_quality():
    summary = summarize(evaluate(CROSSINGS_FAIL), TER, SUB)
    assert summary["overall"] == "fail"
    parsed = json.loads(serialize_summary(summary))
    assert parsed["overall"] == "fail"


def test_overall_recomputed_from_terrain_exceedance():
    layers = [(1.0, 1, 1, [(5.5, 0.5)])]
    summary = summarize(evaluate(CROSSINGS), assess(layers), classify(layers))
    assert summary["overall"] == "fail"
    parsed = json.loads(serialize_summary(summary))
    assert parsed["overall"] == "fail"


def test_overall_recomputed_from_substrate_unknown():
    layers = [(1.0, 1, 2, [(None, None), (0.0, 0.0)])]
    summary = summarize(evaluate(CROSSINGS), assess(layers), classify(layers))
    parsed = json.loads(serialize_summary(summary))
    assert parsed["overall"] == "fail"


def test_overall_checked_after_layer_items():
    summary = _summary()
    summary["terrain"][0]["coverage"] = 2.0
    summary["overall"] = 42
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "coverage" in str(excinfo.value)

    summary = _summary()
    summary["substrate"][0]["nx"] = 9
    summary["overall"] = 42
    with pytest.raises(ValueError):
        serialize_summary(summary)


def test_crosspoint_checked_before_overall():
    summary = _summary()
    summary["crosspoint"]["count"] = 0
    summary["overall"] = "x"
    with pytest.raises(ValueError) as excinfo:
        serialize_summary(summary)
    assert "count" in str(excinfo.value)


def test_multiple_layers_roundtrip():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.5, 1, 1, [(1.0, 0.5)]),
    ]
    summary = summarize(
        evaluate(CROSSINGS), assess(layers), classify(layers)
    )
    parsed = json.loads(serialize_summary(summary))
    assert len(parsed["terrain"]) == 2
    assert len(parsed["substrate"]) == 2
    assert parsed["overall"] == "pass"
