"""Tests for report.generate and report.summarize."""

import copy
import math

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.crosspoint import evaluate
from ocean_sonar.quality import assess
from ocean_sonar.substrate import classify
from ocean_sonar.report import generate, summarize

CROSSINGS_PASS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]
LAYERS_PASS = [
    (1.0, 2, 2, [(1.0, 0.5), (None, None), (4.0, 1.0), (0.0, 0.0)]),
]
CROSSINGS_FAIL = [(0.0, 0.0, 10.0, 9.0)]  # |r| = 1.0 > 0.5
LAYERS_SLOPE_EXCEED = [(1.0, 1, 2, [(5.5, 0.5), (2.0, 1.0)])]
LAYERS_ROUGH_EXCEED = [(1.0, 1, 2, [(1.0, 1.5), (2.0, 1.0)])]


def test_all_pass():
    result = generate(CROSSINGS_PASS, LAYERS_PASS)
    assert result["overall"] == "pass"
    assert list(result.keys()) == ["crosspoint", "terrain", "overall"]


def test_report_keys_fixed_order():
    result = generate(CROSSINGS_PASS, LAYERS_PASS)
    assert list(result) == ["crosspoint", "terrain", "overall"]


def test_crosspoint_is_evaluate_result():
    result = generate(CROSSINGS_PASS, LAYERS_PASS)
    assert result["crosspoint"] == evaluate(CROSSINGS_PASS, 0.5)
    assert list(result["crosspoint"].keys()) == [
        "count",
        "bias",
        "rmse",
        "max_abs",
        "within_tolerance",
        "quality",
    ]
    cp = result["crosspoint"]
    assert cp["quality"] == "pass"
    assert cp["count"] == 2
    assert cp["within_tolerance"] == 2
    assert type(cp["count"]) is int
    assert type(cp["within_tolerance"]) is int
    for name in ("bias", "rmse", "max_abs"):
        assert type(cp[name]) is float
    assert cp["bias"] == 0.0
    assert cp["max_abs"] == 0.2


def test_terrain_is_assess_result():
    result = generate(CROSSINGS_PASS, LAYERS_PASS)
    assert result["terrain"] == assess(LAYERS_PASS, 5.0, 1.0)
    assert isinstance(result["terrain"], tuple)
    assert len(result["terrain"]) == 1
    item = result["terrain"][0]
    assert list(item.keys()) == [
        "resolution",
        "total",
        "valid",
        "coverage",
        "slope_exceed",
        "roughness_exceed",
    ]
    assert item == {
        "resolution": 1.0,
        "total": 4,
        "valid": 3,
        "coverage": 0.75,
        "slope_exceed": 0,
        "roughness_exceed": 0,
    }
    assert type(item["total"]) is int
    assert type(item["valid"]) is int
    assert type(item["slope_exceed"]) is int
    assert type(item["roughness_exceed"]) is int
    assert type(item["resolution"]) is float
    assert type(item["coverage"]) is float


def test_crosspoint_failure_fails_overall():
    result = generate(CROSSINGS_FAIL, LAYERS_PASS)
    assert result["crosspoint"]["quality"] == "fail"
    assert result["overall"] == "fail"


def test_slope_exceed_fails_overall():
    result = generate(CROSSINGS_PASS, LAYERS_SLOPE_EXCEED)
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 1
    assert result["terrain"][0]["roughness_exceed"] == 0
    assert result["overall"] == "fail"


def test_roughness_exceed_fails_overall():
    result = generate(CROSSINGS_PASS, LAYERS_ROUGH_EXCEED)
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 1
    assert result["overall"] == "fail"


def test_any_layer_exceed_fails_overall():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.0, 1, 1, [(6.0, 0.0)]),
    ]
    result = generate(CROSSINGS_PASS, layers)
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][1]["slope_exceed"] == 1
    assert result["overall"] == "fail"


