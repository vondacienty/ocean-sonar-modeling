"""Tests for product.load_dashboard_history_report."""

from __future__ import annotations

import json
import math
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history,
    load_dashboard_history_report,
    serialize_dashboard_history,
    serialize_dashboard_history_report,
)

REPORT_KEYS = [
    "schema_version",
    "source",
    "history",
    "summary",
    "quality",
]
SOURCE_KEYS = ["path", "inputs"]
HISTORY_KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
    "quality",
]
SUMMARY_KEYS = [
    "snapshots",
    "regressed",
    "stability",
    "volatility",
    "longest_regression",
    "worst_index",
]


def trend_item(index, failed_delta, regressed_delta, passed_delta, quality):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "regressed_delta": regressed_delta,
        "passed_delta": passed_delta,
        "quality": quality,
    }


def dashboard_doc(changes):
    n = len(changes)
    r = sum(1 for c in changes if c["quality"] == "fail")
    p = n - r
    ratio = round(float(p / n), 6)
    if ratio == 0:
        ratio = 0.0
    worst = min(
        changes,
        key=lambda c: (
            c["passed_delta"],
            -c["failed_delta"],
            -c["regressed_delta"],
            c["index"],
        ),
    )
    return {
        "trend": {
            "count": n + 1,
            "changes": changes,
            "regressed": r,
            "worst": worst,
            "quality": "pass" if r == 0 else "fail",
        },
        "summary": {
            "reports": n + 1,
            "passed": p,
            "regressed": r,
            "ratio": ratio,
            "worst": worst["index"],
        },
        "quality": "pass" if r == 0 else "fail",
    }


def write_dashboard(tmp_path, doc, name):
    path = tmp_path / name
    path.write_bytes(product_mod._dump_overview_comparison_report_trend(doc))
    return str(path)


def snapshot_docs():
    passing = [trend_item(i + 1, 0, 0, 1, "pass") for i in range(3)]
    one_fail = [
        trend_item(1, 0, 0, 1, "pass"),
        trend_item(2, 1, 1, -1, "fail"),
        trend_item(3, 0, 0, 1, "pass"),
    ]
    two_fail = [
        trend_item(1, 1, 1, -1, "fail"),
        trend_item(2, 1, 1, -1, "fail"),
        trend_item(3, 0, 0, 1, "pass"),
    ]
    return dashboard_doc(passing), dashboard_doc(one_fail), dashboard_doc(
        two_fail
    )


