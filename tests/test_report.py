"""Tests for report.generate."""

import copy
import math

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.crosspoint import evaluate
from ocean_sonar.quality import assess
from ocean_sonar.report import generate

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