def test_boundary_difference_equal_to_tolerance_passes():
    crossings = [(0.0, 0.0, 10.0, 10.5)]  # |r| == tolerance
    result = generate(crossings, LAYERS_PASS, tolerance=0.5)
    assert result["crosspoint"]["quality"] == "pass"
    assert result["overall"] == "pass"


def test_boundary_slope_equal_to_limit_passes():
    layers = [(1.0, 1, 1, [(5.0, 1.0)])]
    result = generate(CROSSINGS_PASS, layers, slope_limit=5.0, roughness_limit=1.0)
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 0
    assert result["overall"] == "pass"


def test_boundary_just_over_limits_fails():
    layers = [(1.0, 1, 1, [(5.0000001, 1.0000001)])]
    result = generate(CROSSINGS_PASS, layers, slope_limit=5.0, roughness_limit=1.0)
    assert result["terrain"][0]["slope_exceed"] == 1
    assert result["terrain"][0]["roughness_exceed"] == 1
    assert result["overall"] == "fail"


def test_single_crosspoint_and_single_cell_layer():
    crossings = [(3.0, 4.0, 2.0, 2.0)]
    layers = [(0.5, 1, 1, [(0.0, 0.0)])]
    result = generate(crossings, layers)
    assert result["crosspoint"] == {
        "count": 1,
        "bias": 0.0,
        "rmse": 0.0,
        "max_abs": 0.0,
        "within_tolerance": 1,
        "quality": "pass",
    }
    assert result["terrain"] == (
        {
            "resolution": 0.5,
            "total": 1,
            "valid": 1,
            "coverage": 1.0,
            "slope_exceed": 0,
            "roughness_exceed": 0,
        },
    )
    assert result["overall"] == "pass"


def test_empty_cells_do_not_exceed():
    layers = [(1.0, 1, 2, [(None, None), (0.0, 0.0)])]
    result = generate(CROSSINGS_PASS, layers)
    item = result["terrain"][0]
    assert item["valid"] == 1
    assert item["coverage"] == 0.5
    assert item["slope_exceed"] == 0
    assert item["roughness_exceed"] == 0
    assert result["overall"] == "pass"


def test_slope_none_counts_roughness_only():
    layers = [(1.0, 1, 1, [(None, 0.5)])]
    result = generate(CROSSINGS_PASS, layers)
    item = result["terrain"][0]
    assert item["valid"] == 1
    assert item["slope_exceed"] == 0
    assert item["roughness_exceed"] == 0
    assert result["overall"] == "pass"


def test_custom_limits_used():
    crossings = [(0.0, 0.0, 10.0, 10.2)]
    layers = [(1.0, 1, 1, [(2.0, 0.3)])]
    result = generate(
        crossings, layers, tolerance=0.1, slope_limit=1.0, roughness_limit=0.2
    )
    assert result["crosspoint"]["quality"] == "fail"
    assert result["terrain"][0]["slope_exceed"] == 1
    assert result["terrain"][0]["roughness_exceed"] == 1
    assert result["overall"] == "fail"


def test_inputs_not_modified():
    crossings = [[0, 0, 10.0, 10.2], [1, 1, 5.0, 4.8]]
    layers = [
        [1.0, 1, 1, [[1.0, 0.5]]],
    ]
    crossings_snapshot = copy.deepcopy(crossings)
    layers_snapshot = copy.deepcopy(layers)
    generate(crossings, layers)
    assert crossings == crossings_snapshot
    assert layers == layers_snapshot


def test_crosspoint_called_before_assess(monkeypatch):
    calls = []

    def fake_evaluate(crossings, tolerance=0.5):
        calls.append(("evaluate", crossings, tolerance))
        return evaluate(crossings, tolerance)

    def fake_assess(layers, slope_limit=5.0, roughness_limit=1.0):
        calls.append(("assess", layers, slope_limit, roughness_limit))
        return assess(layers, slope_limit, roughness_limit)

    monkeypatch.setattr(report_mod, "evaluate", fake_evaluate)
    monkeypatch.setattr(report_mod, "assess", fake_assess)
    generate(CROSSINGS_PASS, LAYERS_PASS, 0.25, 4.0, 0.9)
    assert [c[0] for c in calls] == ["evaluate", "assess"]
    assert calls[0][1:] == (CROSSINGS_PASS, 0.25)
    assert calls[1][1:] == (LAYERS_PASS, 4.0, 0.9)


