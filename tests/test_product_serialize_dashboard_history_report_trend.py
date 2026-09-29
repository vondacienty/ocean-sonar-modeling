"""Tests for product.serialize_dashboard_history_report_trend."""

from __future__ import annotations

import json

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history_report_trend,
    serialize_dashboard_history_report_trend,
)

KEYS = ["count", "changes", "regressed", "worst", "quality"]
ITEM_KEYS = [
    "index",
    "stability_delta",
    "volatility_delta",
    "quality",
]


def report(snapshots=3, stability=0.5, volatility=0.1, quality="pass"):
    return {
        "schema_version": 1,
        "source": {"path": "history.json", "inputs": ("a", "b", "c")},
        "history": {},
        "summary": {
            "snapshots": snapshots,
            "regressed": 0,
            "stability": stability,
            "volatility": volatility,
            "longest_regression": 0,
            "worst_index": 1,
        },
        "quality": quality,
    }


def install_loader(monkeypatch, reports):
    calls = []

    def fake_load(path):
        calls.append(path)
        value = reports[len(calls) - 1]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(
        product_mod, "load_dashboard_history_report", fake_load
    )
    return calls


def test_exported():
    assert (
        "serialize_dashboard_history_report_trend" in product_mod.__all__
    )
    assert (
        product_mod.serialize_dashboard_history_report_trend
        is serialize_dashboard_history_report_trend
    )


def test_serialize_calls_trend_once(monkeypatch):
    reports = [report(stability=0.1), report(stability=0.2)]
    install_loader(monkeypatch, reports)
    calls = []
    original = dashboard_history_report_trend

    def spy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(
        product_mod, "dashboard_history_report_trend", spy
    )
    data = serialize_dashboard_history_report_trend(["a", "b"])
    assert calls == [["a", "b"]]
    assert isinstance(data, bytes)


def test_serialize_bytes_and_key_order(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.2),
         report(stability=0.6, volatility=0.1)],
    )
    data = serialize_dashboard_history_report_trend(["a", "b"])
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
                "stability_delta": 0.1,
                "volatility_delta": -0.1,
                "quality": "pass",
            }
        ],
        "regressed": 0,
        "worst": {
            "index": 1,
            "stability_delta": 0.1,
            "volatility_delta": -0.1,
            "quality": "pass",
        },
        "quality": "pass",
    }

    canonical = json.dumps(
        {
            "count": 2,
            "changes": [
                {
                    "index": 1,
                    "stability_delta": 0.1,
                    "volatility_delta": -0.1,
                    "quality": "pass",
                }
            ],
            "regressed": 0,
            "worst": {
                "index": 1,
                "stability_delta": 0.1,
                "volatility_delta": -0.1,
                "quality": "pass",
            },
            "quality": "pass",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert data == canonical


def test_serialize_changes_tuple_encoded_as_array(monkeypatch):
    install_loader(monkeypatch, [report(), report(stability=0.4)])
    data = serialize_dashboard_history_report_trend(["a", "b"])
    document = json.loads(data)
    assert isinstance(document["changes"], list)


def test_serialize_regressed_snapshot(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.9, quality="pass"),
         report(stability=0.8, quality="fail")],
    )
    document = json.loads(
        serialize_dashboard_history_report_trend(["a", "b"])
    )
    assert document["changes"][0]["quality"] == "fail"
    assert document["regressed"] == 1
    assert document["quality"] == "fail"


def test_serialize_negative_zero_normalized(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.1, volatility=0.1),
         report(stability=0.1, volatility=0.1)],
    )
    data = serialize_dashboard_history_report_trend(["a", "b"])
    assert b'"stability_delta":0.0' in data
    assert b'"volatility_delta":0.0' in data
    assert b"stability_delta\":-0.0" not in data
    assert b"volatility_delta\":-0.0" not in data


def test_serialize_floats_rounded_to_six(monkeypatch):
    raw = 1.0 / 3.0
    install_loader(
        monkeypatch,
        [report(stability=0.0, volatility=0.0),
         report(stability=raw, volatility=raw)],
    )
    data = serialize_dashboard_history_report_trend(["a", "b"])
    assert f'"stability_delta":{round(raw, 6)}'.encode() in data
    assert f'"volatility_delta":{round(raw, 6)}'.encode() in data


def test_serialize_paths_passed_through_and_propagates(monkeypatch):
    seen = []

    def fake_trend(value):
        seen.append(value)
        raise TypeError("paths must be a list or tuple")

    monkeypatch.setattr(
        product_mod, "dashboard_history_report_trend", fake_trend
    )
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        serialize_dashboard_history_report_trend(123)
    assert seen == [123]


def test_serialize_load_exception_propagates(monkeypatch):
    boom = ValueError(
        "file does not contain a valid dashboard history report: x"
    )
    install_loader(monkeypatch, [report(), boom])
    with pytest.raises(ValueError, match="^file does not contain"):
        serialize_dashboard_history_report_trend(["a", "b"])


def test_serialize_paths_validation_failure_makes_no_call(monkeypatch):
    calls = install_loader(monkeypatch, [report(), report()])
    with pytest.raises(ValueError):
        serialize_dashboard_history_report_trend(["only"])
    assert calls == []


def test_serialize_missing_file(tmp_path):
    paths = (
        str(tmp_path / "missing.json"),
        str(tmp_path / "also-missing.json"),
    )
    with pytest.raises(FileNotFoundError):
        serialize_dashboard_history_report_trend(paths)


def test_serialize_encoding_value_error(monkeypatch):
    def fake_trend(value):
        return {
            "count": 2,
            "changes": (),
            "regressed": 0,
            "worst": object(),
            "quality": "pass",
        }

    monkeypatch.setattr(
        product_mod, "dashboard_history_report_trend", fake_trend
    )
    with pytest.raises(ValueError):
        serialize_dashboard_history_report_trend(["a.json", "b.json"])


def _dump(report_obj):
    return json.dumps(
        report_obj,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _valid_report(snapshots, stability, volatility):
    regressed = 0 if stability == 1.0 else 1
    quality = "pass" if regressed == 0 else "fail"
    worst_verdict = "pass" if regressed == 0 else "fail"
    return {
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


def test_real_files_roundtrip(tmp_path):
    p1 = tmp_path / "r1.json"
    p1.write_bytes(_dump(_valid_report(2, 0.0, 0.5)))
    p2 = tmp_path / "r2.json"
    p2.write_bytes(_dump(_valid_report(2, 1.0, 0.0)))

    data = serialize_dashboard_history_report_trend([str(p1), str(p2)])
    assert json.loads(data) == {
        "count": 2,
        "changes": [
            {
                "index": 1,
                "stability_delta": 1.0,
                "volatility_delta": -0.5,
                "quality": "pass",
            }
        ],
        "regressed": 0,
        "worst": {
            "index": 1,
            "stability_delta": 1.0,
            "volatility_delta": -0.5,
            "quality": "pass",
        },
        "quality": "pass",
    }
