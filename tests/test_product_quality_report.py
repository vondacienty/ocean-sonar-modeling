"""Tests for product.quality_report."""

from __future__ import annotations

import copy
import json

import pytest

import ocean_sonar.product as product_mod
from ocean_sonar.product import build, quality_report, serialize, write

POINTS = [
    (0.0, 0.0, 10.0),
    (0.5, 0.5, 12.0),
    (1.5, 1.5, 8.0),
    (1.9, 1.9, 9.0),
]
BOUNDS = (0.0, 0.0, 2.0, 2.0)
RESOLUTIONS = (1.0, 2.0)
CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]


def _write_product(tmp_path, product=None, name="product.json"):
    if product is None:
        product = build(POINTS, BOUNDS, RESOLUTIONS, CROSSINGS)
    path = tmp_path / name
    path.write_bytes(serialize(product))
    return path, product


def test_quality_report_exported():
    assert "quality_report" in product_mod.__all__
    assert product_mod.quality_report is quality_report


def test_report_key_order_and_compact_bytes(tmp_path):
    path, _ = _write_product(tmp_path)
    data = quality_report(str(path))
    assert isinstance(data, bytes)
    assert data == data.rstrip(b"\n")
    assert b", " not in data and b": " not in data
    assert list(json.loads(data).keys()) == [
        "layers",
        "total",
        "valid",
        "coverage",
        "terrain_exceed",
        "unknown",
        "worst",
        "crosspoint",
        "quality",
    ]


def test_report_values_match_product(tmp_path):
    path, product = _write_product(tmp_path)
    parsed = json.loads(quality_report(str(path)))

    layers = product["layers"]
    total = sum(layer["quality"]["total"] for layer in layers)
    valid = sum(layer["quality"]["valid"] for layer in layers)
    terrain_exceed = sum(
        layer["quality"]["slope_exceed"]
        + layer["quality"]["roughness_exceed"]
        for layer in layers
    )
    unknown = sum(layer["substrate"]["counts"]["unknown"] for layer in layers)

    assert parsed["layers"] == len(layers)
    assert parsed["total"] == total
    assert parsed["valid"] == valid
    assert parsed["coverage"] == round(float(valid / total), 6)
    assert parsed["terrain_exceed"] == terrain_exceed
    assert parsed["unknown"] == unknown
    assert parsed["crosspoint"] == product["crosspoint"]["quality"]
    assert parsed["quality"] == product["overall"]

    for name in (
        "layers",
        "total",
        "valid",
        "terrain_exceed",
        "unknown",
        "worst",
    ):
        assert type(parsed[name]) is int
    assert type(parsed["coverage"]) is float


def test_worst_picks_max_unrounded_tuple(tmp_path):
    path, product = _write_product(tmp_path)
    parsed = json.loads(quality_report(str(path)))

    def key(index):
        layer = product["layers"][index]
        return (
            layer["substrate"]["counts"]["unknown"],
            layer["quality"]["slope_exceed"]
            + layer["quality"]["roughness_exceed"],
            -float(
                layer["quality"]["valid"] / layer["quality"]["total"]
            ),
            -index,
        )

    expected = max(range(len(product["layers"])), key=key)
    assert parsed["worst"] == expected


def test_worst_tie_goes_to_lowest_index(tmp_path):
    points = [
        (float(i) + 0.5, float(j) + 0.5, 10.0)
        for i in range(2)
        for j in range(2)
    ]
    product = build(points, BOUNDS, RESOLUTIONS, CROSSINGS)
    # Flatten both layers to the same quality/substrate figures so the
    # first three tuple components tie and only -index decides.
    for layer in product["layers"]:
        quality_item = layer["quality"]
        quality_item["valid"] = 0
        quality_item["coverage"] = 0.0
        quality_item["slope_exceed"] = 0
        quality_item["roughness_exceed"] = 0

        n = len(layer["substrate"]["classes"])
        layer["substrate"]["classes"] = ("unknown",) * n
        layer["substrate"]["counts"] = {
            "unknown": n,
            "mud": 0,
            "sand": 0,
            "gravel": 0,
            "rock": 0,
        }
    product["overall"] = "fail"

    path, _ = _write_product(tmp_path, product)
    parsed = json.loads(quality_report(str(path)))
    assert parsed["worst"] == 0


def test_coverage_rounds_to_six_decimals(tmp_path):
    # Three layers of 4 cells each: valid counts 1, 1, 0 -> 2/12, which
    # has more than six significant decimals.
    points = [
        (float(i) + 0.5, float(j) + 0.5, 10.0)
        for i in range(2)
        for j in range(2)
    ]
    resolutions = (0.5, 1.0, 2.0)
    product = build(points, BOUNDS, resolutions, CROSSINGS)
    path, _ = _write_product(tmp_path, product)
    parsed = json.loads(quality_report(str(path)))
    total = sum(layer["quality"]["total"] for layer in product["layers"])
    valid = sum(layer["quality"]["valid"] for layer in product["layers"])
    assert parsed["coverage"] == round(valid / total, 6)


def test_load_called_exactly_once(tmp_path, monkeypatch):
    path, _ = _write_product(tmp_path)
    calls = []
    real_load = product_mod.load

    def spy(argument):
        calls.append(argument)
        return real_load(argument)

    monkeypatch.setattr(product_mod, "load", spy)
    quality_report(str(path))
    assert calls == [str(path)]


def test_file_not_modified(tmp_path):
    path, _ = _write_product(tmp_path)
    before = path.read_bytes()
    quality_report(str(path))
    assert path.read_bytes() == before


def test_loaded_product_not_modified(tmp_path, monkeypatch):
    path, _ = _write_product(tmp_path)
    snapshot = {}
    real_load = product_mod.load

    def spy(argument):
        product = real_load(argument)
        snapshot["value"] = copy.deepcopy(product)
        return product

    monkeypatch.setattr(product_mod, "load", spy)
    quality_report(str(path))
    assert product_mod.load(str(path)) == snapshot["value"]


def test_load_exceptions_propagate_unchanged(tmp_path):
    with pytest.raises(FileNotFoundError):
        quality_report(str(tmp_path / "missing.json"))

    with pytest.raises(TypeError):
        quality_report(123)

    with pytest.raises(ValueError):
        quality_report("")

    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    with pytest.raises(ValueError):
        quality_report(str(bad))