def test_evaluate_exception_propagates_unchanged(monkeypatch):
    sentinel = RuntimeError("boom")

    def fake_evaluate(crossings, tolerance=0.5):
        raise sentinel

    def fail_assess(*args, **kwargs):
        raise AssertionError("assess must not be called")

    monkeypatch.setattr(report_mod, "evaluate", fake_evaluate)
    monkeypatch.setattr(report_mod, "assess", fail_assess)
    with pytest.raises(RuntimeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS)
    assert excinfo.value is sentinel


def test_assess_exception_propagates_unchanged(monkeypatch):
    sentinel = RuntimeError("bang")

    def fake_assess(layers, slope_limit=5.0, roughness_limit=1.0):
        raise sentinel

    monkeypatch.setattr(report_mod, "assess", fake_assess)
    with pytest.raises(RuntimeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS)
    assert excinfo.value is sentinel


# --- validation / first-error order -----------------------------------------

def test_error_crossings_type_first():
    bad = {"not": "a list"}
    with pytest.raises(TypeError) as excinfo:
        generate(bad, LAYERS_PASS)
    assert str(excinfo.value) == "crossings must be a list or tuple"


def test_error_crossings_empty_first():
    with pytest.raises(ValueError) as excinfo:
        generate([], LAYERS_PASS)
    assert str(excinfo.value) == "crossings must be non-empty"


def test_error_crossings_item_prefix_propagated():
    with pytest.raises(ValueError) as excinfo:
        generate([(1, 2)], LAYERS_PASS)
    assert str(excinfo.value) == "crossings[0]: must have 4 elements"
    with pytest.raises(TypeError) as excinfo:
        generate([(0, 0, "x", 1.0)], LAYERS_PASS)
    assert str(excinfo.value) == (
        "crossings[0]: d1 must be a non-bool int or float"
    )


def test_error_tolerance_type_before_layers():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, "bad layers", tolerance="nope")
    assert str(excinfo.value) == "tolerance must be a non-bool int or float"


def test_error_tolerance_bool_rejected():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, tolerance=True)
    assert str(excinfo.value) == "tolerance must be a non-bool int or float"


def test_error_tolerance_nonfinite():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, tolerance=float("nan"))
    assert str(excinfo.value) == "tolerance must be finite"
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, tolerance=float("inf"))
    assert str(excinfo.value) == "tolerance must be finite"


def test_error_tolerance_range():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, tolerance=0)
    assert str(excinfo.value) == "tolerance must be > 0"
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, tolerance=-0.1)
    assert str(excinfo.value) == "tolerance must be > 0"


def test_error_layers_type_after_crossings_validated():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, set())
    assert str(excinfo.value) == "layers must be a list or tuple"


def test_error_layers_empty():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, ())
    assert str(excinfo.value) == "layers must be non-empty"


def test_error_layers_item_prefix_propagated():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, [("x", 1, 1, [])])
    assert str(excinfo.value) == "layers[0]: r must be a non-bool int or float"
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, [(1.0, 2, 1, [])])
    assert str(excinfo.value) == "layers[0]: analysis must have nx * ny elements"


def test_error_layers_cell_prefix_propagated():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, [(1.0, 1, 1, [(1.0,)])])
    assert str(excinfo.value) == "layers[0].analysis[0]: must have 2 elements"
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, [(1.0, 1, 1, [(1.0, float("nan"))])])
    assert str(excinfo.value) == "layers[0].analysis[0]: roughness must be finite"


