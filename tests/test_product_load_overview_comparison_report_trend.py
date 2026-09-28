"""Tests for product.load_overview_comparison_report_trend."""

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    load_overview_comparison_report_trend,
    serialize_overview_comparison_report_trend,
)

KEYS = ["count", "changes", "regressed", "worst", "quality"]
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


def dump(doc):
    return product_mod._dump_overview_comparison_report_trend(doc)


def write_bytes(tmp_path, data, name="trend.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path, doc=None):
    if doc is None:
        doc = trend_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 2, -1, "fail"),
                item(3, 0, -1, 0, "pass"),
            ]
        )
    data = dump(doc)
    return write_bytes(tmp_path, data), data


def test_exported():
    assert "load_overview_comparison_report_trend" in product_mod.__all__
    assert (
        product_mod.load_overview_comparison_report_trend
        is load_overview_comparison_report_trend
    )


def test_roundtrip_structure(tmp_path):
    doc = trend_doc(
        [
            item(1, 0, 0, 1, "pass"),
            item(2, 1, 2, -1, "fail"),
            item(3, 0, -1, 0, "pass"),
        ]
    )
    path, data = write_valid(tmp_path, doc)

    result = load_overview_comparison_report_trend(path)

    assert list(result.keys()) == KEYS
    assert result["count"] == 4
    assert result["regressed"] == 1
    assert result["quality"] == "fail"
    changes = result["changes"]
    assert isinstance(changes, tuple)
    assert len(changes) == 3
    for i, change in enumerate(changes):
        assert list(change.keys()) == ITEM_KEYS
        assert change["index"] == i + 1
    # worst references the matching tuple item, never a copy
    assert result["worst"] is changes[1]
    assert data == dump(result)


def test_all_pass(tmp_path):
    doc = trend_doc([item(1, 0, 0, 2, "pass"), item(2, 0, 1, 0, "pass")])
    path, _ = write_valid(tmp_path, doc)

    result = load_overview_comparison_report_trend(path)

    assert result["regressed"] == 0
    assert result["quality"] == "pass"
    assert result["worst"]["quality"] == "pass"


def test_minimum_count_two(tmp_path):
    doc = trend_doc([item(1, -1, 0, 1, "pass")], count=2)
    path, _ = write_valid(tmp_path, doc)

    result = load_overview_comparison_report_trend(path)

    assert result["count"] == 2
    assert len(result["changes"]) == 1


