"""Tests for product.serialize."""

import copy
import json

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.crosspoint import evaluate
from ocean_sonar.product import build, serialize
from ocean_sonar.quality import assess
from ocean_sonar.substrate import classify

POINTS = [
    (0.0, 0.0, 10.0),
    (0.5, 0.5, 12.0),
    (1.5, 1.5, 8.0),
    (1.9, 1.9, 9.0),
]
BOUNDS = (0.0, 0.0, 2.0, 2.0)
RESOLUTIONS = (1.0, 2.0)
CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]

PRODUCT = build(POINTS, BOUNDS, RESOLUTIONS, CROSSINGS)


def _product(**changes):
    value = copy.deepcopy(PRODUCT)
    value.update(changes)
    return value


def _passing_product():
    """A structurally passing product: flat field, all-mud substrate."""
    points = [
        (float(i) + 0.5, float(j) + 0.5, 10.0)
        for i in range(2)
        for j in range(2)
    ]
    product = build(points, BOUNDS, RESOLUTIONS, CROSSINGS)
    for layer in product["layers"]:
        n = layer["nx"] * layer["ny"]
        layer["substrate"]["classes"] = ("mud",) * n
        layer["substrate"]["counts"] = {
            "unknown": 0,
            "mud": n,
            "sand": 0,
            "gravel": 0,
            "rock": 0,
        }
    product["overall"] = "pass"
    return product


def test_serialize_exported():
    assert "serialize" in product_mod.__all__
    assert product_mod.serialize is serialize


def test_returns_bytes_without_trailing_newline():
    data = serialize(PRODUCT)
    assert isinstance(data, bytes)
    assert data == data.rstrip(b"\n")
    data.decode("utf-8")


def test_json_is_compact_and_key_orders_preserved():
    data = serialize(PRODUCT)
    assert b", " not in data
    assert b": " not in data
    parsed = json.loads(data)
    assert list(parsed.keys()) == ["crosspoint", "layers", "overall"]
    assert list(parsed["crosspoint"].keys()) == [
        "count",
        "bias",
        "rmse",
        "max_abs",
        "within_tolerance",
        "quality",
    ]
    for layer in parsed["layers"]:
        assert list(layer.keys()) == [
            "resolution",
            "nx",
            "ny",
            "cells",
            "analysis",
            "quality",
            "substrate",
        ]
        assert list(layer["quality"].keys()) == [
            "resolution",
            "total",
            "valid",
            "coverage",
            "slope_exceed",
            "roughness_exceed",
        ]
        assert list(layer["substrate"].keys()) == [
            "resolution",
            "nx",
            "ny",
            "classes",
            "counts",
        ]
        assert list(layer["substrate"]["counts"].keys()) == [
            "unknown",
            "mud",
            "sand",
            "gravel",
            "rock",
        ]


def test_tuples_become_arrays():
    parsed = json.loads(serialize(PRODUCT))
    assert isinstance(parsed["layers"], list)
    for layer in parsed["layers"]:
        assert isinstance(layer["cells"], list)
        assert isinstance(layer["analysis"], list)
        assert all(isinstance(cell, list) for cell in layer["cells"])
        assert all(isinstance(cell, list) for cell in layer["analysis"])
        assert isinstance(layer["substrate"]["classes"], list)


def test_cells_lengths_and_content():
    parsed = json.loads(serialize(PRODUCT))
    layer0, layer1 = parsed["layers"]
    assert len(layer0["cells"]) == 4
    assert len(layer0["analysis"]) == 4
    assert len(layer1["cells"]) == 1
    assert len(layer1["analysis"]) == 1
    assert layer0["cells"][0] == [2, 11.0]
    assert layer0["cells"][1] == [0, None]


def test_pass_and_fail_content_roundtrip():
    assert json.loads(serialize(PRODUCT))["overall"] == "fail"
    passing = _passing_product()
    parsed = json.loads(serialize(passing))
    assert parsed["overall"] == "pass"
    assert parsed["crosspoint"]["quality"] == "pass"
    for layer in parsed["layers"]:
        assert layer["quality"]["slope_exceed"] == 0
        assert layer["quality"]["roughness_exceed"] == 0
        assert "unknown" not in layer["substrate"]["classes"]


def test_failure_from_crosspoint_quality():
    product = build(
        POINTS,
        BOUNDS,
        RESOLUTIONS,
        [(0.0, 0.0, 10.0, 9.0)],
    )
    assert product["overall"] == "fail"
    parsed = json.loads(serialize(product))
    assert parsed["overall"] == "fail"
    assert parsed["crosspoint"]["quality"] == "fail"


def test_floats_rounded_to_six_and_negative_zero_normalized():
    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells[1] = (1, 0.123456789)
    product["layers"][0]["cells"] = tuple(cells)
    token = serialize(product).decode("utf-8")
    assert "0.123457" in token

    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells[1] = (1, -0.0)
    product["layers"][0]["cells"] = tuple(cells)
    data = serialize(product)
    assert b"[1,0.0]" in data
    assert b"-0.0" not in data


