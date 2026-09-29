"""Tests for product.load_trend_dashboard."""

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    load_overview_comparison_report_trend,
    load_trend_dashboard,
    serialize_trend_dashboard,
)

TREND_KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "failed_delta",
    "regressed_delta",
    "passed_delta",
    "quality",
]
SUMMARY_KEYS = ["reports", "passed", "regressed", "ratio", "worst"]


def item(index, failed_delta, regressed_delta, passed_delta, quality):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "regressed_delta": regressed_delta,
        "passed_delta": passed_delta,
        "quality": quality,
    }


def trend_doc(changes):
    regressed = sum(1 for c in changes if c["quality"] == "fail")
    worst = min(
        changes,
        key=lambda c: (
            c["passed_delta"],
            -c["failed_delta"],
            -c["regressed_delta"],
            c["index"],
        ),
    )
    quality = "pass" if regressed == 0 else "fail"
    return {
        "count": len(changes) + 1,
        "changes": changes,
        "regressed": regressed,
        "worst": worst,
        "quality": quality,
    }


def write_trend(tmp_path, doc=None, name="trend.json"):
    if doc is None:
        doc = trend_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 2, -1, "fail"),
                item(3, 0, -1, 0, "pass"),
            ]
        )
    path = tmp_path / name
    path.write_bytes(
        product_mod._dump_overview_comparison_report_trend(doc)
    )
    return str(path)


def write_bytes(tmp_path, data, name="dashboard.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path):
    trend_path = write_trend(tmp_path)
    data = serialize_trend_dashboard(trend_path)
    return write_bytes(tmp_path, data), data


def test_exported():
    assert "load_trend_dashboard" in product_mod.__all__
    assert product_mod.load_trend_dashboard is load_trend_dashboard


def test_roundtrip_structure(tmp_path):
    path, data = write_valid(tmp_path)

    result = load_trend_dashboard(path)

    assert list(result.keys()) == ["trend", "summary", "quality"]
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
    assert trend["worst"] is changes[1]
    assert list(result["summary"].keys()) == SUMMARY_KEYS
    assert result["summary"] == {
        "reports": 4,
        "passed": 2,
        "regressed": 1,
        "ratio": 0.666667,
        "worst": 2,
    }
    assert result["quality"] == "fail"
    assert data == product_mod._dump_overview_comparison_report_trend(result)


def test_matches_trend_dashboard(tmp_path):
    trend_path = write_trend(tmp_path)
    dashboard_path = write_bytes(
        tmp_path, serialize_trend_dashboard(trend_path)
    )

    loaded = load_trend_dashboard(dashboard_path)
    trend = load_overview_comparison_report_trend(trend_path)

    assert loaded["trend"] == trend
    assert loaded["trend"]["worst"] is loaded["trend"]["changes"][
        trend["worst"]["index"] - 1
    ]


def test_all_pass(tmp_path):
    trend_path = write_trend(
        tmp_path,
        trend_doc([item(1, 0, 0, 2, "pass"), item(2, 0, 0, 1, "pass")]),
    )
    path = write_bytes(
        tmp_path, serialize_trend_dashboard(trend_path), "allpass.json"
    )

    result = load_trend_dashboard(path)

    assert result["summary"] == {
        "reports": 3,
        "passed": 2,
        "regressed": 0,
        "ratio": 1.0,
        "worst": 2,
    }
    assert result["quality"] == "pass"
    assert result["trend"]["quality"] == "pass"


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
    _, data = write_valid(tmp_path)
    mangled = data.replace(b'"reports":4', b'"reports":3', 1)
    path = write_bytes(tmp_path, mangled, "bad.json")

    with pytest.raises(ValueError):
        load_trend_dashboard(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data, "bom.json")
    with pytest.raises(ValueError, match="BOM"):
        load_trend_dashboard(path)


def test_trailing_newline_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(tmp_path, data + b"\n", "nl.json")
    with pytest.raises(ValueError, match="trailing newline"):
        load_trend_dashboard(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}", "utf8.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_trend_dashboard(path)


@pytest.mark.parametrize(
    "data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"']
)
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data, "json.json")
    with pytest.raises(ValueError):
        load_trend_dashboard(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'"ratio":0.666667', f'"ratio":{token}'.encode(), 1
    )
    path = write_bytes(tmp_path, mangled, "const.json")
    with pytest.raises(ValueError):
        load_trend_dashboard(path)


def test_duplicate_keys_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'{"reports":4', b'{"reports":4,"reports":4', 1
    )
    path = write_bytes(tmp_path, mangled, "dup.json")
    with pytest.raises(ValueError, match="duplicate"):
        load_trend_dashboard(path)


def _dashboard_dict(tmp_path):
    trend_path = write_trend(tmp_path)
    document = json.loads(serialize_trend_dashboard(trend_path))
    return document


def _raw(document):
    return json.dumps(
        document, ensure_ascii=False, separators=(",", ":")
    ).encode()