def test_error_slope_limit_before_roughness_and_after_layers():
    with pytest.raises(TypeError) as excinfo:
        generate(
            CROSSINGS_PASS,
            LAYERS_PASS,
            slope_limit="bad",
            roughness_limit="also bad",
        )
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"


def test_error_slope_limit_bool_rejected():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, slope_limit=False)
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"


def test_error_slope_limit_nonfinite():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, slope_limit=float("inf"))
    assert str(excinfo.value) == "slope_limit must be finite"


def test_error_slope_limit_range():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, slope_limit=0)
    assert str(excinfo.value) == "slope_limit must be > 0"


def test_error_roughness_limit_type():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, roughness_limit=object())
    assert str(excinfo.value) == "roughness_limit must be a non-bool int or float"


def test_error_roughness_limit_bool_rejected():
    with pytest.raises(TypeError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, roughness_limit=True)
    assert str(excinfo.value) == "roughness_limit must be a non-bool int or float"


def test_error_roughness_limit_nonfinite():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, roughness_limit=float("-inf"))
    assert str(excinfo.value) == "roughness_limit must be finite"


def test_error_roughness_limit_range():
    with pytest.raises(ValueError) as excinfo:
        generate(CROSSINGS_PASS, LAYERS_PASS, roughness_limit=-1.0)
    assert str(excinfo.value) == "roughness_limit must be > 0"


def test_full_error_order_chain():
    # Everything invalid: crossings error must win.
    with pytest.raises(TypeError):
        generate(42, 42, tolerance="x", slope_limit="y", roughness_limit="z")
    # crossings valid item structure but tolerance bad: tolerance wins over layers.
    crossings = [(0, 0, 1, 1)]
    with pytest.raises(TypeError) as excinfo:
        generate(crossings, 42, tolerance="x", slope_limit="y", roughness_limit="z")
    assert str(excinfo.value) == "tolerance must be a non-bool int or float"
    # layers bad: slope_limit must not be reached first.
    with pytest.raises(TypeError) as excinfo:
        generate(crossings, 42, slope_limit="y", roughness_limit="z")
    assert str(excinfo.value) == "layers must be a list or tuple"
    # layers valid: slope_limit wins over roughness_limit.
    with pytest.raises(TypeError) as excinfo:
        generate(
            crossings,
            LAYERS_PASS,
            slope_limit="y",
            roughness_limit="z",
        )
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"


# --- summarize --------------------------------------------------------------

SUMMARIZE_CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]
SUMMARIZE_LAYERS = [
    (1.0, 2, 2, [(1.0, 0.5), (2.0, 0.0), (4.0, 1.0), (0.0, 0.0)]),
]

CP = evaluate(SUMMARIZE_CROSSINGS)
TER = assess(SUMMARIZE_LAYERS)
SUB = classify(SUMMARIZE_LAYERS)


def _cp(**changes):
    value = copy.deepcopy(CP)
    value.update(changes)
    return value


def _ter(*items):
    return tuple(copy.deepcopy(item) for item in items)


def _sub(*items):
    return tuple(copy.deepcopy(item) for item in items)


def _terrain_item(**changes):
    item = copy.deepcopy(TER[0])
    item.update(changes)
    return item


def _substrate_item(**changes):
    item = copy.deepcopy(SUB[0])
    item.update(changes)
    return item


def test_summarize_exported():
    assert "summarize" in report_mod.__all__
    assert report_mod.summarize is summarize


def test_summarize_all_pass():
    result = summarize(CP, TER, SUB)
    assert list(result.keys()) == ["crosspoint", "terrain", "substrate", "overall"]
    assert result["overall"] == "pass"


def test_summarize_passes_inputs_through_unchanged():
    result = summarize(CP, TER, SUB)
    assert result["crosspoint"] is CP
    assert result["terrain"] is TER
    assert result["substrate"] is SUB


def test_summarize_multiple_layers_pass():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.5, 1, 1, [(1.0, 0.5)]),
    ]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["overall"] == "pass"