def test_input_not_modified():
    snapshot = copy.deepcopy(PRODUCT)
    serialize(PRODUCT)
    assert PRODUCT == snapshot


def test_container_type_error_first():
    with pytest.raises(TypeError) as excinfo:
        serialize(42)
    assert str(excinfo.value) == "product must be a dict"
    with pytest.raises(TypeError):
        serialize([])


def test_key_order_error():
    reordered = {
        key: PRODUCT[key]
        for key in ("overall", "crosspoint", "layers")
    }
    with pytest.raises(TypeError) as excinfo:
        serialize(reordered)
    assert "keys must be in the order" in str(excinfo.value)


def test_missing_and_extra_keys():
    missing = {key: PRODUCT[key] for key in PRODUCT if key != "overall"}
    with pytest.raises(TypeError):
        serialize(missing)
    extra = dict(PRODUCT, extra=1)
    with pytest.raises(TypeError):
        serialize(extra)


def test_crosspoint_validation_rules():
    product = _product()
    product["crosspoint"]["count"] = 0
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    product["crosspoint"]["bias"] = 1
    with pytest.raises(TypeError):
        serialize(product)


def test_layers_container_rules():
    product = _product()
    product["layers"] = []
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"] = list(PRODUCT["layers"])
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"] = ()
    with pytest.raises(ValueError):
        serialize(product)


def test_layer_must_be_dict_with_key_order():
    layer = PRODUCT["layers"][0]
    product = _product()
    product["layers"] = (list(layer),)
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"] = (
        {
            "resolution": layer["resolution"],
            "nx": layer["nx"],
            "ny": layer["ny"],
            "analysis": layer["analysis"],
            "cells": layer["cells"],
            "quality": layer["quality"],
            "substrate": layer["substrate"],
        },
    )
    with pytest.raises(TypeError) as excinfo:
        serialize(product)
    assert "keys must be in the order" in str(excinfo.value)


def test_layer_scalar_field_rules():
    product = _product()
    product["layers"][0]["resolution"] = 1
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"][0]["resolution"] = 0.0
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    product["layers"][0]["nx"] = 2.0
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"][0]["ny"] = 0
    with pytest.raises(ValueError):
        serialize(product)


def test_cells_rules():
    product = _product()
    product["layers"][0]["cells"] = list(product["layers"][0]["cells"])
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells.pop()
    product["layers"][0]["cells"] = tuple(cells)
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells[0] = list(cells[0])
    product["layers"][0]["cells"] = tuple(cells)
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells[0] = (0, 1.0)
    product["layers"][0]["cells"] = tuple(cells)
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    cells = list(product["layers"][0]["cells"])
    cells[0] = (1, None)
    product["layers"][0]["cells"] = tuple(cells)
    with pytest.raises(TypeError):
        serialize(product)


def test_analysis_rules():
    product = _product()
    product["layers"][0]["analysis"] = list(product["layers"][0]["analysis"])
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"][0]["analysis"] = product["layers"][0]["analysis"][:1]
    with pytest.raises(ValueError):
        serialize(product)

    # (None, roughness) boundary cells produced by terrain.analyze are legal
    product = _product()
    analysis = list(product["layers"][0]["analysis"])
    analysis[0] = (None, 1.0)
    product["layers"][0]["analysis"] = tuple(analysis)
    serialize(product)

    product = _product()
    analysis = list(product["layers"][0]["analysis"])
    analysis[0] = (1.0, None)
    product["layers"][0]["analysis"] = tuple(analysis)
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    analysis = list(product["layers"][0]["analysis"])
    analysis[0] = (1, 0.0)
    product["layers"][0]["analysis"] = tuple(analysis)
    with pytest.raises(TypeError):
        serialize(product)


def test_quality_rules():
    product = _product()
    product["layers"][0]["quality"]["coverage"] = 1
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"][0]["quality"]["coverage"] = 1.5
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    quality = product["layers"][0]["quality"]
    product["layers"][0]["quality"] = {
        "resolution": quality["resolution"],
        "total": quality["total"],
        "valid": quality["valid"],
        "slope_exceed": quality["slope_exceed"],
        "coverage": quality["coverage"],
        "roughness_exceed": quality["roughness_exceed"],
    }
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    product["layers"][0]["quality"]["resolution"] = 9.0
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    product["layers"][0]["quality"]["total"] = 9
    with pytest.raises(ValueError):
        serialize(product)