def make_paths(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    return (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, two_fail, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
    )


def write_report(tmp_path, paths, name="report.json"):
    history_path = tmp_path / "history.json"
    history_path.write_bytes(serialize_dashboard_history(paths))
    data = serialize_dashboard_history_report(str(history_path), paths)
    report_path = tmp_path / name
    report_path.write_bytes(data)
    return str(report_path), data


def write_bytes(tmp_path, data, name="report.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def report_doc(paths, history_path=None):
    history = dashboard_history(paths)
    changes = history["changes"]
    longest = 0
    run = 0
    for item in changes:
        if item["quality"] == "fail":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    volatility = round(
        math.fsum(abs(item["ratio_delta"]) for item in changes)
        / len(changes),
        6,
    )
    return {
        "schema_version": 1,
        "source": {
            "path": history_path if history_path is not None else "history.json",
            "inputs": list(paths),
        },
        "history": {
            "count": history["count"],
            "changes": [dict(item) for item in changes],
            "regressed": history["regressed"],
            "worst": dict(history["worst"]),
            "quality": history["quality"],
        },
        "summary": {
            "snapshots": history["count"],
            "regressed": history["regressed"],
            "stability": round(1 - history["regressed"] / len(changes), 6),
            "volatility": volatility,
            "longest_regression": longest,
            "worst_index": history["worst"]["index"],
        },
        "quality": history["quality"],
    }


def dump(doc):
    return product_mod._dump_dashboard_history(doc)


def test_exported():
    assert "load_dashboard_history_report" in product_mod.__all__
    assert (
        product_mod.load_dashboard_history_report
        is load_dashboard_history_report
    )


def test_roundtrip_structure(tmp_path):
    paths = make_paths(tmp_path)
    path, data = write_report(tmp_path, paths)

    result = load_dashboard_history_report(path)

    assert list(result.keys()) == REPORT_KEYS
    assert result["schema_version"] == 1
    assert type(result["schema_version"]) is int

    assert list(result["source"].keys()) == SOURCE_KEYS
    assert type(result["source"]["path"]) is str
    assert isinstance(result["source"]["inputs"], tuple)
    assert list(result["source"]["inputs"]) == list(paths)
    assert len(result["source"]["inputs"]) >= 2
    for value in result["source"]["inputs"]:
        assert type(value) is str
        assert value != ""

    history = result["history"]
    assert list(history.keys()) == HISTORY_KEYS
    assert isinstance(history["changes"], tuple)
    assert len(history["changes"]) == history["count"] - 1
    for i, item in enumerate(history["changes"]):
        assert list(item.keys()) == ITEM_KEYS
        assert item["index"] == i + 1
    assert list(history["worst"].keys()) == ITEM_KEYS
    # worst references the matching tuple item, never a copy
    assert history["worst"] is history["changes"][history["worst"]["index"] - 1]

    assert list(result["summary"].keys()) == SUMMARY_KEYS
    assert data == dump(result)


def test_summary_matches_history(tmp_path):
    paths = make_paths(tmp_path)
    path, _ = write_report(tmp_path, paths)

    result = load_dashboard_history_report(path)
    history = dashboard_history(paths)
    changes = history["changes"]
    summary = result["summary"]

    assert summary["snapshots"] == history["count"]
    assert summary["regressed"] == history["regressed"]
    assert summary["stability"] == round(
        1 - history["regressed"] / len(changes), 6
    )
    assert type(summary["stability"]) is float
    assert summary["volatility"] == round(
        math.fsum(abs(item["ratio_delta"]) for item in changes)
        / len(changes),
        6,
    )
    assert type(summary["volatility"]) is float
    assert summary["worst_index"] == history["worst"]["index"]
    assert result["quality"] == history["quality"]
    assert result["history"] == history


def test_matches_serialize_report_bytes(tmp_path):
    paths = make_paths(tmp_path)
    history_path = tmp_path / "history.json"
    history_path.write_bytes(serialize_dashboard_history(paths))
    data = serialize_dashboard_history_report(str(history_path), paths)
    report_path = write_bytes(tmp_path, data)

    result = load_dashboard_history_report(report_path)
    assert dump(result) == data


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_dashboard_history_report(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_dashboard_history_report("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dashboard_history_report(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_dashboard_history_report(str(tmp_path))


def test_file_not_modified_on_success(tmp_path):
    paths = make_paths(tmp_path)
    path, data = write_report(tmp_path, paths)
    before = os.stat(path)

    load_dashboard_history_report(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    mangled = data.replace(b'"snapshots":4', b'"snapshots":3', 1)
    path = write_bytes(tmp_path, mangled, name="bad.json")

    with pytest.raises(ValueError):
        load_dashboard_history_report(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data, name="bom.json")
    with pytest.raises(ValueError, match="BOM"):
        load_dashboard_history_report(path)


def test_trailing_newline_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    path = write_bytes(tmp_path, data + b"\n", name="nl.json")
    with pytest.raises(ValueError, match="trailing newline"):
        load_dashboard_history_report(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}", name="utf8.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_dashboard_history_report(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data, name="bad.json")
    with pytest.raises(ValueError):
        load_dashboard_history_report(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, token):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    mangled = data.replace(
        b'"schema_version":1',
        f'"schema_version":{token}'.encode(),
        1,
    )
    path = write_bytes(tmp_path, mangled, name="const.json")
    with pytest.raises(ValueError):
        load_dashboard_history_report(path)


def test_duplicate_keys_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    mangled = data.replace(
        b'{"schema_version":1',
        b'{"schema_version":1,"schema_version":1',
        1,
    )
    path = write_bytes(tmp_path, mangled, name="dup.json")
    with pytest.raises(ValueError, match="duplicate"):
        load_dashboard_history_report(path)


def test_history_document_rejected(tmp_path):
    # A bare dashboard history is not a dashboard history report.
    paths = make_paths(tmp_path)
    data = serialize_dashboard_history(paths)
    path = write_bytes(tmp_path, data, name="history-only.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report(path)


def test_wrong_top_key_order_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    reordered = {key: doc[key] for key in reversed(REPORT_KEYS)}
    path = write_bytes(
        tmp_path,
        json.dumps(reordered, separators=(",", ":")).encode(),
        name="order.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report(path)


def test_extra_top_key_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    path = write_bytes(tmp_path, data[:-1] + b',"extra":1}', name="extra.json")
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report(path)


def test_missing_top_key_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    del doc["quality"]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="missing.json",
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_dashboard_history_report(path)


def test_schema_version_must_be_int(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["schema_version"] = 1.0
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="svfloat.json",
    )
    with pytest.raises(ValueError, match="schema_version must be a non-bool"):
        load_dashboard_history_report(path)


def test_schema_version_must_be_one(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["schema_version"] = 2
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="sv2.json",
    )
    with pytest.raises(ValueError, match="schema_version must be 1"):
        load_dashboard_history_report(path)


def test_source_wrong_key_order_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"] = {
        "inputs": doc["source"]["inputs"],
        "path": doc["source"]["path"],
    }
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="srcorder.json",
    )
    with pytest.raises(ValueError, match="source keys must be in the order"):
        load_dashboard_history_report(path)


def test_source_path_must_be_non_empty_str(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["path"] = ""
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="srcpath.json",
    )
    with pytest.raises(ValueError, match="source.path must not be empty"):
        load_dashboard_history_report(path)


def test_inputs_must_be_array(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["inputs"] = "not-an-array"
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="inputs.json",
    )
    with pytest.raises(ValueError, match="source.inputs must be a JSON array"):
        load_dashboard_history_report(path)


def test_inputs_must_have_at_least_two_items(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["inputs"] = [paths[0]]
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="one.json",
    )
    with pytest.raises(
        ValueError,
        match="source.inputs must have history.count elements",
    ):
        load_dashboard_history_report(path)


def test_inputs_item_must_be_str(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["inputs"][1] = 5
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="itemtype.json",
    )
    with pytest.raises(ValueError, match=r"source.inputs\[1\]: must be a str"):
        load_dashboard_history_report(path)


def test_inputs_item_must_not_be_empty(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["inputs"][0] = ""
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="empty.json",
    )
    with pytest.raises(ValueError, match=r"source.inputs\[0\]: must not be"):
        load_dashboard_history_report(path)


def test_inputs_length_must_equal_history_count(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["source"]["inputs"].append("extra.json")
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="length.json",
    )
    with pytest.raises(
        ValueError,
        match="source.inputs must have history.count elements",
    ):
        load_dashboard_history_report(path)


def test_invalid_nested_history_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["history"]["regressed"] = doc["history"]["regressed"] + 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="baddata.json",
    )
    with pytest.raises(ValueError, match="dashboard history"):
        load_dashboard_history_report(path)


def test_history_wrong_key_order_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["history"] = {
        key: doc["history"][key] for key in reversed(HISTORY_KEYS)
    }
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="horder.json",
    )
    with pytest.raises(ValueError, match="dashboard history keys must be"):
        load_dashboard_history_report(path)


def test_summary_wrong_key_order_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"] = {
        key: doc["summary"][key] for key in reversed(SUMMARY_KEYS)
    }
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="sumorder.json",
    )
    with pytest.raises(ValueError, match="summary keys must be in the order"):
        load_dashboard_history_report(path)


def test_snapshots_must_equal_count(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["snapshots"] += 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="snap.json",
    )
    with pytest.raises(ValueError, match="summary.snapshots must equal"):
        load_dashboard_history_report(path)


def test_regressed_must_equal_history(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["regressed"] += 1
    doc["summary"]["stability"] = round(
        1 - doc["summary"]["regressed"] / 3, 6
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="reg.json",
    )
    with pytest.raises(ValueError, match="summary.regressed must equal"):
        load_dashboard_history_report(path)


def test_stability_mismatch_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["stability"] = 0.123456
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="stab.json",
    )
    with pytest.raises(ValueError, match="summary.stability must equal"):
        load_dashboard_history_report(path)


def test_stability_must_be_float(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["stability"] = 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="stabint.json",
    )
    with pytest.raises(ValueError, match="summary.stability must be a float"):
        load_dashboard_history_report(path)


def test_volatility_mismatch_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["volatility"] = round(
        doc["summary"]["volatility"] + 0.01, 6
    )
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="vol.json",
    )
    with pytest.raises(ValueError, match="summary.volatility must equal"):
        load_dashboard_history_report(path)