def test_summarize_resolution_int_float_numeric_equality():
    terrain = _ter(_terrain_item(resolution=1.0))
    substrate = _sub(_substrate_item(resolution=1))
    with pytest.raises(TypeError):
        # gate accepts 1 == 1.0; per-item structure then rejects int
        summarize(CP, terrain, substrate)

    terrain = _ter(_terrain_item(resolution=1.0))
    substrate = _sub(_substrate_item(resolution=1.0))
    assert summarize(CP, terrain, substrate)["overall"] == "pass"


def test_summarize_crosspoint_fail_fails_overall():
    cp = evaluate([(0.0, 0.0, 10.0, 9.0)])
    assert cp["quality"] == "fail"
    assert summarize(cp, TER, SUB)["overall"] == "fail"


def test_summarize_slope_exceed_fails_overall():
    layers = [(1.0, 1, 1, [(5.5, 0.5)])]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["terrain"][0]["slope_exceed"] == 1
    assert result["overall"] == "fail"


def test_summarize_roughness_exceed_fails_overall():
    layers = [(1.0, 1, 1, [(0.0, 1.5)])]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["terrain"][0]["roughness_exceed"] == 1
    assert result["overall"] == "fail"


def test_summarize_any_layer_exceed_fails_overall():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.0, 1, 1, [(6.0, 0.0)]),
    ]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["terrain"][1]["slope_exceed"] == 1
    assert result["overall"] == "fail"


def test_summarize_unknown_class_from_none_slope_fails_overall():
    layers = [(1.0, 1, 1, [(None, 0.5)])]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["substrate"][0]["classes"] == ("unknown",)
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["overall"] == "fail"


def test_summarize_unknown_class_from_empty_cell_fails_overall():
    layers = [(1.0, 1, 2, [(None, None), (0.0, 0.0)])]
    result = summarize(CP, assess(layers), classify(layers))
    assert "unknown" in result["substrate"][0]["classes"]
    assert result["overall"] == "fail"


def test_summarize_any_substrate_layer_unknown_fails_overall():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.0, 1, 1, [(None, None)]),
    ]
    result = summarize(CP, assess(layers), classify(layers))
    assert result["overall"] == "fail"


def test_summarize_inputs_not_modified():
    cp = copy.deepcopy(CP)
    terrain = copy.deepcopy(TER)
    substrate = copy.deepcopy(SUB)
    snapshots = (copy.deepcopy(cp), copy.deepcopy(terrain), copy.deepcopy(substrate))
    summarize(cp, terrain, substrate)
    assert (cp, terrain, substrate) == snapshots


# validation order: crosspoint -> terrain -> substrate -> lengths ->
# per-layer resolution -> per-item structure

def test_summarize_crosspoint_not_dict():
    with pytest.raises(TypeError):
        summarize([("resolution", 1.0)], TER, SUB)


def test_summarize_crosspoint_wrong_key_order():
    reordered = {
        key: CP[key]
        for key in (
            "quality",
            "count",
            "bias",
            "rmse",
            "max_abs",
            "within_tolerance",
        )
    }
    with pytest.raises(TypeError):
        summarize(reordered, TER, SUB)


def test_summarize_crosspoint_missing_key():
    broken = {key: CP[key] for key in CP if key != "quality"}
    with pytest.raises(TypeError):
        summarize(broken, TER, SUB)


def test_summarize_crosspoint_extra_key():
    broken = dict(CP, extra=1)
    with pytest.raises(TypeError):
        summarize(broken, TER, SUB)


def test_summarize_crosspoint_count_type():
    with pytest.raises(TypeError):
        summarize(_cp(count=2.0), TER, SUB)
    with pytest.raises(TypeError):
        summarize(_cp(count=True), TER, SUB)


def test_summarize_crosspoint_count_range():
    with pytest.raises(ValueError):
        summarize(_cp(count=0), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(count=-1), TER, SUB)