def test_worst_tie_break_order(tmp_path):
    # equal passed_delta/failed_delta/regressed_delta -> smallest index
    doc = trend_doc(
        [
            item(1, 0, 0, 0, "fail"),
            item(2, 0, 0, 0, "fail"),
            item(3, 0, 0, 1, "pass"),
        ]
    )
    path, _ = write_valid(tmp_path, doc)

    result = load_overview_comparison_report_trend(path)

    assert result["worst"]["index"] == 1


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_overview_comparison_report_trend(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_overview_comparison_report_trend("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_overview_comparison_report_trend(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_overview_comparison_report_trend(str(tmp_path))


def test_file_not_modified_on_success(tmp_path):
    path, data = write_valid(tmp_path)
    before = os.stat(path)

    load_overview_comparison_report_trend(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass"), item(2, 1, 0, -1, "fail")])
    mangled = dump(doc).replace(b'"count":3', b'"count":2', 1)
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        load_overview_comparison_report_trend(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + dump(doc))
    with pytest.raises(ValueError, match="BOM"):
        load_overview_comparison_report_trend(path)


def test_trailing_newline_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    path = write_bytes(tmp_path, dump(doc) + b"\n")
    with pytest.raises(ValueError, match="trailing newline"):
        load_overview_comparison_report_trend(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_overview_comparison_report_trend(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data)
    with pytest.raises(ValueError):
        load_overview_comparison_report_trend(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    data = dump(doc).replace(b'"count":2', f'"count":{token}'.encode(), 1)
    path = write_bytes(tmp_path, data)
    with pytest.raises(ValueError):
        load_overview_comparison_report_trend(path)


def test_duplicate_keys_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    data = dump(doc).replace(
        b'{"count"', b'{"count":2,"count"', 1
    )
    path = write_bytes(tmp_path, data)
    with pytest.raises(ValueError, match="duplicate"):
        load_overview_comparison_report_trend(path)


def test_missing_top_key_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    del doc["quality"]
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview_comparison_report_trend(path)


def test_extra_top_key_rejected(tmp_path):
    data = dump(trend_doc([item(1, 0, 0, 1, "pass")]))
    path = write_bytes(tmp_path, data[:-1] + b',"extra":1}')
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview_comparison_report_trend(path)


def test_wrong_top_key_order_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    reordered = {key: doc[key] for key in reversed(KEYS)}
    path = write_bytes(
        tmp_path, json.dumps(reordered, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview_comparison_report_trend(path)


def test_wrong_item_key_order_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    doc["changes"][0] = {
        "index": 1,
        "passed_delta": 1,
        "failed_delta": 0,
        "regressed_delta": 0,
        "quality": "pass",
    }
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview_comparison_report_trend(path)


def test_count_bool_rejected(tmp_path):
    data = dump(trend_doc([item(1, 0, 0, 1, "pass")]))
    path = write_bytes(tmp_path, data.replace(b'"count":2', b'"count":true', 1))
    with pytest.raises(ValueError, match="count must be a non-bool int"):
        load_overview_comparison_report_trend(path)


@pytest.mark.parametrize("bad_count", [-1, 0, 1])
def test_count_must_be_at_least_two(tmp_path, bad_count):
    doc = trend_doc([item(1, 0, 0, 1, "pass")], count=bad_count)
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="count must be >= 2"):
        load_overview_comparison_report_trend(path)


def test_changes_length_must_match_count(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")], count=3)
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="count - 1 elements"):
        load_overview_comparison_report_trend(path)


@pytest.mark.parametrize(
    "name",
    ["index", "failed_delta", "regressed_delta", "passed_delta"],
)
def test_item_ints_reject_bool(tmp_path, name):
    doc = trend_doc([item(1, 0, 0, 0, "pass")])
    raw = dump(doc)
    needle = b'"index":1' if name == "index" else f'"{name}":0'.encode()
    replacement = f'"{name}":true'.encode()
    path = write_bytes(tmp_path, raw.replace(needle, replacement, 1))
    with pytest.raises(ValueError, match=f"{name} must be a non-bool int"):
        load_overview_comparison_report_trend(path)


def test_index_must_run_consecutively_from_one(tmp_path):
    doc = trend_doc(
        [item(1, 0, 0, 1, "pass"), item(3, 0, 0, 1, "pass")]
    )
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="index must run consecutively"):
        load_overview_comparison_report_trend(path)


def test_item_quality_enum(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "maybe")], regressed=0, quality="pass")
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="quality must be 'pass' or 'fail'"):
        load_overview_comparison_report_trend(path)


def test_regressed_bool_rejected(tmp_path):
    data = dump(
        trend_doc([item(1, 0, 0, 1, "pass")])
    )
    path = write_bytes(
        tmp_path, data.replace(b'"regressed":0', b'"regressed":false', 1)
    )
    with pytest.raises(ValueError, match="regressed must be a non-bool int"):
        load_overview_comparison_report_trend(path)


def test_regressed_must_equal_fail_count(tmp_path):
    doc = trend_doc([item(1, 1, 0, -1, "fail")], regressed=0)
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="regressed must equal"):
        load_overview_comparison_report_trend(path)


def test_worst_must_be_minimizing_item(tmp_path):
    changes = [item(1, 0, 0, 1, "pass"), item(2, 1, 2, -1, "fail")]
    doc = trend_doc(changes, worst=changes[0])
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="worst must be the changes item"):
        load_overview_comparison_report_trend(path)


def test_top_quality_must_follow_regressed(tmp_path):
    doc = trend_doc([item(1, 1, 0, -1, "fail")], quality="pass")
    path = write_bytes(
        tmp_path, json.dumps(doc, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="quality must be 'pass' exactly"):
        load_overview_comparison_report_trend(path)


def test_non_canonical_spacing_rejected(tmp_path):
    data = dump(trend_doc([item(1, 0, 0, 1, "pass")]))
    path = write_bytes(tmp_path, data.replace(b":", b": ", 1))
    with pytest.raises(ValueError, match="canonical"):
        load_overview_comparison_report_trend(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    doc = trend_doc([item(1, 0, 0, 1, "pass")])
    data = dump(doc).replace(
        b'"quality":"pass"', b'"quality":"p\\u0061ss"', 1
    )
    path = write_bytes(tmp_path, data)
    with pytest.raises(ValueError, match="canonical"):
        load_overview_comparison_report_trend(path)


def test_end_to_end_with_serializer(tmp_path):
    # The loader accepts the real serializer output built from report files.
    def comparison_report(failed, regressed_delta, passed_delta, quality):
        return {
            "schema_version": 1,
            "source": {"path": "x.json", "kind": "overview_comparison"},
            "summary": {
                "count": 3,
                "failed": failed,
                "regressed_delta": regressed_delta,
                "passed_delta": passed_delta,
            },
            "worst": {
                "index": 1,
                "regressed_delta": regressed_delta,
                "passed_delta": passed_delta,
                "quality": quality,
            },
            "quality": quality,
        }

    reports = [
        comparison_report(0, 0, 2, "pass"),
        comparison_report(1, 1, 1, "fail"),
        comparison_report(1, 0, 1, "fail"),
    ]
    report_paths = []
    for i, report in enumerate(reports):
        rp = tmp_path / f"report{i}.json"
        rp.write_bytes(
            json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()
        )
        report_paths.append(str(rp))

    trend = product_mod.overview_comparison_report_trend(report_paths)
    data = serialize_overview_comparison_report_trend(report_paths)
    trend_path = tmp_path / "trend.json"
    trend_path.write_bytes(data)

    result = load_overview_comparison_report_trend(str(trend_path))

    assert result == trend
    assert result["worst"] is result["changes"][trend["worst"]["index"] - 1]
