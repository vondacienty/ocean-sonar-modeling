"""Tests for report.generate combined crosspoint/terrain reporting."""

import math

import pytest

from ocean_sonar import report
from ocean_sonar.crosspoint import evaluate
from ocean_sonar.quality import assess
from ocean_sonar.report import generate


def _crossings(diff=0.0):
    return [(0.0, 0.0, 10.0, 10.0), (1.0, 2.0, 12.0, 12.0 - diff)]


def _layers(slope=1.0, roughness=0.5):
    return [(1.0, 2, 1, [(slope, roughness), (None, None)])]


# --- overall verdict ----------------------------------------------------


def test_all_pass():
    result = generate(_crossings(diff=0.2), _layers())
    assert result["overall"] == "pass"
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 0


def test_crosspoint_fail_makes_overall_fail():
    result = generate(_crossings(diff=0.6), _layers())
    assert result["crosspoint"]["quality"] == "fail"
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 0
    assert result["overall"] == "fail"


def test_slope_exceed_makes_overall_fail():
    result = generate(_crossings(), _layers(slope=5.5, roughness=0.5))
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 1
    assert result["terrain"][0]["roughness_exceed"] == 0
    assert result["overall"] == "fail"


def test_roughness_exceed_makes_overall_fail():
    result = generate(_crossings(), _layers(slope=1.0, roughness=1.5))
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 1
    assert result["overall"] == "fail"


def test_any_failing_layer_makes_overall_fail():
    crossings = _crossings()
    layers = [
        (1.0, 1, 1, [(1.0, 0.5)]),
        (2.0, 1, 1, [(5.5, 0.5)]),
    ]
    result = generate(crossings, layers)
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][1]["slope_exceed"] == 1
    assert result["overall"] == "fail"


def test_boundary_values_still_pass():
    # |d1 - d2| == tolerance is within; slope/roughness equal to the
    # limit are not strict exceedances.
    crossings = [(0.0, 0.0, 10.0, 9.5)]
    layers = [(1.0, 1, 1, [(5.0, 1.0)])]
    result = generate(crossings, layers)
    assert result["crosspoint"]["quality"] == "pass"
    assert result["terrain"][0]["slope_exceed"] == 0
    assert result["terrain"][0]["roughness_exceed"] == 0
    assert result["overall"] == "pass"


def test_just_beyond_boundary_fails():
    crossings = [(0.0, 0.0, 10.0, 9.49)]
    layers = [(1.0, 1, 1, [(5.0001, 1.0001)])]
    result = generate(crossings, layers)
    assert result["overall"] == "fail"


def test_custom_limits():
    crossings = [(0.0, 0.0, 10.0, 9.0)]
    layers = [(1.0, 1, 1, [(2.0, 0.4)])]
    assert generate(crossings, layers, tolerance=1.0,
                    slope_limit=2.0, roughness_limit=0.4)["overall"] == "pass"
    assert generate(crossings, layers, tolerance=0.5,
                    slope_limit=2.0, roughness_limit=0.4)["overall"] == "fail"
    assert generate(crossings, layers, tolerance=1.0,
                    slope_limit=1.0, roughness_limit=0.4)["overall"] == "fail"
    assert generate(crossings, layers, tolerance=1.0,
                    slope_limit=2.0, roughness_limit=0.3)["overall"] == "fail"


# --- structure / key order / passthrough --------------------------------


def test_fixed_top_level_key_order():
    result = generate(_crossings(), _layers())
    assert list(result) == ["crosspoint", "terrain", "overall"]


def test_crosspoint_value_is_evaluate_dict():
    crossings = _crossings(diff=0.2)
    result = generate(crossings, _layers())
    expected_crosspoint = evaluate(crossings, 0.5)
    assert result["crosspoint"] == expected_crosspoint
    assert list(result["crosspoint"]) == list(expected_crosspoint)
    assert list(result["crosspoint"]) == [
        "count", "bias", "rmse", "max_abs", "within_tolerance", "quality",
    ]
    assert type(result["crosspoint"]["count"]) is int
    assert type(result["crosspoint"]["bias"]) is float


def test_terrain_value_is_assess_tuple():
    layers = _layers()
    result = generate(_crossings(), layers)
    expected_terrain = assess(layers, 5.0, 1.0)
    assert isinstance(result["terrain"], tuple)
    assert result["terrain"] == expected_terrain
    assert list(result["terrain"][0]) == [
        "resolution", "total", "valid", "coverage",
        "slope_exceed", "roughness_exceed",
    ]
    assert type(result["terrain"][0]["total"]) is int
    assert type(result["terrain"][0]["coverage"]) is float


def test_inputs_not_modified():
    crossings = _crossings(diff=0.2)
    layers = _layers()
    crossings_copy = [(x, y, d1, d2) for x, y, d1, d2 in crossings]
    layers_copy = [
        (r, nx, ny, [(slope, roughness) for slope, roughness in analysis])
        for r, nx, ny, analysis in layers
    ]
    generate(crossings, layers)
    assert crossings == crossings_copy
    assert [
        (r, nx, ny, [(slope, roughness) for slope, roughness in analysis])
        for r, nx, ny, analysis in layers
    ] == layers_copy


# --- error propagation --------------------------------------------------


def test_crossings_container_type_error():
    with pytest.raises(TypeError, match=r"^crossings must be a list or tuple$"):
        generate({(0.0, 0.0, 1.0, 1.0)}, _layers())


def test_crossings_empty_value_error():
    with pytest.raises(ValueError, match=r"^crossings must be non-empty$"):
        generate([], _layers())


