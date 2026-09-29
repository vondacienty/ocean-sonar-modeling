"""Tests for product.load_dashboard_history_report_trend."""

from __future__ import annotations

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history_report_trend,
    load_dashboard_history_report_trend,
    serialize_dashboard_history_report_trend,
)

KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "stability_delta",
    "volatility_delta",
    "quality",
]


def trend_doc(
    changes, regressed=None, worst=None, quality=None, count=None
):
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


def change(index, stability_delta, volatility_delta, quality):
    return {
        "index": index,
        "stability_delta": stability_delta,
        "volatility_delta": volatility_delta,
        "quality": quality,
    }


def dump(doc):
    return product_mod._dump_dashboard_history_report_trend(doc)


def write_bytes(tmp_path, data, name="trend.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path, doc=None):
    if doc is None:
        doc = trend_doc(
            [
                change(1, 0.5, -0.25, "pass"),
                change(2, -0.25, 0.5, "fail"),
                change(3, 0.0, 0.1, "pass"),
            ]
        )
    data = dump(doc)
    return write_bytes(tmp_path, data), data


def test_exported():
    assert "load_dashboard_history_report_trend" in product_mod.__all__
    assert (
        product_mod.load_dashboard_history_report_trend
        is load_dashboard_history_report_trend
    )


def test_roundtrip_structure(tmp_path):
    path, data = write_valid(tmp_path)

    result = load_dashboard_history_report_trend(path)

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
        assert type(item["index"]) is int
        assert type(item["stability_delta"]) is float
        assert type(item["volatility_delta"]) is float
    # worst references the matching tuple item, never a copy
    assert result["worst"] is changes[0]

    assert data == dump(
        {
            "count": result["count"],
            "changes": [dict(item) for item in changes],
            "regressed": result["regressed"],
            "worst": dict(result["worst"]),
            "quality": result["quality"],
        }
    )


def test_all_pass_quality(tmp_path):
    path, _ = write_valid(
        tmp_path,
        trend_doc(
            [
                change(1, 0.5, -0.1, "pass"),
                change(2, 0.1, 0.2, "pass"),
            ]
        ),
    )
    result = load_dashboard_history_report_trend(path)
    assert result["quality"] == "pass"
    assert result["regressed"] == 0


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_dashboard_history_report_trend(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_dashboard_history_report_trend("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dashboard_history_report_trend(
            str(tmp_path / "missing.json")
        )


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_dashboard_history_report_trend(str(tmp_path))


def test_file_not_modified_on_success(tmp_path):
    path, data = write_valid(tmp_path)
    before = os.stat(path)

    load_dashboard_history_report_trend(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    mangled = dump(doc).replace(b'"count":2', b'"count":3', 1)
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        load_dashboard_history_report_trend(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data, name="bom.json")
    with pytest.raises(ValueError, match="BOM"):
        load_dashboard_history_report_trend(path)


def test_trailing_newline_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data + b"\n", name="nl.json")
    with pytest.raises(ValueError, match="trailing newline"):
        load_dashboard_history_report_trend(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}", name="utf8.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize(
    "data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"']
)
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data, name="bad.json")
    with pytest.raises(ValueError):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'"regressed":1', f'"regressed":{token}'.encode(), 1
    )
    path = write_bytes(tmp_path, mangled, name="const.json")
    with pytest.raises(ValueError):
        load_dashboard_history_report_trend(path)


def test_duplicate_keys_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(b'{"count"', b'{"count":1,"count"', 1)
    path = write_bytes(tmp_path, mangled, name="dup.json")
    with pytest.raises(ValueError, match="duplicate"):
        load_dashboard_history_report_trend(path)