def test_summarize_crosspoint_bias_type():
    with pytest.raises(TypeError):
        summarize(_cp(bias=0), TER, SUB)


def test_summarize_crosspoint_values_nonfinite():
    with pytest.raises(ValueError):
        summarize(_cp(bias=float("nan")), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(rmse=float("inf")), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(max_abs=float("-inf")), TER, SUB)


def test_summarize_crosspoint_negative_rmse_and_max_abs():
    with pytest.raises(ValueError):
        summarize(_cp(rmse=-0.01), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(max_abs=-0.01), TER, SUB)


def test_summarize_crosspoint_within_tolerance_checks():
    with pytest.raises(TypeError):
        summarize(_cp(within_tolerance=2.0), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(within_tolerance=-1), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(within_tolerance=3), TER, SUB)


def test_summarize_crosspoint_quality_checks():
    with pytest.raises(TypeError):
        summarize(_cp(quality=False), TER, SUB)
    with pytest.raises(ValueError):
        summarize(_cp(quality="maybe"), TER, SUB)


def test_summarize_crosspoint_field_order():
    broken = _cp(bias="bad", rmse="bad")
    with pytest.raises(TypeError) as excinfo:
        summarize(broken, TER, SUB)
    assert "bias" in str(excinfo.value)


def test_summarize_terrain_not_tuple():
    with pytest.raises(TypeError):
        summarize(CP, [dict(TER[0])], SUB)


def test_summarize_terrain_empty():
    with pytest.raises(ValueError):
        summarize(CP, (), SUB)


def test_summarize_substrate_not_tuple():
    with pytest.raises(TypeError):
        summarize(CP, TER, [dict(SUB[0])])


def test_summarize_substrate_empty():
    with pytest.raises(ValueError):
        summarize(CP, TER, ())


def test_summarize_layer_count_mismatch():
    with pytest.raises(ValueError):
        summarize(CP, TER + TER, SUB)
    with pytest.raises(ValueError):
        summarize(CP, TER, SUB + SUB)


def test_summarize_resolution_mismatch():
    terrain = assess([(1.0, 1, 1, [(0.0, 0.0)])])
    substrate = classify([(2.0, 1, 1, [(0.0, 0.0)])])
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, terrain, substrate)
    assert "resolution" in str(excinfo.value)


def test_summarize_resolution_nan_is_mismatch():
    terrain = _ter(_terrain_item(resolution=float("nan")))
    substrate = _sub(_substrate_item(resolution=float("nan")))
    with pytest.raises(ValueError):
        summarize(CP, terrain, substrate)


def test_summarize_resolution_gate_before_item_structure():
    terrain = assess([(1.0, 1, 1, [(0.0, 0.0)])])
    substrate = classify([(2.0, 1, 1, [(0.0, 0.0)])])
    bad = dict(substrate[0])
    bad["nx"] = 5  # structural inconsistency must not be reached first
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, terrain, (bad,))
    assert "resolution" in str(excinfo.value)


def test_summarize_terrain_item_not_dict():
    with pytest.raises(TypeError) as excinfo:
        summarize(CP, (("not", "a", "dict"),), SUB)
    assert "terrain[0]" in str(excinfo.value)


def test_summarize_substrate_item_not_dict():
    with pytest.raises(TypeError) as excinfo:
        summarize(CP, TER, ("not-a-dict",))
    assert "substrate[0]" in str(excinfo.value)


def test_summarize_terrain_item_wrong_key_order():
    item = {
        key: TER[0][key]
        for key in (
            "resolution",
            "total",
            "valid",
            "coverage",
            "roughness_exceed",
            "slope_exceed",
        )
    }
    with pytest.raises(TypeError):
        summarize(CP, _ter(item), SUB)