def test_crossings_item_prefix_propagates():
    with pytest.raises(TypeError, match=r"^crossings\[1\]: must be a list or tuple$"):
        generate([(0.0, 0.0, 1.0, 1.0), "bad"], _layers())


def test_crossings_field_error_propagates():
    with pytest.raises(ValueError,
                       match=r"^crossings\[0\]: d1 must be >= 0$"):
        generate([(0.0, 0.0, -1.0, 1.0)], _layers())


def test_crossings_non_finite_error_propagates():
    with pytest.raises(ValueError,
                       match=r"^crossings\[0\]: d2 must be finite$"):
        generate([(0.0, 0.0, 1.0, math.nan)], _layers())


def test_tolerance_type_error():
    with pytest.raises(TypeError,
                       match=r"^tolerance must be a non-bool int or float$"):
        generate(_crossings(), _layers(), tolerance="0.5")


def test_tolerance_bool_type_error():
    with pytest.raises(TypeError, match=r"tolerance"):
        generate(_crossings(), _layers(), tolerance=True)


def test_tolerance_non_finite():
    with pytest.raises(ValueError, match=r"^tolerance must be finite$"):
        generate(_crossings(), _layers(), tolerance=math.inf)


def test_tolerance_must_be_positive():
    with pytest.raises(ValueError, match=r"^tolerance must be > 0$"):
        generate(_crossings(), _layers(), tolerance=0)


def test_layers_container_type_error():
    bad_layers = {(1.0, 1, 1, ((1.0, 0.5),))}
    with pytest.raises(TypeError, match=r"^layers must be a list or tuple$"):
        generate(_crossings(), bad_layers)


def test_layers_empty_value_error():
    with pytest.raises(ValueError, match=r"^layers must be non-empty$"):
        generate(_crossings(), [])


def test_layers_prefix_propagates():
    with pytest.raises(ValueError,
                       match=r"^layers\[0\]: must have 4 elements$"):
        generate(_crossings(), [(1.0, 1, 1)])


def test_layer_analysis_cell_prefix_propagates():
    with pytest.raises(ValueError,
                       match=r"^layers\[0\]\.analysis\[1\]: must have 2 elements$"):
        generate(_crossings(),
                 [(1.0, 2, 1, [(1.0, 0.5), (1.0,)])])


def test_slope_limit_type_error():
    with pytest.raises(TypeError,
                       match=r"^slope_limit must be a non-bool int or float$"):
        generate(_crossings(), _layers(), slope_limit="5")


def test_slope_limit_non_finite():
    with pytest.raises(ValueError, match=r"^slope_limit must be finite$"):
        generate(_crossings(), _layers(), slope_limit=math.nan)


def test_slope_limit_must_be_positive():
    with pytest.raises(ValueError, match=r"^slope_limit must be > 0$"):
        generate(_crossings(), _layers(), slope_limit=0)


def test_roughness_limit_type_error():
    with pytest.raises(TypeError,
                       match=r"^roughness_limit must be a non-bool int or float$"):
        generate(_crossings(), _layers(), roughness_limit=None)


def test_roughness_limit_non_finite():
    with pytest.raises(ValueError, match=r"^roughness_limit must be finite$"):
        generate(_crossings(), _layers(), roughness_limit=math.inf)


def test_roughness_limit_must_be_positive():
    with pytest.raises(ValueError, match=r"^roughness_limit must be > 0$"):
        generate(_crossings(), _layers(), roughness_limit=-1.0)


# --- first-error ordering: crossings, tolerance, layers, slope, rough ---


def test_order_crossings_before_tolerance():
    # Bad crossings container and bad tolerance: crossings wins.
    with pytest.raises(TypeError, match=r"^crossings must be a list or tuple$"):
        generate("bad", _layers(), tolerance=0)


def test_order_tolerance_before_layers():
    with pytest.raises(ValueError, match=r"^tolerance must be > 0$"):
        generate(_crossings(), "bad", tolerance=0, slope_limit=0)


def test_order_layers_before_slope_limit():
    with pytest.raises(TypeError, match=r"^layers must be a list or tuple$"):
        generate(_crossings(), "bad", slope_limit=0, roughness_limit=0)


def test_order_layers_contents_before_slope_limit():
    bad_layers = [(1.0, 1, 1, [(1.0,)])]
    with pytest.raises(ValueError,
                       match=r"^layers\[0\]\.analysis\[0\]: must have 2 elements$"):
        generate(_crossings(), bad_layers, slope_limit=0)


def test_order_slope_limit_before_roughness_limit():
    with pytest.raises(ValueError, match=r"^slope_limit must be > 0$"):
        generate(_crossings(), _layers(), slope_limit=0, roughness_limit=0)


def test_exception_identical_to_evaluate():
    try:
        generate([(0.0, 0.0, 1.0, "x")], _layers(), tolerance=0)
    except TypeError as exc:
        generated = str(exc)
    else:
        pytest.fail("expected TypeError")
    with pytest.raises(TypeError) as excinfo:
        evaluate([(0.0, 0.0, 1.0, "x")], 0)
    assert generated == str(excinfo.value)


def test_exception_identical_to_assess():
    try:
        generate(_crossings(), [(1.0, 1, 1, [("x", 0.5)])],
                 slope_limit=0, roughness_limit=0)
    except TypeError as exc:
        generated = str(exc)
    else:
        pytest.fail("expected TypeError")
    with pytest.raises(TypeError) as excinfo:
        assess([(1.0, 1, 1, [("x", 0.5)])], 0, 0)
    assert generated == str(excinfo.value)


def test_exported():
    assert report.__all__ == ["generate"]
    assert callable(report.generate)
