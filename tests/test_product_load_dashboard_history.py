"""Tests for product.load_dashboard_history."""

from __future__ import annotations

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history,
    load_dashboard_history,
    serialize_dashboard_history,
)

KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
    "quality",
]


def history_doc(changes, regressed=None, worst=None, quality=None, count=None):
    if regressed is None:
        regressed = sum(1 for c in changes if c["quality"] == "fail")
    if worst is None:
        worst = changes[0]
    if quality is None:
        quality = "pass" if regressed == 0 else "fail"
    if count is None:
        count = len(changes) + 1
    return {
        "count": count,
        "changes": changes,
        "regressed": regressed,
        "worst": worst,
        "quality": quality,
    }


def change(index, passed_delta, regressed_delta, ratio_delta, quality):
    return {
        "index": index,
        "passed_delta": passed_delta,
        "regressed_delta": regressed_delta,
        "ratio_delta": ratio_delta,
        "quality": quality,
    }


def dump(doc):
    return product_mod._dump_dashboard_history(doc)


def write_bytes(tmp_path, data, name="history.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path, doc=None):
    if doc is None:
        doc = history_doc(
            [
                change(1, 1, -1, round(1 / 3, 6), "pass"),
                change(2, -1, 1, -0.25, "fail"),
                change(3, 0, 0, 0.0, "pass"),
            ]
        )
    data = dump(doc)
    return write_bytes(tmp_path, data), data


def test_exported():
    assert "load_dashboard_history" in product_mod.__all__
    assert product_mod.load_dashboard_history is load_dashboard_history


def test_roundtrip_structure(tmp_path):
    path, data = write_valid(tmp_path)

    result = load_dashboard_history(path)

    assert list(result.keys()) == KEYS
    assert result["count"] == 4
    assert result["regressed"] == 1
    assert result["quality"] == "fail"
    changes = result["changes"]
    assert isinstance(changes, tuple)
    assert len(changes) == 3
    for i, item in enumerate(changes):
        assert list(item.keys()) == ITEM_KEYS
        assert item["index"] == i + 1
        assert type(item["passed_delta"]) is int
        assert type(item["regressed_delta"]) is int
        assert type(item["ratio_delta"]) is float
    # worst references the matching tuple item, never a copy
    assert result["worst"] is changes[0]

    assert data == dump(result)


def test_all_pass_quality(tmp_path):
    path, _ = write_valid(
        tmp_path,
        history_doc(
            [
                change(1, 1, 0, 0.5, "pass"),
                change(2, 0, -1, 0.1, "pass"),
            ]
        ),
    )
    result = load_dashboard_history(path)
    assert result["quality"] == "pass"
    assert result["regressed"] == 0


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_dashboard_history(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_dashboard_history("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dashboard_history(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_dashboard_history(str(tmp_path))


def test_file_not_modified_on_success(tmp_path):
    path, data = write_valid(tmp_path)
    before = os.stat(path)

    load_dashboard_history(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    mangled = dump(doc).replace(b'"count":2', b'"count":3', 1)
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        load_dashboard_history(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data, name="bom.json")
    with pytest.raises(ValueError, match="BOM"):
        load_dashboard_history(path)


def test_trailing_newline_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data + b"\n", name="nl.json")
    with pytest.raises(ValueError, match="trailing newline"):
        load_dashboard_history(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}", name="utf8.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_dashboard_history(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data, name="bad.json")
    with pytest.raises(ValueError):
        load_dashboard_history(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'"regressed":1', f'"regressed":{token}'.encode(), 1
    )
    path = write_bytes(tmp_path, mangled, name="const.json")
    with pytest.raises(ValueError):
        load_dashboard_history(path)


def test_duplicate_keys_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'{"count"', b'{"count":1,"count"', 1
    )
    path = write_bytes(tmp_path, mangled, name="dup.json")
    with pytest.raises(ValueError, match="duplicate"):
        load_dashboard_history(path)


def test_missing_top_key_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    del doc["quality"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="missing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history(path)


def test_extra_top_key_rejected(tmp_path):
    _, data = write_valid(
        tmp_path, history_doc([change(1, 0, 0, 0.0, "pass")])
    )
    path = write_bytes(tmp_path, data[:-1] + b',"extra":1}', name="extra.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history(path)


def test_wrong_top_key_order_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    reordered = {key: doc[key] for key in reversed(KEYS)}
    path = write_bytes(
        tmp_path,
        json.dumps(reordered, separators=(",", ":")).encode(),
        name="order.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history(path)


def test_missing_item_key_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    del doc["changes"][0]["ratio_delta"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="imissing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history(path)


def test_wrong_item_key_order_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["changes"][0] = {
        key: doc["changes"][0][key] for key in reversed(ITEM_KEYS)
    }
    doc["worst"] = doc["changes"][0]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="iorder.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history(path)


def test_count_must_be_non_bool_int(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    raw = json.dumps(doc, separators=(",", ":")).replace(
        '"count":2', '"count":true'
    )
    path = write_bytes(tmp_path, raw.encode(), name="countbool.json")
    with pytest.raises(ValueError, match="count must be a non-bool int"):
        load_dashboard_history(path)


@pytest.mark.parametrize("count", [0, 1, -3])
def test_count_must_be_at_least_two(tmp_path, count):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")], count=count)
    doc["changes"] = []
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="count.json",
    )
    with pytest.raises(ValueError, match="count must be >= 2"):
        load_dashboard_history(path)


def test_changes_must_be_array(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["changes"] = {"0": change(1, 0, 0, 0.0, "pass")}
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="array.json",
    )
    with pytest.raises(ValueError, match="changes must be a JSON array"):
        load_dashboard_history(path)


def test_changes_length_must_be_count_minus_one(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["count"] = 3
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="length.json",
    )
    with pytest.raises(ValueError, match="count - 1 elements"):
        load_dashboard_history(path)


def test_index_must_run_consecutively_from_one(tmp_path):
    doc = history_doc(
        [
            change(1, 0, 0, 0.0, "pass"),
            change(3, 0, 0, 0.0, "pass"),
        ],
        worst=change(1, 0, 0, 0.0, "pass"),
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="index.json",
    )
    with pytest.raises(ValueError, match="index must run consecutively"):
        load_dashboard_history(path)


@pytest.mark.parametrize("name", ["index", "passed_delta", "regressed_delta"])
def test_int_fields_reject_bool(tmp_path, name):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["changes"][0][name] = True
    if name == "index":
        doc["worst"] = {
            key: value for key, value in doc["changes"][0].items()
        }
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name=f"{name}bool.json",
    )
    with pytest.raises(ValueError, match=name):
        load_dashboard_history(path)


def test_ratio_delta_must_be_float(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["changes"][0]["ratio_delta"] = 0
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="ratioint.json",
    )
    with pytest.raises(ValueError, match="ratio_delta must be a float"):
        load_dashboard_history(path)


def test_ratio_delta_must_be_finite(tmp_path):
    _, data = write_valid(
        tmp_path, history_doc([change(1, 0, 0, 0.0, "pass")])
    )
    mangled = data.replace(b'"ratio_delta":0.0', b'"ratio_delta":1e999', 1)
    path = write_bytes(tmp_path, mangled, name="ratioinf.json")
    with pytest.raises(ValueError, match="ratio_delta must be finite"):
        load_dashboard_history(path)


@pytest.mark.parametrize("value", [-1.5, 1.5])
def test_ratio_delta_must_be_in_range(tmp_path, value):
    doc = history_doc([change(1, 0, 0, value, "pass")])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="range.json",
    )
    with pytest.raises(ValueError, match=r"ratio_delta must be in \[-1, 1\]"):
        load_dashboard_history(path)


def test_ratio_delta_must_have_at_most_six_decimals(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.1234567, "pass")])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="digits.json",
    )
    with pytest.raises(ValueError, match="at most 6 decimals"):
        load_dashboard_history(path)


def test_ratio_delta_negative_zero_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    raw = dump(doc).replace(b'"ratio_delta":0.0', b'"ratio_delta":-0.0', 1)
    path = write_bytes(tmp_path, raw, name="rationeg0.json")
    with pytest.raises(ValueError, match="negative zero"):
        load_dashboard_history(path)


def test_item_quality_enum(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "maybe")], regressed=0, quality="pass")
    doc["regressed"] = 0
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="qenum.json",
    )
    with pytest.raises(ValueError, match="quality must be 'pass' or 'fail'"):
        load_dashboard_history(path)