def test_missing_top_key_rejected(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    del doc["quality"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="missing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report_trend(path)


def test_extra_top_key_rejected(tmp_path):
    _, data = write_valid(
        tmp_path, trend_doc([change(1, 0.0, 0.0, "pass")])
    )
    path = write_bytes(
        tmp_path, data[:-1] + b',"extra":1}', name="extra.json"
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report_trend(path)


def test_wrong_top_key_order_rejected(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    reordered = {key: doc[key] for key in reversed(KEYS)}
    path = write_bytes(
        tmp_path,
        json.dumps(reordered, separators=(",", ":")).encode(),
        name="order.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report_trend(path)


def test_missing_item_key_rejected(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    del doc["changes"][0]["volatility_delta"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="imissing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report_trend(path)


def test_wrong_item_key_order_rejected(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
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
        load_dashboard_history_report_trend(path)


def test_count_must_be_non_bool_int(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    raw = json.dumps(doc, separators=(",", ":")).replace(
        '"count":2', '"count":true'
    )
    path = write_bytes(tmp_path, raw.encode(), name="countbool.json")
    with pytest.raises(
        ValueError, match="count must be a non-bool int"
    ):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("count", [0, 1, -3])
def test_count_must_be_at_least_two(tmp_path, count):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")], count=count)
    doc["changes"] = []
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="count.json",
    )
    with pytest.raises(ValueError, match="count must be >= 2"):
        load_dashboard_history_report_trend(path)


def test_changes_must_be_array(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["changes"] = {"0": change(1, 0.0, 0.0, "pass")}
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="array.json",
    )
    with pytest.raises(ValueError, match="changes must be a JSON array"):
        load_dashboard_history_report_trend(path)


def test_changes_length_must_be_count_minus_one(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["count"] = 3
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="length.json",
    )
    with pytest.raises(ValueError, match="count - 1 elements"):
        load_dashboard_history_report_trend(path)


def test_index_must_run_consecutively_from_one(tmp_path):
    doc = trend_doc(
        [
            change(1, 0.0, 0.0, "pass"),
            change(3, 0.0, 0.0, "pass"),
        ],
        worst=change(1, 0.0, 0.0, "pass"),
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="index.json",
    )
    with pytest.raises(
        ValueError, match="index must run consecutively"
    ):
        load_dashboard_history_report_trend(path)


def test_index_must_be_non_bool_int(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["changes"][0]["index"] = True
    doc["worst"] = dict(doc["changes"][0])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="indexbool.json",
    )
    with pytest.raises(ValueError, match="index must be a non-bool int"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("name", ["stability_delta", "volatility_delta"])
def test_delta_must_be_float(tmp_path, name):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["changes"][0][name] = 0
    doc["worst"] = dict(doc["changes"][0])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="dint.json",
    )
    with pytest.raises(ValueError, match=rf"{name} must be a float"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("name", ["stability_delta", "volatility_delta"])
def test_delta_must_be_finite(tmp_path, name):
    _, data = write_valid(
        tmp_path, trend_doc([change(1, 0.0, 0.0, "pass")])
    )
    mangled = data.replace(
        f'"{name}":0.0'.encode(), f'"{name}":1e999'.encode(), 1
    )
    path = write_bytes(tmp_path, mangled, name="dinf.json")
    with pytest.raises(ValueError, match=rf"{name} must be finite"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("name", ["stability_delta", "volatility_delta"])
@pytest.mark.parametrize("value", [-1.5, 1.5])
def test_delta_must_be_in_range(tmp_path, name, value):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["changes"][0][name] = value
    doc["worst"] = dict(doc["changes"][0])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="range.json",
    )
    with pytest.raises(ValueError, match=rf"{name} must be in \[-1, 1\]"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("name", ["stability_delta", "volatility_delta"])
def test_delta_must_have_at_most_six_decimals(tmp_path, name):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["changes"][0][name] = 0.1234567
    doc["worst"] = dict(doc["changes"][0])
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="digits.json",
    )
    with pytest.raises(ValueError, match="at most 6 decimals"):
        load_dashboard_history_report_trend(path)


@pytest.mark.parametrize("name", ["stability_delta", "volatility_delta"])
def test_delta_negative_zero_rejected(tmp_path, name):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    raw = dump(doc).replace(
        f'"{name}":0.0'.encode(), f'"{name}":-0.0'.encode(), 1
    )
    path = write_bytes(tmp_path, raw, name="dneg0.json")
    with pytest.raises(ValueError, match="negative zero"):
        load_dashboard_history_report_trend(path)


def test_item_quality_enum(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "maybe")], regressed=0)
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="qenum.json",
    )
    with pytest.raises(
        ValueError, match="quality must be 'pass' or 'fail'"
    ):
        load_dashboard_history_report_trend(path)


def test_regressed_must_be_non_bool_int(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    doc["regressed"] = False
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="regbool.json",
    )
    with pytest.raises(
        ValueError, match="regressed must be a non-bool int"
    ):
        load_dashboard_history_report_trend(path)


def test_regressed_must_equal_fail_count(tmp_path):
    doc = trend_doc(
        [
            change(1, 0.0, 0.0, "pass"),
            change(2, 0.0, 0.0, "fail"),
        ],
        regressed=2,
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="reg.json",
    )
    with pytest.raises(
        ValueError, match="regressed must equal the number"
    ):
        load_dashboard_history_report_trend(path)


def test_worst_must_equal_a_changes_item(tmp_path):
    items = [
        change(1, 0.0, 0.0, "pass"),
        change(2, -0.5, 0.5, "fail"),
    ]
    doc = trend_doc(items, worst=change(3, -0.5, 0.5, "fail"))
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="worst.json",
    )
    with pytest.raises(
        ValueError, match="worst must equal one of"
    ):
        load_dashboard_history_report_trend(path)


def test_quality_pass_requires_zero_regressed(tmp_path):
    doc = trend_doc(
        [change(1, -0.1, 0.1, "fail")], regressed=1, quality="pass"
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
        load_dashboard_history_report_trend(path)


def test_quality_fail_requires_nonzero_regressed(tmp_path):
    doc = trend_doc(
        [change(1, 0.0, 0.0, "pass")], regressed=0, quality="fail"
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
        load_dashboard_history_report_trend(path)


def test_non_canonical_spacing_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(
        tmp_path, data.replace(b":", b": ", 1), name="space.json"
    )
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history_report_trend(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    doc = trend_doc([change(1, 0.0, 0.0, "pass")])
    data = dump(doc).replace(
        b'"quality":"pass"', b'"quality":"p\\u0061ss"', 1
    )
    path = write_bytes(tmp_path, data, name="unicode.json")
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history_report_trend(path)


def _report_bytes(snapshots, stability, volatility):
    regressed = 0 if stability == 1.0 else 1
    quality = "pass" if regressed == 0 else "fail"
    worst_verdict = "pass" if regressed == 0 else "fail"
    report_obj = {
        "schema_version": 1,
        "source": {"path": "in.json", "inputs": ["a", "b"]},
        "history": {
            "count": snapshots,
            "changes": [
                {
                    "index": 1,
                    "passed_delta": 0,
                    "regressed_delta": 0,
                    "ratio_delta": volatility,
                    "quality": worst_verdict,
                }
            ],
            "regressed": regressed,
            "worst": {
                "index": 1,
                "passed_delta": 0,
                "regressed_delta": 0,
                "ratio_delta": volatility,
                "quality": worst_verdict,
            },
            "quality": quality,
        },
        "summary": {
            "snapshots": snapshots,
            "regressed": regressed,
            "stability": stability,
            "volatility": volatility,
            "longest_regression": regressed,
            "worst_index": 1,
        },
        "quality": quality,
    }
    return json.dumps(
        report_obj,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_roundtrip_matches_dashboard_history_report_trend(tmp_path):
    p1 = tmp_path / "r1.json"
    p1.write_bytes(_report_bytes(2, 0.0, 0.5))
    p2 = tmp_path / "r2.json"
    p2.write_bytes(_report_bytes(2, 1.0, 0.0))

    data = serialize_dashboard_history_report_trend([str(p1), str(p2)])
    trend_path = write_bytes(tmp_path, data, name="trend.json")

    result = load_dashboard_history_report_trend(trend_path)
    expected = dashboard_history_report_trend([str(p1), str(p2)])
    assert result == expected
    assert result["worst"] is result["changes"][0]
    assert isinstance(result["changes"], tuple)