def test_substrate_rules():
    product = _product()
    product["layers"][0]["substrate"]["classes"] = list(
        product["layers"][0]["substrate"]["classes"]
    )
    with pytest.raises(TypeError):
        serialize(product)

    product = _product()
    classes = list(product["layers"][0]["substrate"]["classes"])
    classes[0] = "silt"
    product["layers"][0]["substrate"]["classes"] = tuple(classes)
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    product["layers"][0]["substrate"]["counts"]["mud"] += 1
    product["layers"][0]["substrate"]["counts"]["sand"] -= 1
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    product["layers"][0]["substrate"]["resolution"] = 9.0
    with pytest.raises(ValueError):
        serialize(product)

    product = _product()
    substrate = product["layers"][0]["substrate"]
    substrate["nx"], substrate["ny"] = 4, 1
    substrate["classes"] = ("mud",) * 4
    substrate["counts"] = {
        "unknown": 0,
        "mud": 4,
        "sand": 0,
        "gravel": 0,
        "rock": 0,
    }
    with pytest.raises(ValueError):
        serialize(product)


def test_overall_rules():
    product = _product()
    product["overall"] = False
    with pytest.raises(TypeError) as excinfo:
        serialize(product)
    assert str(excinfo.value) == "overall must be a str"

    product = _product()
    product["overall"] = "maybe"
    with pytest.raises(ValueError) as excinfo:
        serialize(product)
    assert str(excinfo.value) == "overall must be 'pass' or 'fail'"

    passing = _passing_product()
    passing["overall"] = "fail"
    with pytest.raises(ValueError) as excinfo:
        serialize(passing)
    assert "inconsistent" in str(excinfo.value)

    product = _product(overall="pass")
    with pytest.raises(ValueError) as excinfo:
        serialize(product)
    assert "inconsistent" in str(excinfo.value)


def test_validation_order():
    # top level -> crosspoint -> layers
    product = _product()
    product["crosspoint"]["count"] = 0
    product["layers"] = ()
    with pytest.raises(ValueError) as excinfo:
        serialize(product)
    assert "count" in str(excinfo.value)

    # cells -> analysis within a layer
    product = _product()
    product["layers"][0]["cells"] = ()
    analysis = list(product["layers"][0]["analysis"])
    analysis[0] = (True, 1.0)
    product["layers"][0]["analysis"] = tuple(analysis)
    with pytest.raises(ValueError) as excinfo:
        serialize(product)
    assert "cells" in str(excinfo.value)

    # analysis -> quality
    product = _product()
    analysis = list(product["layers"][0]["analysis"])
    analysis[0] = (True, 1.0)
    product["layers"][0]["analysis"] = tuple(analysis)
    product["layers"][0]["quality"]["coverage"] = 1
    with pytest.raises(TypeError) as excinfo:
        serialize(product)
    assert "analysis" in str(excinfo.value)

    # quality -> substrate
    product = _product()
    product["layers"][0]["quality"]["coverage"] = 1
    product["layers"][0]["substrate"]["classes"] = []
    with pytest.raises(TypeError) as excinfo:
        serialize(product)
    assert "quality" in str(excinfo.value)

    # layers -> overall
    product = _product()
    product["layers"][0]["substrate"]["resolution"] = 9.0
    product["overall"] = 42
    with pytest.raises(ValueError) as excinfo:
        serialize(product)
    assert "resolution" in str(excinfo.value)

    # layer 0 before layer 1
    product = _product()
    product["layers"][0]["cells"] = list(product["layers"][0]["cells"])
    product["layers"][1]["nx"] = True
    with pytest.raises(TypeError) as excinfo:
        serialize(product)
    assert "layers[0]" in str(excinfo.value)


def test_accepts_assess_and_classify_contracts_directly():
    from ocean_sonar.terrain import analyze

    grids = [
        (1.0, 2, 2, ((1, 0.5), (2, 0.0), (4, 1.0), (3, 0.5))),
        (2.0, 1, 1, ((10, 0.5),)),
    ]
    analysis_layers = [analyze(*grid) for grid in grids]
    qualities = assess(
        [
            (grid[0], grid[1], grid[2], analysis_layers[i])
            for i, grid in enumerate(grids)
        ]
    )
    substrates = classify(
        [
            (grid[0], grid[1], grid[2], analysis_layers[i])
            for i, grid in enumerate(grids)
        ]
    )
    crosspoint = evaluate(CROSSINGS)
    layers = tuple(
        {
            "resolution": round(float(grids[i][0]), 6),
            "nx": grids[i][1],
            "ny": grids[i][2],
            "cells": grids[i][3],
            "analysis": analysis_layers[i],
            "quality": qualities[i],
            "substrate": substrates[i],
        }
        for i in range(2)
    )
    product = {
        "crosspoint": crosspoint,
        "layers": layers,
        "overall": "fail",
    }
    parsed = json.loads(serialize(product))
    assert parsed["overall"] == "fail"
    assert parsed["layers"][0]["quality"] == {
        "resolution": 1.0,
        "total": 4,
        "valid": 4,
        "coverage": 1.0,
        "slope_exceed": 0,
        "roughness_exceed": 0,
    }
    # 1x1 grid: no neighbours -> slope None -> substrate unknown
    assert parsed["layers"][1]["substrate"]["counts"] == {
        "unknown": 1,
        "mud": 0,
        "sand": 0,
        "gravel": 0,
        "rock": 0,
    }
