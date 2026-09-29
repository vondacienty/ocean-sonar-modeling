"""Tests for product.serialize_dashboard_history_report."""

from __future__ import annotations

import json
import math

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history,
    serialize_dashboard_history,
    serialize_dashboard_history_report,
)

ITEM_KEYS = [
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
    "quality",
]
HISTORY_KEYS = ["count", "changes", "regressed", "worst", "quality"]
REPORT_KEYS = [
    "schema_version",
    "source",
    "history",
    "summary",
    "quality",
]
SOURCE_KEYS = ["path", "inputs"]
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
    path.write_bytes(
        product_mod._dump_overview_comparison_report_trend(doc)
    )
    return str(path)


def write_history(tmp_path, paths, name="history.json"):
    path = tmp_path / name
    path.write_bytes(serialize_dashboard_history(paths))
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


def test_exported():
    assert "serialize_dashboard_history_report" in product_mod.__all__
    assert (
        product_mod.serialize_dashboard_history_report
        is serialize_dashboard_history_report
    )


def test_serialize_calls_each_source_once(tmp_path, monkeypatch):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    history_path = write_history(tmp_path, paths)

    load_calls = []
    history_calls = []
    original_load = product_mod.load_dashboard_history
    original_history = dashboard_history

    def load_spy(value):
        load_calls.append(value)
        return original_load(value)

    def history_spy(value):
        history_calls.append(value)
        return original_history(value)

    monkeypatch.setattr(product_mod, "load_dashboard_history", load_spy)
    monkeypatch.setattr(product_mod, "dashboard_history", history_spy)

    data = serialize_dashboard_history_report(history_path, paths)
    assert load_calls == [history_path]
    assert history_calls == [paths]
    assert isinstance(data, bytes)


def test_serialize_bytes_and_key_order(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, two_fail, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
    )
    history_path = write_history(tmp_path, paths)

    data = serialize_dashboard_history_report(history_path, paths)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")

    document = json.loads(data)
    assert list(document.keys()) == REPORT_KEYS
    assert document["schema_version"] == 1
    assert type(document["schema_version"]) is int
    assert list(document["source"].keys()) == SOURCE_KEYS
    assert document["source"]["path"] == history_path
    assert document["source"]["inputs"] == list(paths)
    assert list(document["history"].keys()) == HISTORY_KEYS
    for item in document["history"]["changes"]:
        assert list(item.keys()) == ITEM_KEYS
    assert list(document["history"]["worst"].keys()) == ITEM_KEYS
    assert list(document["summary"].keys()) == SUMMARY_KEYS


def test_serialize_summary_values(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, two_fail, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
    )
    history_path = write_history(tmp_path, paths)
    history = dashboard_history(paths)

    document = json.loads(
        serialize_dashboard_history_report(history_path, paths)
    )
    changes = history["changes"]
    expected_volatility = round(
        math.fsum(abs(item["ratio_delta"]) for item in changes)
        / len(changes),
        6,
    )
    assert document["summary"] == {
        "snapshots": history["count"],
        "regressed": history["regressed"],
        "stability": round(
            1 - history["regressed"] / len(changes), 6
        ),
        "volatility": expected_volatility,
        "longest_regression": 2,
        "worst_index": history["worst"]["index"],
    }
    assert document["quality"] == history["quality"]
    assert document["history"] == json.loads(
        serialize_dashboard_history(paths)
    )


def test_serialize_longest_regression_counts_consecutive_fails(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    # fail, pass, fail, fail -> longest run of fails is 2 at the tail
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, passing, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
        write_dashboard(tmp_path, two_fail, "e.json"),
    )
    history_path = write_history(tmp_path, paths)
    qualities = [
        item["quality"]
        for item in json.loads(
            serialize_dashboard_history(paths)
        )["changes"]
    ]
    assert qualities == ["fail", "pass", "fail", "fail"]

    document = json.loads(
        serialize_dashboard_history_report(history_path, paths)
    )
    assert document["summary"]["longest_regression"] == 2


def test_serialize_all_pass_summary(tmp_path):
    passing, _, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, passing, "b.json"),
    )
    history_path = write_history(tmp_path, paths)
    document = json.loads(
        serialize_dashboard_history_report(history_path, paths)
    )
    assert document["summary"] == {
        "snapshots": 2,
        "regressed": 0,
        "stability": 1.0,
        "volatility": 0.0,
        "longest_regression": 0,
        "worst_index": 1,
    }
    assert document["quality"] == "pass"


def test_serialize_tuple_inputs_encoded_as_array(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    history_path = write_history(tmp_path, paths)
    data = serialize_dashboard_history_report(history_path, paths)
    document = json.loads(data)
    assert isinstance(document["source"]["inputs"], list)
    assert isinstance(document["history"]["changes"], list)


def test_serialize_canonical_bytes(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    history_path = write_history(tmp_path, paths)
    history = dashboard_history(paths)
    data = serialize_dashboard_history_report(history_path, paths)

    canonical = json.dumps(
        {
            "schema_version": 1,
            "source": {"path": history_path, "inputs": list(paths)},
            "history": {
                "count": history["count"],
                "changes": [dict(item) for item in history["changes"]],
                "regressed": history["regressed"],
                "worst": dict(history["worst"]),
                "quality": history["quality"],
            },
            "summary": json.loads(data)["summary"],
            "quality": history["quality"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert data == canonical


def test_serialize_mismatched_history_raises_value_error(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    paths_ab = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    paths_ac = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, two_fail, "c.json"),
    )
    history_path = write_history(tmp_path, paths_ab, "ab.json")
    with pytest.raises(ValueError):
        serialize_dashboard_history_report(history_path, paths_ac)


def test_serialize_invalid_history_file_raises_value_error(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'{"x":1}')
    with pytest.raises(ValueError):
        serialize_dashboard_history_report(str(bad), paths)


def test_serialize_path_validation_passthrough(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    history_path = write_history(tmp_path, paths)

    with pytest.raises(TypeError):
        serialize_dashboard_history_report(123, paths)
    with pytest.raises(ValueError):
        serialize_dashboard_history_report("", paths)
    with pytest.raises(FileNotFoundError):
        serialize_dashboard_history_report(str(tmp_path / "missing"), paths)


def test_serialize_paths_validation_passthrough(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )
    history_path = write_history(tmp_path, paths)

    with pytest.raises(TypeError):
        serialize_dashboard_history_report(history_path, "not-a-list")
    with pytest.raises(ValueError, match="paths\[1\]: "):
        serialize_dashboard_history_report(history_path, ["a", ""])


def test_serialize_does_not_modify_inputs(tmp_path):
    passing, one_fail, _ = snapshot_docs()
    paths = list(
        (
            write_dashboard(tmp_path, passing, "a.json"),
            write_dashboard(tmp_path, one_fail, "b.json"),
        )
    )
    history_path = write_history(tmp_path, paths)
    before = [open(path, "rb").read() for path in paths]
    history_before = open(history_path, "rb").read()
    paths_snapshot = list(paths)

    serialize_dashboard_history_report(history_path, paths)

    assert [open(path, "rb").read() for path in paths] == before
    assert open(history_path, "rb").read() == history_before
    assert paths == paths_snapshot
