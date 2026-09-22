"""Tests for substrate.classify seabed substrate classification."""

import copy

import pytest

from ocean_sonar.substrate import classify


def test_class_bit_mapping():
    # 00 mud, 01 sand, 10 gravel, 11 rock on a 2x2 grid (y then x).
    layers = [
        (1.0, 2, 2, [(1.0, 0.5), (1.0, 2.0), (6.0, 0.5), (6.0, 2.0)]),
    ]
    result = classify(layers)
    assert isinstance(result, tuple)
    assert result[0]["classes"] == ("mud", "sand", "gravel", "rock")


def test_result_dict_key_order():
    result = classify([(1.0, 1, 1, [(0.0, 0.0)])])
    assert list(result[0].keys()) == [
        "resolution",
        "nx",
        "ny",
        "classes",
        "counts",
    ]


def test_counts_key_order_and_types():
    layers = [
        (1.0, 2, 2, [(1.0, 0.5), (1.0, 2.0), (6.0, 0.5), (6.0, 2.0)]),
    ]
    counts = classify(layers)[0]["counts"]
    assert list(counts.keys()) == ["unknown", "mud", "sand", "gravel", "rock"]
    assert counts == {"unknown": 0, "mud": 1, "sand": 1, "gravel": 1, "rock": 1}
    assert all(type(v) is int for v in counts.values())


def test_classes_is_tuple_of_str_in_yx_order():
    layers = [
        (1.0, 2, 3, [(0.0, 0.0)] * 6),
    ]
    classes = classify(layers)[0]["classes"]
    assert isinstance(classes, tuple)
    assert len(classes) == 6
    assert all(type(label) is str for label in classes)


def test_nx_ny_and_resolution_echoed():
    result = classify([(2, 3, 4, [(0.0, 0.0)] * 12)])[0]
    assert result["nx"] == 3
    assert result["ny"] == 4
    assert result["resolution"] == 2.0
    assert type(result["resolution"]) is float


def test_resolution_rounded_six_places():
    result = classify([(1.00000049, 1, 1, [(0.0, 0.0)])])[0]
    assert result["resolution"] == 1.0


def test_unknown_cells():
    # Both (None, None) and (None, q) are unknown; slope None alone is illegal.
    layers = [(1.0, 1, 3, [(None, None), (None, 0.5), (1.0, 0.5)])]
    result = classify(layers)[0]
    assert result["classes"] == ("unknown", "unknown", "mud")
    assert result["counts"]["unknown"] == 2
    assert result["counts"]["mud"] == 1


def test_strict_comparison_boundary_equal_is_mud():
    layers = [(1.0, 1, 1, [(5.0, 1.0)])]
    result = classify(layers, slope_limit=5.0, roughness_limit=1.0)[0]
    assert result["classes"] == ("mud",)
    assert result["counts"] == {
        "unknown": 0,
        "mud": 1,
        "sand": 0,
        "gravel": 0,
        "rock": 0,
    }


def test_just_over_limits_is_rock():
    layers = [(1.0, 1, 1, [(5.0000001, 1.0000001)])]
    result = classify(layers)[0]
    assert result["classes"] == ("rock",)


def test_custom_limits():
    layers = [(1.0, 1, 1, [(2.0, 0.3)])]
    result = classify(layers, slope_limit=1.0, roughness_limit=0.2)[0]
    assert result["classes"] == ("rock",)
    result = classify(layers, slope_limit=2.0, roughness_limit=0.3)[0]
    assert result["classes"] == ("mud",)


def test_multiple_layers_order_preserved():
    layers = [
        (1.0, 1, 1, [(0.0, 0.0)]),
        (2.0, 1, 1, [(6.0, 0.0)]),
        (3.0, 1, 1, [(None, None)]),
    ]
    result = classify(layers)
    assert isinstance(result, tuple) and len(result) == 3
    assert result[0]["classes"] == ("mud",)
    assert result[1]["classes"] == ("gravel",)
    assert result[2]["classes"] == ("unknown",)
    assert [item["resolution"] for item in result] == [1.0, 2.0, 3.0]


def test_tuple_inputs():
    result = classify(((1.0, 1, 1, ((0, 0),)),))
    assert isinstance(result, tuple)
    assert result[0]["classes"] == ("mud",)


def test_inputs_not_modified():
    layers = [
        [1.0, 2, 1, [[1.0, 0.5], [None, None]]],
    ]
    snapshot = copy.deepcopy(layers)
    classify(layers)
    assert layers == snapshot


# --- validation / first-error order -----------------------------------------

def test_error_layers_type():
    with pytest.raises(TypeError) as excinfo:
        classify("x")
    assert str(excinfo.value) == "layers must be a list or tuple"


def test_error_layers_empty():
    with pytest.raises(ValueError) as excinfo:
        classify(())
    assert str(excinfo.value) == "layers must be non-empty"


def test_error_layer_type_and_length():
    with pytest.raises(TypeError) as excinfo:
        classify([42])
    assert str(excinfo.value) == "layers[0]: must be a list or tuple"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1)])
    assert str(excinfo.value) == "layers[0]: must have 4 elements"