def test_missing_top_key_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    del document["quality"]
    path = write_bytes(tmp_path, _raw(document), "missing.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_extra_top_key_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    reordered = dict(document)
    reordered["extra"] = 1
    path = write_bytes(tmp_path, _raw(reordered), "extra.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_wrong_top_key_order_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    reordered = {key: document[key] for key in reversed(document)}
    path = write_bytes(tmp_path, _raw(reordered), "order.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


def test_wrong_summary_key_order_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"] = {
        key: document["summary"][key]
        for key in reversed(document["summary"])
    }
    path = write_bytes(tmp_path, _raw(document), "sorder.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_trend_dashboard(path)


@pytest.mark.parametrize("name", ["reports", "passed", "regressed", "worst"])
def test_summary_ints_reject_bool(tmp_path, name):
    document = _dashboard_dict(tmp_path)
    raw = _raw(document)
    needle = f'"{name}":{document["summary"][name]}'.encode()
    mangled = raw.replace(needle, f'"{name}":true'.encode(), 1)
    path = write_bytes(tmp_path, mangled, "bool.json")
    with pytest.raises(
        ValueError, match=f"{name} must be a non-bool int"
    ):
        load_trend_dashboard(path)


def test_ratio_must_be_float(tmp_path):
    document = _dashboard_dict(tmp_path)
    raw = _raw(document).replace(b'"ratio":0.666667', b'"ratio":1', 1)
    path = write_bytes(tmp_path, raw, "ratio-int.json")
    with pytest.raises(ValueError, match="ratio must be a float"):
        load_trend_dashboard(path)


def test_ratio_must_be_finite(tmp_path):
    document = _dashboard_dict(tmp_path)
    raw = _raw(document).replace(
        b'"ratio":0.666667', b'"ratio":1e999', 1
    )
    path = write_bytes(tmp_path, raw, "ratio-inf.json")
    with pytest.raises(ValueError, match="ratio must be finite"):
        load_trend_dashboard(path)


def test_ratio_at_most_six_decimals(tmp_path):
    document = _dashboard_dict(tmp_path)
    raw = _raw(document).replace(
        b'"ratio":0.666667', b'"ratio":0.6666667', 1
    )
    path = write_bytes(tmp_path, raw, "ratio-prec.json")
    with pytest.raises(ValueError, match="at most 6 decimals"):
        load_trend_dashboard(path)


def test_ratio_negative_zero_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    # all-pass case would serialize ratio as 1.0; use a value that is
    # zero by building a trend whose rounded ratio is zero.
    changes = [
        item(1, 1, 0, -1, "fail"),
        item(2, 1, 0, -1, "fail"),
        item(3, 1, 0, -1, "fail"),
    ]
    trend_path = write_trend(tmp_path, trend_doc(changes), "zero.json")
    raw = serialize_trend_dashboard(trend_path)
    assert b'"ratio":0.0' in raw
    mangled = raw.replace(b'"ratio":0.0', b'"ratio":-0.0', 1)
    path = write_bytes(tmp_path, mangled, "negzero.json")
    with pytest.raises(ValueError, match="negative zero"):
        load_trend_dashboard(path)


def test_reports_must_equal_trend_count(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"]["reports"] = 3
    path = write_bytes(tmp_path, _raw(document), "reports.json")
    with pytest.raises(ValueError, match="reports must equal trend.count"):
        load_trend_dashboard(path)


def test_passed_must_equal_changes_minus_regressed(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"]["passed"] = 1
    path = write_bytes(tmp_path, _raw(document), "passed.json")
    with pytest.raises(
        ValueError, match="passed must equal len.changes. - regressed"
    ):
        load_trend_dashboard(path)


def test_regressed_must_equal_trend_regressed(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"]["regressed"] = 2
    # also keep passed consistent so that check passes first order-wise
    document["summary"]["passed"] = 1
    path = write_bytes(tmp_path, _raw(document), "regressed.json")
    with pytest.raises(
        ValueError, match="regressed must equal trend.regressed"
    ):
        load_trend_dashboard(path)


def test_ratio_must_match_formula(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"]["ratio"] = 0.5
    path = write_bytes(tmp_path, _raw(document), "ratio.json")
    with pytest.raises(ValueError, match="ratio must equal"):
        load_trend_dashboard(path)


def test_worst_must_equal_trend_worst_index(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["summary"]["worst"] = 3
    path = write_bytes(tmp_path, _raw(document), "worst.json")
    with pytest.raises(
        ValueError, match="worst must equal trend.worst.index"
    ):
        load_trend_dashboard(path)


def test_top_quality_must_equal_trend_quality(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["quality"] = "pass"
    path = write_bytes(tmp_path, _raw(document), "quality.json")
    with pytest.raises(
        ValueError, match="quality must equal trend.quality"
    ):
        load_trend_dashboard(path)


def test_embedded_trend_violation_rejected(tmp_path):
    document = _dashboard_dict(tmp_path)
    document["trend"]["count"] = 3
    path = write_bytes(tmp_path, _raw(document), "trend.json")
    with pytest.raises(ValueError, match="count - 1 elements"):
        load_trend_dashboard(path)


def test_non_canonical_spacing_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    path = write_bytes(
        tmp_path, data.replace(b":", b": ", 1), "spacing.json"
    )
    with pytest.raises(ValueError, match="canonical"):
        load_trend_dashboard(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    _, data = write_valid(tmp_path)
    mangled = data.replace(
        b'"quality":"fail"', b'"quality":"f\\u0061il"', 1
    )
    path = write_bytes(tmp_path, mangled, "unicode.json")
    with pytest.raises(ValueError, match="canonical"):
        load_trend_dashboard(path)


def test_end_to_end_with_serializer(tmp_path):
    trend_path = write_trend(tmp_path)
    data = serialize_trend_dashboard(trend_path)
    path = write_bytes(tmp_path, data, "e2e.json")

    result = load_trend_dashboard(path)

    assert product_mod._dump_overview_comparison_report_trend(result) == data
    assert (
        result["trend"]["worst"]
        is result["trend"]["changes"][result["summary"]["worst"] - 1]
    )
