"""Tests for product.serialize_trend_dashboard and export_trend_dashboard."""

from __future__ import annotations

import json

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    export_trend_dashboard,
    load_overview_comparison_report_trend,
    serialize_overview_comparison_report_trend,
    serialize_trend_dashboard,
    trend_dashboard,
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


def test_exported():
    assert "serialize_trend_dashboard" in product_mod.__all__
    assert product_mod.serialize_trend_dashboard is serialize_trend_dashboard
    assert "export_trend_dashboard" in product_mod.__all__
    assert product_mod.export_trend_dashboard is export_trend_dashboard


def test_serialize_calls_trend_dashboard_once(tmp_path, monkeypatch):
    path = write_trend(tmp_path)
    calls = []
    original = trend_dashboard

    def spy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(product_mod, "trend_dashboard", spy)
    data = serialize_trend_dashboard(path)
    assert calls == [path]
    assert isinstance(data, bytes)


def test_serialize_bytes_and_key_order(tmp_path):
    path = write_trend(
        tmp_path,
        trend_doc(
            [
                item(1, 0, 0, 1, "pass"),
                item(2, 1, 1, -1, "fail"),
            ]
        ),
    )
    data = serialize_trend_dashboard(path)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")

    document = json.loads(data)
    assert list(document.keys()) == ["trend", "summary", "quality"]
    assert list(document["trend"].keys()) == KEYS
    assert list(document["trend"]["changes"][0].keys()) == ITEM_KEYS
    assert list(document["summary"].keys()) == [
        "reports",
        "passed",
        "regressed",
        "ratio",
        "worst",
    ]
    assert document["summary"] == {
        "reports": 3,
        "passed": 1,
        "regressed": 1,
        "ratio": 0.5,
        "worst": 2,
    }
    assert document["quality"] == "fail"

    trend = load_overview_comparison_report_trend(path)
    dashboard = trend_dashboard(path)
    canonical = json.dumps(
        {
            "trend": {
                "count": trend["count"],
                "changes": list(trend["changes"]),
                "regressed": trend["regressed"],
                "worst": trend["worst"],
                "quality": trend["quality"],
            },
            "summary": dashboard["summary"],
            "quality": dashboard["quality"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert data == canonical


def test_serialize_trend_identity_embedded(tmp_path):
    path = write_trend(tmp_path)
    trend = load_overview_comparison_report_trend(path)
    data = serialize_trend_dashboard(path)
    document = json.loads(data)
    assert document["trend"] == {
        "count": trend["count"],
        "changes": [dict(c) for c in trend["changes"]],
        "regressed": trend["regressed"],
        "worst": dict(trend["worst"]),
        "quality": trend["quality"],
    }
    assert isinstance(document["trend"]["changes"], list)


def test_serialize_all_pass(tmp_path):
    path = write_trend(
        tmp_path,
        trend_doc([item(1, 0, 0, 2, "pass"), item(2, 0, 0, 1, "pass")]),
    )
    document = json.loads(serialize_trend_dashboard(path))
    assert document["summary"] == {
        "reports": 3,
        "passed": 2,
        "regressed": 0,
        "ratio": 1.0,
        "worst": 2,
    }
    assert document["quality"] == "pass"


def test_serialize_input_file_unchanged(tmp_path):
    path = write_trend(tmp_path)
    before = open(path, "rb").read()
    serialize_trend_dashboard(path)
    assert open(path, "rb").read() == before


def test_serialize_path_passed_through_and_propagates(monkeypatch):
    seen = []

    def fake_dashboard(value):
        seen.append(value)
        raise TypeError("path must be a str")

    monkeypatch.setattr(product_mod, "trend_dashboard", fake_dashboard)
    with pytest.raises(TypeError, match="path must be a str"):
        serialize_trend_dashboard(123)
    assert seen == [123]


def test_serialize_encoding_value_error_propagates(monkeypatch):
    def fake_dashboard(value):
        return {"trend": object(), "summary": {}, "quality": "fail"}

    monkeypatch.setattr(product_mod, "trend_dashboard", fake_dashboard)
    with pytest.raises(ValueError):
        serialize_trend_dashboard("x.json")


def test_serialize_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        serialize_trend_dashboard(missing)


def test_serialize_corrupted_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError):
        serialize_trend_dashboard(str(path))


def test_export_calls_serialize_once(tmp_path, monkeypatch):
    path = write_trend(tmp_path)
    output = str(tmp_path / "dash.json")
    calls = []
    payload = b'{"ok":true}'

    def fake_serialize(value):
        calls.append(value)
        return payload

    monkeypatch.setattr(
        product_mod, "serialize_trend_dashboard", fake_serialize
    )
    result = export_trend_dashboard(path, output)
    assert calls == [path]
    assert result == payload
    assert open(output, "rb").read() == payload


def test_export_success_returns_same_bytes(tmp_path):
    path = write_trend(tmp_path)
    output = tmp_path / "dash.json"
    data = export_trend_dashboard(path, str(output))
    assert output.read_bytes() == data
    assert data == serialize_trend_dashboard(path)


def test_export_path_error_precedes_output(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_trend_dashboard(
            str(tmp_path / "missing.json"), str(tmp_path / "o.json")
        )
    assert not (tmp_path / "o.json").exists()


@pytest.mark.parametrize(
    "output,exc_type",
    [
        pytest.param(123, TypeError, id="non-str"),
        pytest.param("", ValueError, id="empty"),
    ],
)
def test_export_output_validation(tmp_path, output, exc_type):
    path = write_trend(tmp_path)
    with pytest.raises(exc_type):
        export_trend_dashboard(path, output)


def test_export_rejects_same_file(tmp_path):
    path = write_trend(tmp_path)
    with pytest.raises(ValueError):
        export_trend_dashboard(path, path)


def test_export_overwrites_atomically_and_preserves_on_failure(tmp_path):
    path = write_trend(tmp_path)
    output = tmp_path / "dash.json"
    output.write_bytes(b"OLD")
    export_trend_dashboard(path, str(output))
    assert output.read_bytes() == serialize_trend_dashboard(path)

    preserved = tmp_path / "keep.json"
    preserved.write_bytes(b"PRESERVE")
    with pytest.raises(OSError):
        export_trend_dashboard(
            path, str(tmp_path / "missing-dir" / "x.json")
        )
    assert preserved.read_bytes() == b"PRESERVE"


def test_export_input_file_unchanged(tmp_path):
    path = write_trend(tmp_path)
    before = open(path, "rb").read()
    export_trend_dashboard(path, str(tmp_path / "dash.json"))
    assert open(path, "rb").read() == before
