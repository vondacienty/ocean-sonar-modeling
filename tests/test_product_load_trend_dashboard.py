"""Tests for product.load_trend_dashboard."""

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    load_trend_dashboard,
    serialize_trend_dashboard,
    trend_dashboard,
)

KEYS = ["trend", "summary", "quality"]
SUMMARY_KEYS = ["reports", "passed", "regressed", "ratio", "worst"]
TREND_KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "failed_delta",
    "regressed_delta",
    "passed_delta",
    "quality",
]


def item(index, failed_delta, regressed_delta, passed_delta, quality):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "regressed_delta": regressed_delta,
        "passed_delta": passed_delta,
        "quality": quality,
    }


def trend_doc(changes, regressed=None, worst=None, quality=None, count=None):
    if regressed is None:
        regressed = sum(1 for c in changes if c["quality"] == "fail")
    if worst is None:
        worst = min(
            changes,
            key=lambda c: (
                c["passed_delta"],
                -c["failed_delta"],
                -c["regressed_delta"],
                c["index"],
            ),
        )
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


def dashboard_doc(changes):
    trend = trend_doc(changes)
    n = len(changes)
    r = trend["regressed"]
    p = n - r
    ratio = round(float(p / n), 6)
    if ratio == 0:
        ratio = 0.0
    return {
        "trend": trend,
        "summary": {
            "reports": trend["count"],
            "passed": p,
            "regressed": r,
            "ratio": ratio,
            "worst": trend["worst"]["index"],
        },
        "quality": trend["quality"],
    }


def dump(doc):
    return product_mod._dump_overview_comparison_report_trend(doc)


def write_bytes(tmp_path, data, name="dashboard.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path, doc=None):
    if doc is None:
        doc = dashboard_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 2, -1, "fail"),
                item(3, 0, -1, 0, "pass"),
            ]
        )
    data = dump(doc)
    return write_bytes(tmp_path, data), data


def write_trend(tmp_path, doc):
    path = tmp_path / "trend.json"
    path.write_bytes(dump(doc))
    return str(path)


def test_exported():
    assert "load_trend_dashboard" in product_mod.__all__
    assert product_mod.load_trend_dashboard is load_trend_dashboard


def test_roundtrip_structure(tmp_path):
    path, data = write_valid(tmp_path)

    result = load_trend_dashboard(path)

    assert list(result.keys()) == KEYS
    trend = result["trend"]
    assert list(trend.keys()) == TREND_KEYS
    assert trend["count"] == 4
    assert trend["regressed"] == 1
    assert trend["quality"] == "fail"
    changes = trend["changes"]
    assert isinstance(changes, tuple)
    assert len(changes) == 3
    for i, change in enumerate(changes):
        assert list(change.keys()) == ITEM_KEYS
        assert change["index"] == i + 1
    # worst references the matching tuple item, never a copy
    assert trend["worst"] is changes[1]

    summary = result["summary"]
    assert list(summary.keys()) == SUMMARY_KEYS
    assert summary == {
        "reports": 4,
        "passed": 2,
        "regressed": 1,
        "ratio": round(2 / 3, 6),
        "worst": 2,
    }
    assert type(summary["reports"]) is int
    assert type(summary["passed"]) is int
    assert type(summary["regressed"]) is int
    assert type(summary["worst"]) is int
    assert type(summary["ratio"]) is float

    assert result["quality"] == "fail"
    assert data == dump(result)


def test_matches_trend_dashboard_output(tmp_path):
    trend_path = write_trend(
        tmp_path,
        trend_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 2, -1, "fail"),
                item(3, 0, -1, 0, "pass"),
            ]
        ),
    )
    dashboard_path = write_bytes(
        tmp_path, serialize_trend_dashboard(trend_path)
    )

    assert load_trend_dashboard(dashboard_path) == trend_dashboard(trend_path)


