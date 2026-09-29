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

REPORT_KEYS = ["schema_version", "source", "history", "summary", "quality"]
SOURCE_KEYS = ["path", "inputs"]
SUMMARY_KEYS = [
    "snapshots",
    "regressed",
    "stability",
    "volatility",
    "longest_regression",
    "worst_index",
]
HISTORY_KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
    "quality",
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


def dashboards(tmp_path, qualities_by_doc):
    paths = []
    for i, qualities in enumerate(qualities_by_doc):
        items = [
            trend_item(
                j,
                0 if q == "pass" else 1,
                0 if q == "pass" else 2,
                1 if q == "pass" else -1,
                q,
            )
            for j, q in enumerate(qualities, start=1)
        ]
        paths.append(write_dashboard(tmp_path, dashboard_doc(items), f"d{i}.json"))
    return paths


def write_history(tmp_path, paths, name="history.json"):
    path = tmp_path / name
    path.write_bytes(serialize_dashboard_history(paths))
    return str(path)


def valid_pair(tmp_path):
    paths = dashboards(
        tmp_path,
        (
            ("pass", "pass"),
            ("pass", "fail"),
        ),
    )
    return write_history(tmp_path, paths), paths


def test_exported():
    assert "serialize_dashboard_history_report" in product_mod.__all__
    assert (
        product_mod.serialize_dashboard_history_report
        is serialize_dashboard_history_report
    )


def test_calls_each_helper_once_with_unchanged_arguments(tmp_path, monkeypatch):
    path, paths = valid_pair(tmp_path)
    load_calls = []
    history_calls = []
    original_load = product_mod.load_dashboard_history
    original_history = dashboard_history

    def spy_load(value):
        load_calls.append(value)
        return original_load(value)

    def spy_history(value):
        history_calls.append(value)
        return original_history(value)

    monkeypatch.setattr(product_mod, "load_dashboard_history", spy_load)
    monkeypatch.setattr(product_mod, "dashboard_history", spy_history)

    data = serialize_dashboard_history_report(path, paths)

    assert load_calls == [path]
    assert history_calls == [paths]
    assert isinstance(data, bytes)


def test_bytes_and_key_order(tmp_path):
    path, paths = valid_pair(tmp_path)

    data = serialize_dashboard_history_report(path, paths)

    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")
    document = json.loads(data)
    assert list(document.keys()) == REPORT_KEYS
    assert list(document["source"].keys()) == SOURCE_KEYS
    assert list(document["summary"].keys()) == SUMMARY_KEYS
    assert list(document["history"].keys()) == HISTORY_KEYS
    assert list(document["history"]["changes"][0].keys()) == ITEM_KEYS
    assert list(document["history"]["worst"].keys()) == ITEM_KEYS


def test_source_values_and_inputs_array(tmp_path):
    paths = [p for p in valid_pair(tmp_path)[1]]
    path = write_history(tmp_path, paths, "other.json")

    document = json.loads(serialize_dashboard_history_report(path, paths))

    assert document["source"]["path"] == path
    assert document["source"]["inputs"] == paths
    assert isinstance(document["source"]["inputs"], list)


def test_history_equals_serialized_history(tmp_path):
    path, paths = valid_pair(tmp_path)

    document = json.loads(serialize_dashboard_history_report(path, paths))

    assert document["history"] == json.loads(
        serialize_dashboard_history(paths)
    )


def test_summary_values_for_single_fail(tmp_path):
    path, paths = valid_pair(tmp_path)

    document = json.loads(serialize_dashboard_history_report(path, paths))
    history = dashboard_history(paths)
    changes = history["changes"]
    expected_volatility = round(
        math.fsum(abs(c["ratio_delta"]) for c in changes) / len(changes),
        6,
    )

    assert document["summary"] == {
        "snapshots": history["count"],
        "regressed": 1,
        "stability": 0.0,
        "volatility": expected_volatility,
        "longest_regression": 1,
        "worst_index": history["worst"]["index"],
    }
    assert document["quality"] == history["quality"]


def test_longest_run_takes_maximum_not_total(tmp_path):
    # four snapshots -> fail, pass, fail: two fails but the longest run is 1
    paths = dashboards(
        tmp_path,
        (
            ("pass", "pass", "pass"),
            ("fail", "pass", "pass"),
            ("pass", "pass", "pass"),
            ("fail", "pass", "pass"),
        ),
    )
    path = write_history(tmp_path, paths)

    document = json.loads(serialize_dashboard_history_report(path, paths))

    assert document["summary"]["regressed"] == 2
    assert document["summary"]["longest_regression"] == 1