def test_regressed_must_be_non_bool_int(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    doc["regressed"] = False
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="regbool.json",
    )
    with pytest.raises(ValueError, match="regressed must be a non-bool int"):
        load_dashboard_history(path)


def test_regressed_must_equal_fail_count(tmp_path):
    doc = history_doc(
        [
            change(1, 0, 0, 0.0, "pass"),
            change(2, 0, 0, 0.0, "fail"),
        ],
        regressed=2,
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="reg.json",
    )
    with pytest.raises(ValueError, match="regressed must equal the number"):
        load_dashboard_history(path)


def test_worst_must_equal_a_changes_item(tmp_path):
    items = [
        change(1, 0, 0, 0.0, "pass"),
        change(2, 1, 0, 0.0, "fail"),
    ]
    doc = history_doc(items, worst=change(3, 1, 0, 0.0, "fail"))
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="worst.json",
    )
    with pytest.raises(ValueError, match="worst must equal one of"):
        load_dashboard_history(path)


def test_quality_pass_requires_zero_regressed(tmp_path):
    doc = history_doc(
        [change(1, 0, 0, 0.0, "fail")], regressed=1, quality="pass"
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="quality.json",
    )
    with pytest.raises(
        ValueError,
        match="quality must be 'pass' exactly when regressed is 0",
    ):
        load_dashboard_history(path)


