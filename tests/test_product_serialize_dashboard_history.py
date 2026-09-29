"""Tests for product.serialize_dashboard_history."""

from __future__ import annotations

import json

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history,
    serialize_dashboard_history,
)

ITEM_KEYS = [
    "index",
    "passed_delta",
    "regressed_delta",
    "ratio_delta",
    "quality",
]
KEYS = ["count", "changes", "regressed", "worst", "quality"]


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


def write_pair(tmp_path, second_changes):
    first = dashboard_doc(
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 1, 2, -1, "fail"),
            trend_item(3, 0, -1, 0, "pass"),
        ]
    )
    second = dashboard_doc(second_changes)
    return (
        write_dashboard(tmp_path, first, "a.json"),
        write_dashboard(tmp_path, second, "b.json"),
    )


def test_exported():
    assert "serialize_dashboard_history" in product_mod.__all__
    assert (
        product_mod.serialize_dashboard_history
        is serialize_dashboard_history
    )


def test_serialize_calls_dashboard_history_once(tmp_path, monkeypatch):
    paths = write_pair(
        tmp_path,
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 0, 0, 1, "pass"),
            trend_item(3, 0, 0, 1, "pass"),
        ],
    )
    calls = []
    original = dashboard_history

    def spy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(product_mod, "dashboard_history", spy)
    data = serialize_dashboard_history(paths)
    assert calls == [paths]
    assert isinstance(data, bytes)


def test_serialize_bytes_and_key_order(tmp_path):
    paths = write_pair(
        tmp_path,
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 0, 0, 1, "pass"),
            trend_item(3, 0, 0, 1, "pass"),
        ],
    )
    data = serialize_dashboard_history(paths)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")

    document = json.loads(data)
    assert list(document.keys()) == KEYS
    assert list(document["changes"][0].keys()) == ITEM_KEYS
    assert list(document["worst"].keys()) == ITEM_KEYS
    assert document == {
        "count": 2,
        "changes": [
            {
                "index": 1,
                "passed_delta": 1,
                "regressed_delta": -1,
                "ratio_delta": round(1 / 3, 6),
                "quality": "pass",
            }
        ],
        "regressed": 0,
        "worst": {
            "index": 1,
            "passed_delta": 1,
            "regressed_delta": -1,
            "ratio_delta": round(1 / 3, 6),
            "quality": "pass",
        },
        "quality": "pass",
    }

    history = dashboard_history(paths)
    canonical = json.dumps(
        {
            "count": history["count"],
            "changes": [dict(item) for item in history["changes"]],
            "regressed": history["regressed"],
            "worst": dict(history["worst"]),
            "quality": history["quality"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert data == canonical


def test_serialize_changes_tuple_encoded_as_array(tmp_path):
    paths = write_pair(
        tmp_path,
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 1, 2, -1, "fail"),
            trend_item(3, 0, -1, 0, "pass"),
        ],
    )
    history = dashboard_history(paths)
    assert isinstance(history["changes"], tuple)
    data = serialize_dashboard_history(paths)
    document = json.loads(data)
    assert isinstance(document["changes"], list)


def test_serialize_regressed_snapshot(tmp_path):
    paths = write_pair(
        tmp_path,
        [
            trend_item(1, 1, 0, -1, "fail"),
            trend_item(2, 1, 2, -1, "fail"),
            trend_item(3, 0, -1, 0, "pass"),
        ],
    )
    document = json.loads(serialize_dashboard_history(paths))
    # ratio falls from 2/3 to 1/3, regressed rises 1 -> 2: the pair fails
    assert document["changes"][0]["quality"] == "fail"
    assert document["regressed"] == 1
    assert document["quality"] == "fail"


def test_serialize_negative_zero_normalized(tmp_path):
    identical = [
        trend_item(1, 0, 0, 1, "pass"),
        trend_item(2, 1, 2, -1, "fail"),
        trend_item(3, 0, -1, 0, "pass"),
    ]
    paths = write_pair(tmp_path, identical)
    data = serialize_dashboard_history(paths)
    assert b'"ratio_delta":0.0' in data
    assert b"ratio_delta\":-0.0" not in data


def test_serialize_input_files_unchanged(tmp_path):
    paths = write_pair(
        tmp_path,
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 0, 0, 1, "pass"),
            trend_item(3, 0, 0, 1, "pass"),
        ],
    )
    before = [open(path, "rb").read() for path in paths]
    serialize_dashboard_history(paths)
    assert [open(path, "rb").read() for path in paths] == before


def test_serialize_does_not_modify_paths(tmp_path):
    paths = list(
        write_pair(
            tmp_path,
            [
                trend_item(1, 0, 0, 1, "pass"),
                trend_item(2, 0, 0, 1, "pass"),
                trend_item(3, 0, 0, 1, "pass"),
            ],
        )
    )
    snapshot = list(paths)
    serialize_dashboard_history(paths)
    assert paths == snapshot


def test_serialize_paths_passed_through_and_propagates(monkeypatch):
    seen = []

    def fake_history(value):
        seen.append(value)
        raise TypeError("paths must be a list or tuple")

    monkeypatch.setattr(product_mod, "dashboard_history", fake_history)
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        serialize_dashboard_history(123)
    assert seen == [123]


def test_serialize_reports_mismatch_propagates(tmp_path):
    first = dashboard_doc(
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 1, 2, -1, "fail"),
        ]
    )
    second = dashboard_doc([trend_item(1, 0, 0, 1, "pass")])
    paths = (
        write_dashboard(tmp_path, first, "a.json"),
        write_dashboard(tmp_path, second, "b.json"),
    )
    with pytest.raises(ValueError, match="summary.reports"):
        serialize_dashboard_history(paths)


def test_serialize_missing_file(tmp_path):
    paths = (
        str(tmp_path / "missing.json"),
        str(tmp_path / "also-missing.json"),
    )
    with pytest.raises(FileNotFoundError):
        serialize_dashboard_history(paths)


def test_serialize_encoding_value_error(monkeypatch):
    def fake_history(value):
        return {
            "count": 2,
            "changes": (),
            "regressed": 0,
            "worst": object(),
            "quality": "pass",
        }

    monkeypatch.setattr(product_mod, "dashboard_history", fake_history)
    with pytest.raises(ValueError):
        serialize_dashboard_history(["a.json", "b.json"])