def test_volatility_must_be_float(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["volatility"] = 0
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="volint.json",
    )
    with pytest.raises(ValueError, match="summary.volatility must be a float"):
        load_dashboard_history_report(path)


def test_longest_regression_mismatch_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["longest_regression"] = 3
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="longest.json",
    )
    with pytest.raises(
        ValueError, match="summary.longest_regression must be"
    ):
        load_dashboard_history_report(path)


def test_longest_regression_counts_consecutive_fails(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, passing, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
        write_dashboard(tmp_path, two_fail, "e.json"),
    )
    path, _ = write_report(tmp_path, paths, name="runs.json")
    result = load_dashboard_history_report(path)
    assert result["summary"]["longest_regression"] == 2


def test_worst_index_mismatch_rejected(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["summary"]["worst_index"] = doc["summary"]["worst_index"] + 1
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="widx.json",
    )
    with pytest.raises(ValueError, match="summary.worst_index must equal"):
        load_dashboard_history_report(path)


def test_top_quality_must_equal_history_quality(tmp_path):
    paths = make_paths(tmp_path)
    doc = report_doc(paths)
    doc["quality"] = "pass"
    path = write_bytes(
        tmp_path,
        json.dumps(doc, separators=(",", ":")).encode(),
        name="quality.json",
    )
    with pytest.raises(ValueError, match="quality must equal history.quality"):
        load_dashboard_history_report(path)


def test_non_canonical_spacing_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    path = write_bytes(tmp_path, data.replace(b":", b": ", 1), name="space.json")
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history_report(path)


def test_non_canonical_unicode_spelling_rejected(tmp_path):
    paths = make_paths(tmp_path)
    _, data = write_report(tmp_path, paths)
    mangled = data.replace(
        b'"quality":"fail"', b'"quality":"f\\u0061il"', 1
    )
    path = write_bytes(tmp_path, mangled, name="unicode.json")
    with pytest.raises(ValueError, match="canonical"):
        load_dashboard_history_report(path)


def test_all_pass_report(tmp_path):
    passing, _, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, passing, "b.json"),
    )
    path, _ = write_report(tmp_path, paths, name="allpass.json")
    result = load_dashboard_history_report(path)
    assert result["summary"] == {
        "snapshots": 2,
        "regressed": 0,
        "stability": 1.0,
        "volatility": 0.0,
        "longest_regression": 0,
        "worst_index": 1,
    }
    assert result["quality"] == "pass"