def test_all_pass_ratio_one(tmp_path):
    path, _ = write_valid(
        tmp_path,
        dashboard_doc([item(1, 0, 0, 2, "pass"), item(2, 0, 1, 0, "pass")]),
    )

    result = load_trend_dashboard(path)

    assert result["summary"]["ratio"] == 1.0
    assert result["quality"] == "pass"
    assert result["trend"]["quality"] == "pass"


def test_all_fail_ratio_zero(tmp_path):
    path, _ = write_valid(
        tmp_path,
        dashboard_doc(
            [
                item(1, 1, 0, -1, "fail"),
                item(2, 0, 1, -2, "fail"),
            ]
        ),
    )

    result = load_trend_dashboard(path)

    assert result["summary"]["ratio"] == 0.0
    assert result["quality"] == "fail"


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_trend_dashboard(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_trend_dashboard("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trend_dashboard(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_trend_dashboard(str(tmp_path))


def test_file_not_modified_on_success(tmp_path):
    path, data = write_valid(tmp_path)
    before = os.stat(path)

    load_trend_dashboard(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path):
    doc = dashboard_doc(
        [item(1, 0, 0, 1, "pass"), item(2, 1, 0, -1, "fail")]
    )
    mangled = dump(doc).replace(b'"reports":3', b'"reports":2', 1)
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        load_trend_dashboard(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data, name="bom.json")
    with pytest.raises(ValueError, match="BOM"):
        load_trend_dashboard(path)


def test_trailing_newline_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data + b"\n", name="nl.json")
    with pytest.raises(ValueError, match="trailing newline"):
        load_trend_dashboard(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}", name="utf8.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_trend_dashboard(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data, name="bad.json")
    with pytest.raises(ValueError):
        load_trend_dashboard(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'"reports":4', f'"reports":{token}'.encode(), 1
    )
    path = write_bytes(tmp_path, mangled, name="const.json")
    with pytest.raises(ValueError):
        load_trend_dashboard(path)


def test_duplicate_keys_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(b'{"trend"', b'{"trend":1,"trend"', 1)
    path = write_bytes(tmp_path, mangled, name="dup.json")
    with pytest.raises(ValueError, match="duplicate"):
        load_trend_dashboard(path)


def test_missing_top_key_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    del doc["quality"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="missing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_extra_top_key_rejected(tmp_path):
    _, data = write_valid(
        tmp_path, dashboard_doc([item(1, 0, 0, 1, "pass")])
    )
    path = write_bytes(tmp_path, data[:-1] + b',"extra":1}', name="extra.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_wrong_top_key_order_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    reordered = {key: doc[key] for key in reversed(KEYS)}
    path = write_bytes(
        tmp_path,
        json.dumps(reordered, separators=(",", ":")).encode(),
        name="order.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_trend_contract_enforced(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["trend"]["count"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="trendbad.json",
    )
    with pytest.raises(ValueError, match="count must be >= 2"):
        load_trend_dashboard(path)


def test_missing_summary_key_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    del doc["summary"]["ratio"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="smissing.json",
    )
    with pytest.raises(ValueError, match="summary keys must be in the order"):
        load_trend_dashboard(path)


def test_extra_summary_key_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"]["extra"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="sextra.json",
    )
    with pytest.raises(ValueError, match="summary keys must be in the order"):
        load_trend_dashboard(path)


def test_wrong_summary_key_order_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"] = {
        key: doc["summary"][key] for key in reversed(SUMMARY_KEYS)
    }
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="sorder.json",
    )
    with pytest.raises(ValueError, match="summary keys must be in the order"):
        load_trend_dashboard(path)


@pytest.mark.parametrize(
    "name",
    ["reports", "passed", "regressed", "worst"],
)
def test_summary_ints_reject_bool(tmp_path, name):
    doc = dashboard_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 0, 0, 0, "pass"),
        ]
    )
    doc["summary"][name] = True
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name=f"{name}bool.json",
    )
    with pytest.raises(ValueError, match=name):
        load_trend_dashboard(path)