def test_longest_run_consecutive_fails(tmp_path):
    paths = dashboards(
        tmp_path,
        (
            ("pass", "pass"),
            ("pass", "fail"),
            ("fail", "fail"),
        ),
    )
    path = write_history(tmp_path, paths)

    document = json.loads(serialize_dashboard_history_report(path, paths))

    assert [
        c["quality"] for c in document["history"]["changes"]
    ] == ["fail", "fail"]
    assert document["summary"]["longest_regression"] == 2
    assert document["summary"]["stability"] == 0.0


def test_all_pass_stability_one(tmp_path):
    paths = dashboards(
        tmp_path,
        (
            ("pass", "pass"),
            ("pass", "pass"),
        ),
    )
    path = write_history(tmp_path, paths)

    document = json.loads(serialize_dashboard_history_report(path, paths))

    summary = document["summary"]
    assert summary["regressed"] == 0
    assert summary["stability"] == 1.0
    assert summary["longest_regression"] == 0


def test_negative_zero_normalized(tmp_path):
    paths = dashboards(
        tmp_path,
        (
            ("pass", "fail"),
            ("pass", "fail"),
        ),
    )
    path = write_history(tmp_path, paths)
    # identical summaries -> the only ratio_delta is exactly zero
    history = dashboard_history(paths)
    assert history["changes"][0]["ratio_delta"] == 0.0

    data = serialize_dashboard_history_report(path, paths)

    assert b'"volatility":0.0' in data
    assert b"volatility\":-0.0" not in data


def test_canonical_encoding_matches_dumps(tmp_path):
    path, paths = valid_pair(tmp_path)
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
    report = {
        "schema_version": 1,
        "source": {"path": path, "inputs": list(paths)},
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
            "stability": 1 - history["regressed"] / len(changes),
            "volatility": math.fsum(
                abs(item["ratio_delta"]) for item in changes
            )
            / len(changes),
            "longest_regression": longest,
            "worst_index": history["worst"]["index"],
        },
        "quality": history["quality"],
    }
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    assert serialize_dashboard_history_report(path, paths) == canonical


def test_mismatch_raises_value_error(tmp_path):
    path, _ = valid_pair(tmp_path)
    other = dashboards(
        tmp_path,
        (
            ("pass", "pass"),
            ("pass", "pass"),
        ),
    )

    with pytest.raises(ValueError, match="does not match"):
        serialize_dashboard_history_report(path, other)


def test_mismatch_does_not_reload(tmp_path, monkeypatch):
    path, paths = valid_pair(tmp_path)

    def fake_history(_value):
        result = dashboard_history(paths)
        return {**result, "regressed": result["regressed"] + 1}

    monkeypatch.setattr(product_mod, "dashboard_history", fake_history)

    with pytest.raises(ValueError):
        serialize_dashboard_history_report(path, paths)


def test_path_validation_propagates_unchanged(tmp_path, monkeypatch):
    seen = []

    def fake_load(value):
        seen.append(value)
        raise TypeError("path must be a str")

    monkeypatch.setattr(product_mod, "load_dashboard_history", fake_load)

    with pytest.raises(TypeError, match="path must be a str"):
        serialize_dashboard_history_report(123, ["a.json", "b.json"])
    assert seen == [123]


def test_missing_history_file(tmp_path):
    paths = [str(tmp_path / "a.json"), str(tmp_path / "b.json")]
    with pytest.raises(FileNotFoundError):
        serialize_dashboard_history_report(
            str(tmp_path / "missing.json"), paths
        )


def test_paths_validation_propagates_unchanged(tmp_path):
    path, _ = valid_pair(tmp_path)
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        serialize_dashboard_history_report(path, 123)
    with pytest.raises(ValueError, match="at least 2 items"):
        serialize_dashboard_history_report(path, ["a.json"])


def test_path_error_precedes_paths_error(tmp_path, monkeypatch):
    def fake_load(value):
        raise TypeError("path must be a str")

    monkeypatch.setattr(product_mod, "load_dashboard_history", fake_load)

    with pytest.raises(TypeError, match="path must be a str"):
        serialize_dashboard_history_report(123, 123)


def test_inputs_and_files_unchanged(tmp_path):
    path, paths_tuple = valid_pair(tmp_path)
    paths = list(paths_tuple)
    snapshot = list(paths)
    before = [open(item, "rb").read() for item in paths]
    history_before = open(path, "rb").read()

    serialize_dashboard_history_report(path, paths)

    assert paths == snapshot
    assert [open(item, "rb").read() for item in paths] == before
    assert open(path, "rb").read() == history_before


def test_paths_accepted_as_tuple(tmp_path):
    path, paths = valid_pair(tmp_path)
    data = serialize_dashboard_history_report(path, tuple(paths))
    document = json.loads(data)
    assert document["source"]["inputs"] == list(paths)