def test_summarize_terrain_item_field_types_and_ranges():
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(resolution=1)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(resolution=float("nan"))), SUB)
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(total=4.0)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(total=0)), SUB)
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(valid=4.0)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(valid=5)), SUB)
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(coverage=1)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(coverage=float("inf"))), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(coverage=1.01)), SUB)
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(slope_exceed=0.0)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(slope_exceed=-1)), SUB)
    with pytest.raises(TypeError):
        summarize(CP, _ter(_terrain_item(roughness_exceed=False)), SUB)
    with pytest.raises(ValueError):
        summarize(CP, _ter(_terrain_item(roughness_exceed=5)), SUB)


def test_summarize_terrain_items_checked_before_substrate_items():
    terrain = _ter(_terrain_item(coverage="bad"))
    substrate = _sub(_substrate_item(nx="bad"))
    with pytest.raises(TypeError) as excinfo:
        summarize(CP, terrain, substrate)
    assert "coverage" in str(excinfo.value)


def test_summarize_terrain_items_index_order():
    good = _terrain_item()
    bad = _terrain_item(total=0)
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, _ter(good, bad), SUB + SUB)
    assert "terrain[1]" in str(excinfo.value)


def test_summarize_substrate_item_wrong_key_order():
    item = {
        key: SUB[0][key]
        for key in ("resolution", "nx", "ny", "counts", "classes")
    }
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_resolution_checks():
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(_substrate_item(resolution=1)))
    with pytest.raises(ValueError):
        summarize(CP, TER, _sub(_substrate_item(resolution=float("inf"))))


def test_summarize_substrate_nx_ny_checks():
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(_substrate_item(nx=2.0)))
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(_substrate_item(ny=False)))
    with pytest.raises(ValueError):
        summarize(CP, TER, _sub(_substrate_item(nx=0)))


def test_summarize_substrate_classes_must_be_tuple():
    item = _substrate_item(classes=["mud"] * 4)
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_classes_length():
    item = _substrate_item(classes=("mud",) * 3)
    with pytest.raises(ValueError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_class_element_type():
    item = _substrate_item(classes=(1,) + ("mud",) * 3)
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_unknown_class_name():
    item = _substrate_item(classes=("silt",) + ("mud",) * 3)
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, TER, _sub(item))
    assert "silt" in str(excinfo.value)


def test_summarize_substrate_counts_must_be_dict():
    item = _substrate_item(counts=(0, 4, 0, 0, 0))
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_counts_wrong_key_order():
    counts = SUB[0]["counts"]
    item = _substrate_item(
        counts={key: counts[key] for key in ("mud", "unknown", "sand", "gravel", "rock")}
    )
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_counts_field_types():
    item = _substrate_item(
        counts={"unknown": 0.0, "mud": 4, "sand": 0, "gravel": 0, "rock": 0}
    )
    with pytest.raises(TypeError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_counts_negative():
    item = _substrate_item(
        counts={"unknown": -1, "mud": 4, "sand": 0, "gravel": 0, "rock": 0}
    )
    with pytest.raises(ValueError):
        summarize(CP, TER, _sub(item))


def test_summarize_substrate_counts_must_match_classes():
    item = _substrate_item(classes=("sand",) * 4)
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, TER, _sub(item))
    assert "counts" in str(excinfo.value)


def test_summarize_full_error_order_chain():
    good_layers = [(1.0, 1, 1, [(0.0, 0.0)])]
    terrain = assess(good_layers)
    substrate = classify(good_layers)

    with pytest.raises(TypeError):
        summarize(42, 42, 42)
    with pytest.raises(TypeError):
        summarize(CP, 42, 42)
    with pytest.raises(TypeError):
        summarize(CP, terrain, 42)

    # structural item errors lose to count and resolution gates
    with pytest.raises(ValueError):
        summarize(CP, terrain + terrain, substrate)
    bad_resolution_terrain = assess([(9.0, 1, 1, [(0.0, 0.0)])])
    bad_item = dict(substrate[0])
    bad_item["nx"] = 9
    with pytest.raises(ValueError) as excinfo:
        summarize(CP, bad_resolution_terrain, (bad_item,))
    assert "resolution" in str(excinfo.value)