def test_summary_reports_must_equal_count(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"]["reports"] = 9
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="reports.json",
    )
    with pytest.raises(ValueError, match="summary.reports must equal"):
        load_trend_dashboard(path)


def test_summary_passed_must_equal_count_minus_regressed(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"]["passed"] = 0
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="passed.json",
    )
    with pytest.raises(ValueError, match="summary.passed must equal"):
        load_trend_dashboard(path)


def test_summary_regressed_must_equal_trend_regressed(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"]["regressed"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="regressed.json",
    )
    with pytest.raises(ValueError, match="regressed must equal"):
        load_trend_dashboard(path)


def test_summary_worst_must_equal_trend_worst_index(tmp_path):
    doc = dashboard_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 2, -1, "fail"),
        ]
    )
    doc["summary"]["worst"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="worst.json",
    )
    with pytest.raises(ValueError, match="summary.worst must equal"):
        load_trend_dashboard(path)


def test_ratio_must_be_float(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    doc["summary"]["ratio"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="ratioint.json",
    )
    with pytest.raises(ValueError, match="summary.ratio must be a float"):
        load_trend_dashboard(path)


def test_ratio_must_be_finite(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(b'"ratio":0.666667', b'"ratio":1e999', 1)
    path = write_bytes(tmp_path, mangled, name="ratioinf.json")
    with pytest.raises(ValueError, match="summary.ratio must be finite"):
        load_trend_dashboard(path)


def test_ratio_negative_zero_rejected(tmp_path):
    doc = dashboard_doc(
        [
            item(1, 1, 0, -1, "fail"),
            item(2, 0, 1, -2, "fail"),
        ]
    )
    raw = dump(doc)
    # the canonical dump normalizes -0.0 to 0.0; splice the raw token in
    mangled = raw.replace(b'"ratio":0.0', b'"ratio":-0.0', 1)
    path = write_bytes(tmp_path, mangled, name="rationeg0.json")
    with pytest.raises(ValueError, match="negative zero"):
        load_trend_dashboard(path)


def test_ratio_wrong_value_rejected(tmp_path):
    doc = dashboard_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 2, -1, "fail"),
        ]
    )
    doc["summary"]["ratio"] = 0.25
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="ratioval.json",
    )
    with pytest.raises(ValueError, match="summary.ratio must equal"):
        load_trend_dashboard(path)


def test_quality_must_equal_trend_quality(tmp_path):
    doc = dashboard_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 2, -1, "fail"),
        ]
    )
    doc["quality"] = "pass"
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="quality.json",
    )
    with pytest.raises(ValueError, match="quality must equal trend.quality"):
        load_trend_dashboard(path)


def test_non_canonical_spacing_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data.replace(b":", b": ", 1), name="space.json")
    with pytest.raises(ValueError, match="canonical"):
        load_trend_dashboard(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    doc = dashboard_doc([item(1, 0, 0, 1, "pass")])
    data = dump(doc).replace(
        b'"quality":"pass"', b'"quality":"p\\u0061ss"', 1
    )
    path = write_bytes(tmp_path, data, name="unicode.json")
    with pytest.raises(ValueError, match="canonical"):
        load_trend_dashboard(path)


def test_end_to_end_with_serializer(tmp_path):
    trend_path = write_trend(
        tmp_path,
        trend_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 2, -1, "fail"),
                item(3, 0, -1, 0, "pass"),
            ]
        ),
    )
    data = serialize_trend_dashboard(trend_path)
    dashboard_path = tmp_path / "dashboard.json"
    dashboard_path.write_bytes(data)

    result = load_trend_dashboard(str(dashboard_path))
    expected = trend_dashboard(trend_path)

    assert result == expected
    assert result["trend"]["worst"] is result["trend"]["changes"][1]
