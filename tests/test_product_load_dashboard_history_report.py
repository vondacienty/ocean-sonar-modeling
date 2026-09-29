"""Tests for product.load_dashboard_history_report."""

from __future__ import annotations

import json
import math

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history,
    load_dashboard_history_report,
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
    history_path = str(tmp_path / "history.json")
    with open(history_path, "wb") as handle:
        handle.write(serialize_dashboard_history(paths))
    path = tmp_path / name
    path.write_bytes(
        serialize_dashboard_history_report(history_path, paths)
    )
    return str(path), history_path


_RAW_COUNTER = 0


def write_raw(tmp_path, doc, name=None):
    global _RAW_COUNTER
    if name is None:
        _RAW_COUNTER += 1
        name = f"raw_{_RAW_COUNTER}.json"
    path = tmp_path / name
    path.write_bytes(product_mod._dump_dashboard_history(doc))
    return str(path)


def test_exported():
    assert "load_dashboard_history_report" in product_mod.__all__
    assert (
        product_mod.load_dashboard_history_report
        is load_dashboard_history_report
    )


def test_load_structure_and_values(tmp_path):
    paths = make_paths(tmp_path)
    report_path, history_path = write_report(tmp_path, paths)
    history = dashboard_history(paths)
    changes = history["changes"]

    report = load_dashboard_history_report(report_path)

    assert report["source"]["path"] == history_path
    assert report["source"]["inputs"] == tuple(paths)

    loaded_history = report["history"]
    assert list(loaded_history.keys()) == HISTORY_KEYS
    assert type(loaded_history["changes"]) is tuple
    for item in loaded_history["changes"]:
        assert list(item.keys()) == ITEM_KEYS
    assert loaded_history["count"] == history["count"]
    assert loaded_history["changes"] == changes
    assert loaded_history["regressed"] == history["regressed"]
    assert list(loaded_history["worst"].keys()) == ITEM_KEYS
    assert loaded_history["worst"] == history["worst"]
    assert loaded_history["quality"] == history["quality"]

    # worst is the matching object inside the converted changes tuple
    assert loaded_history["worst"] is next(
        item
        for item in loaded_history["changes"]
        if item == history["worst"]
    )

    summary = report["summary"]
    assert list(summary.keys()) == SUMMARY_KEYS
    assert summary == {
        "snapshots": history["count"],
        "regressed": history["regressed"],
        "stability": round(
            1 - history["regressed"] / len(changes), 6
        )
        or 0.0,
        "volatility": round(
            math.fsum(abs(item["ratio_delta"]) for item in changes)
            / len(changes),
            6,
        )
        or 0.0,
        "longest_regression": 2,
        "worst_index": history["worst"]["index"],
    }
    assert report["quality"] == history["quality"]


def test_load_all_pass(tmp_path):
    passing, _, _ = snapshot_docs()
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, passing, "b.json"),
    )
    report_path, _ = write_report(tmp_path, paths)
    report = load_dashboard_history_report(report_path)
    assert report["summary"] == {
        "snapshots": 2,
        "regressed": 0,
        "stability": 1.0,
        "volatility": 0.0,
        "longest_regression": 0,
        "worst_index": 1,
    }
    assert report["quality"] == "pass"


def test_load_matches_serialized_history(tmp_path):
    paths = make_paths(tmp_path)
    report_path, history_path = write_report(tmp_path, paths)
    report = load_dashboard_history_report(report_path)
    standalone = json.loads(serialize_dashboard_history(paths))
    loaded_history = report["history"]
    assert loaded_history["count"] == standalone["count"]
    assert loaded_history["changes"] == tuple(standalone["changes"])
    assert loaded_history["regressed"] == standalone["regressed"]
    assert loaded_history["worst"] == standalone["worst"]
    assert loaded_history["quality"] == standalone["quality"]
    assert report["source"]["path"] == history_path


def test_load_path_validation(tmp_path):
    with pytest.raises(TypeError):
        load_dashboard_history_report(123)
    with pytest.raises(ValueError):
        load_dashboard_history_report("")
    with pytest.raises(FileNotFoundError):
        load_dashboard_history_report(str(tmp_path / "missing.json"))
    with pytest.raises(IsADirectoryError):
        load_dashboard_history_report(str(tmp_path))


def test_load_rejects_bom_and_trailing_newline(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    raw = open(report_path, "rb").read()

    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + raw)
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(bom))

    newline = tmp_path / "newline.json"
    newline.write_bytes(raw + b"\n")
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(newline))


def test_load_rejects_non_canonical_bytes(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    document = json.loads(open(report_path, "rb").read())
    pretty = tmp_path / "pretty.json"
    pretty.write_text(
        json.dumps(document, indent=2), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(pretty))


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{not json")
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(path))


def test_load_rejects_json_constants(tmp_path):
    path = tmp_path / "nan.json"
    path.write_bytes(b'{"schema_version":NaN}')
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(path))