def test_quality_fail_requires_nonzero_regressed(tmp_path):
    doc = history_doc(
        [change(1, 0, 0, 0.0, "pass")], regressed=0, quality="fail"
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="quality2.json",
    )
    with pytest.raises(
        ValueError,
        match="quality must be 'pass' exactly when regressed is 0",
    ):
        load_dashboard_history(path)


def test_non_canonical_spacing_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data.replace(b":", b": ", 1), name="space.json")
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    doc = history_doc([change(1, 0, 0, 0.0, "pass")])
    data = dump(doc).replace(
        b'"quality":"pass"', b'"quality":"p\\u0061ss"', 1
    )
    path = write_bytes(tmp_path, data, name="unicode.json")
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history(path)


def test_roundtrip_matches_dashboard_history(tmp_path):
    first = {
        "trend": {
            "count": 4,
            "changes": [
                {
                    "index": 1,
                    "failed_delta": 0,
                    "regressed_delta": 0,
                    "passed_delta": 1,
                    "quality": "pass",
                },
                {
                    "index": 2,
                    "failed_delta": 1,
                    "regressed_delta": 2,
                    "passed_delta": -1,
                    "quality": "fail",
                },
                {
                    "index": 3,
                    "failed_delta": 0,
                    "regressed_delta": -1,
                    "passed_delta": 0,
                    "quality": "pass",
                },
            ],
            "regressed": 1,
            "worst": {
                "index": 2,
                "failed_delta": 1,
                "regressed_delta": 2,
                "passed_delta": -1,
                "quality": "fail",
            },
            "quality": "fail",
        },
        "summary": {
            "reports": 4,
            "passed": 2,
            "regressed": 1,
            "ratio": round(2 / 3, 6),
            "worst": 2,
        },
        "quality": "fail",
    }
    second = json.loads(json.dumps(first))
    second["summary"]["passed"] = 3
    second["summary"]["regressed"] = 0
    second["summary"]["ratio"] = 1.0
    second["summary"]["worst"] = 1
    second["trend"]["regressed"] = 0
    second["trend"]["quality"] = "pass"
    second["quality"] = "pass"
    second["trend"]["changes"] = [
        {
            "index": 1,
            "failed_delta": 0,
            "regressed_delta": 0,
            "passed_delta": 1,
            "quality": "pass",
        },
        {
            "index": 2,
            "failed_delta": 0,
            "regressed_delta": 0,
            "passed_delta": 1,
            "quality": "pass",
        },
        {
            "index": 3,
            "failed_delta": 0,
            "regressed_delta": 0,
            "passed_delta": 1,
            "quality": "pass",
        },
    ]
    second["trend"]["worst"] = second["trend"]["changes"][0]

    p1 = write_bytes(
        tmp_path,
        product_mod._dump_overview_comparison_report_trend(first),
        name="a.json",
    )
    p2 = write_bytes(
        tmp_path,
        product_mod._dump_overview_comparison_report_trend(second),
        name="b.json",
    )

    data = serialize_dashboard_history([p1, p2])
    history_path = write_bytes(tmp_path, data, name="history.json")

    result = load_dashboard_history(history_path)
    expected = dashboard_history([p1, p2])
    assert result == expected
    assert result["worst"] is result["changes"][0]
    assert isinstance(result["changes"], tuple)