def test_error_layer_r():
    with pytest.raises(TypeError) as excinfo:
        classify([("1", 1, 1, [])])
    assert str(excinfo.value) == "layers[0]: r must be a non-bool int or float"
    with pytest.raises(TypeError) as excinfo:
        classify([(True, 1, 1, [])])
    assert str(excinfo.value) == "layers[0]: r must be a non-bool int or float"
    with pytest.raises(ValueError) as excinfo:
        classify([(float("nan"), 1, 1, [])])
    assert str(excinfo.value) == "layers[0]: r must be finite"
    with pytest.raises(ValueError) as excinfo:
        classify([(0, 1, 1, [])])
    assert str(excinfo.value) == "layers[0]: r must be > 0"


def test_error_layer_nx_ny():
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1.0, 1, [])])
    assert str(excinfo.value) == "layers[0]: nx must be a non-bool int"
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, True, 1, [])])
    assert str(excinfo.value) == "layers[0]: nx must be a non-bool int"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 0, 1, [])])
    assert str(excinfo.value) == "layers[0]: nx must be > 0"
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 2.0, [])])
    assert str(excinfo.value) == "layers[0]: ny must be a non-bool int"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, -1, [])])
    assert str(excinfo.value) == "layers[0]: ny must be > 0"


def test_error_analysis_container_and_length():
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 1, "x")])
    assert str(excinfo.value) == "layers[0]: analysis must be a list or tuple"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 2, 2, [(0.0, 0.0)])])
    assert str(excinfo.value) == "layers[0]: analysis must have nx * ny elements"


def test_error_cell_type_and_length():
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 1, [42])])
    assert str(excinfo.value) == "layers[0].analysis[0]: must be a list or tuple"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1, [(0.0, 0.0, 0.0)])])
    assert str(excinfo.value) == "layers[0].analysis[0]: must have 2 elements"


def test_error_p_none_illegal():
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 1, [(1.0, None)])])
    assert str(excinfo.value) == (
        "layers[0].analysis[0]: roughness must be a non-bool int or float"
    )


def test_error_cell_values():
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 1, [(True, 0.0)])])
    assert str(excinfo.value) == (
        "layers[0].analysis[0]: slope must be None or a non-bool int or float"
    )
    with pytest.raises(TypeError) as excinfo:
        classify([(1.0, 1, 1, [(None, True)])])
    assert str(excinfo.value) == (
        "layers[0].analysis[0]: roughness must be a non-bool int or float"
    )
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1, [(float("inf"), 0.0)])])
    assert str(excinfo.value) == "layers[0].analysis[0]: slope must be finite"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1, [(-1.0, 0.0)])])
    assert str(excinfo.value) == "layers[0].analysis[0]: slope must be >= 0"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1, [(None, float("nan"))])])
    assert str(excinfo.value) == "layers[0].analysis[0]: roughness must be finite"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 1, [(None, -0.5)])])
    assert str(excinfo.value) == "layers[0].analysis[0]: roughness must be >= 0"


def test_error_limits():
    good = [(1.0, 1, 1, [(0.0, 0.0)])]
    with pytest.raises(TypeError) as excinfo:
        classify(good, slope_limit="x")
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"
    with pytest.raises(TypeError) as excinfo:
        classify(good, slope_limit=False)
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"
    with pytest.raises(ValueError) as excinfo:
        classify(good, slope_limit=float("inf"))
    assert str(excinfo.value) == "slope_limit must be finite"
    with pytest.raises(ValueError) as excinfo:
        classify(good, slope_limit=0)
    assert str(excinfo.value) == "slope_limit must be > 0"
    with pytest.raises(TypeError) as excinfo:
        classify(good, roughness_limit=object())
    assert str(excinfo.value) == "roughness_limit must be a non-bool int or float"
    with pytest.raises(ValueError) as excinfo:
        classify(good, roughness_limit=float("-inf"))
    assert str(excinfo.value) == "roughness_limit must be finite"
    with pytest.raises(ValueError) as excinfo:
        classify(good, roughness_limit=-1.0)
    assert str(excinfo.value) == "roughness_limit must be > 0"


def test_error_order_layer_index_and_cell_index():
    good = (1.0, 1, 1, [(0.0, 0.0)])
    with pytest.raises(TypeError) as excinfo:
        classify([good, "x"], slope_limit="bad")
    assert str(excinfo.value) == "layers[1]: must be a list or tuple"
    with pytest.raises(ValueError) as excinfo:
        classify([(1.0, 1, 2, [(0.0, 0.0), (0.0, -1.0)])])
    assert str(excinfo.value) == "layers[0].analysis[1]: roughness must be >= 0"
    with pytest.raises(TypeError) as excinfo:
        classify([good, (1.0, 1, 1, [(1.0, None)])])
    assert str(excinfo.value) == (
        "layers[1].analysis[0]: roughness must be a non-bool int or float"
    )


def test_error_layers_before_limits():
    with pytest.raises(TypeError) as excinfo:
        classify(42, slope_limit="bad", roughness_limit="also bad")
    assert str(excinfo.value) == "layers must be a list or tuple"
    good = [(1.0, 1, 1, [(1.0, None)])]
    with pytest.raises(TypeError) as excinfo:
        classify(good, slope_limit="bad")
    assert str(excinfo.value) == (
        "layers[0].analysis[0]: roughness must be a non-bool int or float"
    )


def test_error_slope_limit_before_roughness_limit():
    good = [(1.0, 1, 1, [(0.0, 0.0)])]
    with pytest.raises(TypeError) as excinfo:
        classify(good, slope_limit="x", roughness_limit="y")
    assert str(excinfo.value) == "slope_limit must be a non-bool int or float"