def test_load_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "dup.json"
    path.write_bytes(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(path))


def test_load_rejects_non_object(tmp_path):
    path = tmp_path / "list.json"
    path.write_bytes(b"[1,2,3]")
    with pytest.raises(ValueError):
        load_dashboard_history_report(str(path))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("quality"),
        lambda d: d.update(extra=1),
        lambda d: d.update(schema_version=d.pop("schema_version")),
    ],
)
def test_load_rejects_bad_top_level(tmp_path, mutate):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    doc = json.loads(open(report_path, "rb").read())
    mutate(doc)
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_rejects_schema_version(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    for value in (2, True, "1", 1.0):
        doc = json.loads(open(report_path, "rb").read())
        doc["schema_version"] = value
        with pytest.raises(ValueError):
            load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_rejects_bad_source(tmp_path):
    paths = make_paths(tmp_path)
    report_path, history_path = write_report(tmp_path, paths)

    doc = json.loads(open(report_path, "rb").read())
    doc["source"] = []
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc, "sa.json"))

    doc = json.loads(open(report_path, "rb").read())
    doc["source"] = {
        "inputs": doc["source"]["inputs"],
        "path": history_path,
    }
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc, "b.json"))

    doc = json.loads(open(report_path, "rb").read())
    doc["source"]["path"] = ""
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc, "c.json"))

    doc = json.loads(open(report_path, "rb").read())
    doc["source"]["path"] = 7
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc, "d.json"))


def test_load_rejects_bad_inputs(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)

    for value in ("not-a-list", 3, [paths[0]], [paths[0], 1], [paths[0], ""]):
        doc = json.loads(open(report_path, "rb").read())
        doc["source"]["inputs"] = value
        with pytest.raises(ValueError):
            load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["source"]["inputs"] = paths[1:]
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_rejects_bad_history(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)

    doc = json.loads(open(report_path, "rb").read())
    doc["history"]["count"] = 3
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["history"]["changes"][0]["quality"] = "pass"
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["history"]["worst"]["index"] = 99
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_rejects_summary_mismatches(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)

    def build(mutate):
        doc = json.loads(open(report_path, "rb").read())
        mutate(doc["summary"])
        return write_raw(tmp_path, doc)

    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(snapshots=99))
        )
    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(regressed=99))
        )
    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(stability=0.5))
        )
    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(volatility=0.5))
        )
    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(longest_regression=99))
        )
    with pytest.raises(ValueError):
        load_dashboard_history_report(
            build(lambda s: s.update(worst_index=99))
        )

    doc = json.loads(open(report_path, "rb").read())
    doc["summary"].pop("worst_index")
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    reordered = {
        "worst_index": doc["summary"]["worst_index"],
        **{k: v for k, v in doc["summary"].items() if k != "worst_index"},
    }
    doc["summary"] = reordered
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["summary"]["stability"] = True
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["summary"]["stability"] = 1
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_rejects_quality_mismatch(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    doc = json.loads(open(report_path, "rb").read())
    doc["quality"] = "pass"
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))

    doc = json.loads(open(report_path, "rb").read())
    doc["quality"] = "maybe"
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc))


def test_load_recomputes_longest_regression(tmp_path):
    passing, one_fail, two_fail = snapshot_docs()
    # fail, pass, fail, fail -> longest run is 2
    paths = (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
        write_dashboard(tmp_path, passing, "c.json"),
        write_dashboard(tmp_path, one_fail, "d.json"),
        write_dashboard(tmp_path, two_fail, "e.json"),
    )
    report_path, _ = write_report(tmp_path, paths)
    report = load_dashboard_history_report(report_path)
    assert report["summary"]["longest_regression"] == 2

    doc = json.loads(open(report_path, "rb").read())
    doc["summary"]["longest_regression"] = 1
    with pytest.raises(ValueError):
        load_dashboard_history_report(write_raw(tmp_path, doc, "bad.json"))


def test_load_does_not_modify_file(tmp_path):
    paths = make_paths(tmp_path)
    report_path, history_path = write_report(tmp_path, paths)
    before = open(report_path, "rb").read()
    load_dashboard_history_report(report_path)
    after = open(report_path, "rb").read()
    assert after == before
    assert open(history_path, "rb").read() == serialize_dashboard_history(
        paths
    )


def test_load_returns_fresh_top_level_dict(tmp_path):
    paths = make_paths(tmp_path)
    report_path, _ = write_report(tmp_path, paths)
    first = load_dashboard_history_report(report_path)
    second = load_dashboard_history_report(report_path)
    assert first == second
    assert first is not second
    assert first["history"] is not second["history"]
