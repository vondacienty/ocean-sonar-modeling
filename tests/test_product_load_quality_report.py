"""Tests for product.load_quality_report."""

import json
import math
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import load_quality_report, quality_report

KEYS = [
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
INT_KEYS = ["layers", "total", "valid", "terrain_exceed", "unknown", "worst"]


def dump_report(report):
    return json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def valid_report(**changes):
    report = {
        "layers": 2,
        "total": 4,
        "valid": 3,
        "coverage": 0.75,
        "terrain_exceed": 1,
        "unknown": 0,
        "worst": 1,
        "crosspoint": "pass",
        "quality": "fail",
    }
    report.update(changes)
    return report


def write_report(tmp_path, report=None, data=None, name="report.json"):
    path = tmp_path / name
    if data is None:
        data = dump_report(report)
    path.write_bytes(data)
    return str(path)


def build_passing_product():
    points = [
        (float(i) + 0.5, float(j) + 0.5, 10.0)
        for i in range(2)
        for j in range(2)
    ]
    product = product_mod.build(
        points,
        (0.0, 0.0, 2.0, 2.0),
        (1.0, 2.0),
        [(0.0, 0.0, 10.0, 10.0), (1.0, 1.0, 5.0, 5.0)],
    )
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


def test_exported():
    assert "load_quality_report" in product_mod.__all__
    assert product_mod.load_quality_report is load_quality_report


def test_roundtrip_with_quality_report(tmp_path):
    product = build_passing_product()
    product_path = write_report(
        tmp_path, data=product_mod.serialize(product), name="product.json"
    )
    data = quality_report(product_path)
    path = write_report(tmp_path, data=data, name="report.json")

    result = load_quality_report(path)

    assert data == dump_report(result)
    assert list(result.keys()) == KEYS
    assert result == {
        "layers": 2,
        "total": 5,
        "valid": 5,
        "coverage": 1.0,
        "terrain_exceed": 0,
        "unknown": 0,
        "worst": 0,
        "crosspoint": "pass",
        "quality": "pass",
    }


def test_int_and_float_types_exact(tmp_path):
    path = write_report(tmp_path, valid_report())

    result = load_quality_report(path)

    for name in INT_KEYS:
        assert type(result[name]) is int
    assert type(result["coverage"]) is float
    assert type(result["crosspoint"]) is str
    assert type(result["quality"]) is str


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(tmp_path, value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_quality_report(value)


def test_empty_path_value_error(tmp_path):
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_quality_report("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_quality_report(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_quality_report(str(tmp_path))


def test_file_not_modified(tmp_path):
    path = write_report(tmp_path, valid_report())
    before = os.stat(path)
    with open(path, "rb") as handle:
        bytes_before = handle.read()

    load_quality_report(path)

    with open(path, "rb") as handle:
        assert handle.read() == bytes_before
    after = os.stat(path)
    assert after.st_size == before.st_size
    assert int(after.st_mtime_ns) >= int(before.st_mtime_ns)


def test_bom_rejected(tmp_path):
    path = write_report(tmp_path, data=b"\xef\xbb\xbf" + dump_report(valid_report()))
    with pytest.raises(ValueError, match="BOM"):
        load_quality_report(path)


def test_trailing_newline_rejected(tmp_path):
    path = write_report(tmp_path, data=dump_report(valid_report()) + b"\n")
    with pytest.raises(ValueError, match="trailing newline"):
        load_quality_report(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_report(tmp_path, data=b"{\xff}")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_quality_report(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_report(tmp_path, data=data)
    with pytest.raises(ValueError):
        load_quality_report(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    report = valid_report()
    data = dump_report(report).replace(b"0.75", token.encode("ascii"))
    path = write_report(tmp_path, data=data)
    with pytest.raises(ValueError):
        load_quality_report(path)


def test_duplicate_keys_rejected(tmp_path):
    data = dump_report(valid_report()).replace(
        b'"layers":2', b'"layers":2,"layers":3', 1
    )
    path = write_report(tmp_path, data=data)
    with pytest.raises(ValueError, match="duplicate"):
        load_quality_report(path)


def test_missing_key_rejected(tmp_path):
    report = valid_report()
    del report["worst"]
    path = write_report(tmp_path, report)
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_quality_report(path)


def test_extra_key_rejected(tmp_path):
    report = valid_report()
    report["extra"] = 1
    path = write_report(tmp_path, report)
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_quality_report(path)


def test_wrong_key_order_rejected(tmp_path):
    reordered = {
        "total": 4,
        "layers": 2,
        "valid": 3,
        "coverage": 0.75,
        "terrain_exceed": 1,
        "unknown": 0,
        "worst": 1,
        "crosspoint": "pass",
        "quality": "fail",
    }
    path = write_report(tmp_path, reordered)
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_quality_report(path)


@pytest.mark.parametrize("name", INT_KEYS)
def test_int_fields_reject_bool(tmp_path, name):
    path = write_report(tmp_path, valid_report(**{name: True}))
    with pytest.raises(ValueError, match=f"{name} must be a non-bool int"):
        load_quality_report(path)


@pytest.mark.parametrize("name", INT_KEYS)
def test_int_fields_reject_float(tmp_path, name):
    path = write_report(tmp_path, valid_report(**{name: 2.0}))
    with pytest.raises(ValueError, match=f"{name} must be a non-bool int"):
        load_quality_report(path)


@pytest.mark.parametrize("name", INT_KEYS)
def test_int_fields_reject_str(tmp_path, name):
    path = write_report(tmp_path, valid_report(**{name: "2"}))
    with pytest.raises(ValueError, match=f"{name} must be a non-bool int"):
        load_quality_report(path)


def test_coverage_reject_bool(tmp_path):
    path = write_report(tmp_path, valid_report(coverage=True))
    with pytest.raises(ValueError, match="coverage must be a float"):
        load_quality_report(path)


def test_coverage_reject_int(tmp_path):
    path = write_report(tmp_path, valid_report(coverage=1))
    with pytest.raises(ValueError, match="coverage must be a float"):
        load_quality_report(path)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_coverage_must_be_finite(tmp_path, value):
    text = dump_report(valid_report()).decode("utf-8").replace(
        "0.75", json.dumps(value, allow_nan=True)
    )
    path = write_report(tmp_path, data=text.encode("utf-8"))
    with pytest.raises(ValueError):
        load_quality_report(path)


def test_layers_must_be_positive(tmp_path):
    path = write_report(tmp_path, valid_report(layers=0, worst=0))
    with pytest.raises(ValueError, match="layers must be > 0"):
        load_quality_report(path)


def test_negative_layers_rejected(tmp_path):
    path = write_report(tmp_path, valid_report(layers=-1, worst=0))
    with pytest.raises(ValueError, match="layers must be > 0"):
        load_quality_report(path)


def test_total_must_be_positive(tmp_path):
    path = write_report(
        tmp_path,
        valid_report(total=0, valid=0, coverage=0.0, worst=0),
    )
    with pytest.raises(ValueError, match="total must be > 0"):
        load_quality_report(path)


@pytest.mark.parametrize("valid_value", [-1, 5])
def test_valid_range(tmp_path, valid_value):
    report = valid_report(total=4, valid=valid_value)
    report["coverage"] = round(float(valid_value / 4), 6) if valid_value >= 0 else 0.0
    path = write_report(tmp_path, report)
    with pytest.raises(ValueError, match="valid must be in"):
        load_quality_report(path)


def test_negative_terrain_exceed_rejected(tmp_path):
    path = write_report(
        tmp_path,
        valid_report(terrain_exceed=-1, quality="pass"),
    )
    with pytest.raises(ValueError, match="terrain_exceed must be >= 0"):
        load_quality_report(path)


def test_negative_unknown_rejected(tmp_path):
    path = write_report(tmp_path, valid_report(unknown=-1))
    with pytest.raises(ValueError, match="unknown must be >= 0"):
        load_quality_report(path)


@pytest.mark.parametrize("worst", [-1, 2, 10])
def test_worst_range(tmp_path, worst):
    path = write_report(tmp_path, valid_report(layers=2, worst=worst))
    with pytest.raises(ValueError, match="worst must be in"):
        load_quality_report(path)


def test_coverage_relation(tmp_path):
    path = write_report(tmp_path, valid_report(total=4, valid=3, coverage=0.5))
    with pytest.raises(ValueError, match="coverage must equal"):
        load_quality_report(path)


def test_coverage_unrounded_rejected(tmp_path):
    # 1/3 stored at full precision instead of round(1/3, 6).
    path = write_report(
        tmp_path, valid_report(total=3, valid=1, coverage=1.0 / 3.0)
    )
    with pytest.raises(ValueError, match="coverage must equal"):
        load_quality_report(path)


def test_coverage_rounded_accepted(tmp_path):
    path = write_report(
        tmp_path,
        valid_report(
            total=3, valid=1, coverage=round(float(1 / 3), 6), worst=0
        ),
    )
    result = load_quality_report(path)
    assert result["coverage"] == 0.333333
    assert type(result["coverage"]) is float


def test_negative_zero_coverage_rejected(tmp_path):
    path = write_report(
        tmp_path,
        valid_report(valid=0, coverage=-0.0, worst=0),
    )
    with pytest.raises(ValueError, match="negative zero"):
        load_quality_report(path)


@pytest.mark.parametrize("value", ["maybe", "", "PASS", 0, None])
def test_crosspoint_enum(tmp_path, value):
    path = write_report(tmp_path, valid_report(crosspoint=value))
    with pytest.raises(ValueError, match="crosspoint must be"):
        load_quality_report(path)


@pytest.mark.parametrize("value", ["maybe", "", "PASS", 0, None])
def test_quality_enum(tmp_path, value):
    path = write_report(tmp_path, valid_report(quality=value))
    with pytest.raises(ValueError, match="quality must be"):
        load_quality_report(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"crosspoint": "fail", "terrain_exceed": 0, "unknown": 0, "quality": "pass"},
        {"crosspoint": "pass", "terrain_exceed": 1, "unknown": 0, "quality": "pass"},
        {"crosspoint": "pass", "terrain_exceed": 0, "unknown": 1, "quality": "pass"},
        {"crosspoint": "fail", "terrain_exceed": 1, "unknown": 1, "quality": "pass"},
        {"crosspoint": "pass", "terrain_exceed": 0, "unknown": 0, "quality": "fail"},
    ],
)
def test_quality_relation(tmp_path, changes):
    path = write_report(tmp_path, valid_report(**changes))
    with pytest.raises(ValueError, match="quality must be 'pass' exactly when"):
        load_quality_report(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"crosspoint": "fail", "terrain_exceed": 0, "unknown": 0, "quality": "fail"},
        {"crosspoint": "pass", "terrain_exceed": 1, "unknown": 0, "quality": "fail"},
        {"crosspoint": "pass", "terrain_exceed": 0, "unknown": 2, "quality": "fail"},
        {"crosspoint": "pass", "terrain_exceed": 0, "unknown": 0, "quality": "pass"},
    ],
)
def test_valid_quality_combinations_accepted(tmp_path, changes):
    result = load_quality_report(write_report(tmp_path, valid_report(**changes)))
    assert result["quality"] == changes["quality"]
    assert result["crosspoint"] == changes["crosspoint"]


def test_non_canonical_spacing_rejected(tmp_path):
    data = dump_report(valid_report()).replace(b":", b": ", 1)
    path = write_report(tmp_path, data=data)
    with pytest.raises(ValueError, match="canonical"):
        load_quality_report(path)


def test_non_canonical_float_spelling_rejected(tmp_path):
    # 0.750 parses to the same float but is not the canonical spelling.
    data = dump_report(valid_report()).replace(b"0.75", b"0.750", 1)
    path = write_report(tmp_path, data=data)
    with pytest.raises(ValueError, match="canonical"):
        load_quality_report(path)


def test_zero_coverage_positive_zero_accepted(tmp_path):
    path = write_report(
        tmp_path,
        valid_report(
            total=4,
            valid=0,
            coverage=0.0,
            terrain_exceed=0,
            unknown=0,
            worst=0,
            crosspoint="pass",
            quality="pass",
        ),
    )
    result = load_quality_report(path)
    assert result["coverage"] == 0.0
    assert math.copysign(1.0, result["coverage"]) == 1.0
