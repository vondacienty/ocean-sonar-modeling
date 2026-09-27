"""Tests for product.quality_report_trend."""

import json
import math

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import quality_report_trend


def report(count=3, failed=0, coverage_delta=0.1, quality="pass"):
    return {
        "schema_version": 1,
        "source": {"path": "trend.json", "kind": "quality_trend"},
        "summary": {
            "count": count,
            "failed": failed,
            "coverage_delta": coverage_delta,
        },
        "worst": {
            "index": 1,
            "coverage_delta": coverage_delta,
            "terrain_exceed_delta": 0,
            "unknown_delta": 0,
            "quality": quality,
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

    monkeypatch.setattr(product_mod, "load_quality_trend_report", fake_load)
    return calls


def test_exported():
    assert "quality_report_trend" in product_mod.__all__
    assert product_mod.quality_report_trend is quality_report_trend


def test_result_key_order(monkeypatch):
    install_loader(monkeypatch, [report(), report(failed=0, coverage_delta=0.2)])
    result = quality_report_trend(["a", "b"])
    assert list(result.keys()) == ["changes", "worst", "quality"]


def test_changes_item_key_order_and_types(monkeypatch):
    install_loader(
        monkeypatch,
        [report(coverage_delta=0.1), report(coverage_delta=0.2)],
    )
    result = quality_report_trend(["a", "b"])
    assert len(result["changes"]) == 1
    item = result["changes"][0]
    assert list(item.keys()) == [
        "index",
        "failed_delta",
        "coverage_delta",
        "quality",
    ]
    assert type(item["index"]) is int
    assert type(item["failed_delta"]) is int
    assert type(item["coverage_delta"]) is float
    assert type(item["quality"]) is str


def test_changes_is_tuple_and_index_values(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(),
            report(coverage_delta=0.2),
            report(coverage_delta=0.3),
            report(coverage_delta=0.4),
        ],
    )
    result = quality_report_trend(("p0", "p1", "p2", "p3"))
    assert isinstance(result["changes"], tuple)
    assert [item["index"] for item in result["changes"]] == [1, 2, 3]


@pytest.mark.parametrize("container", ["x", b"ab", {0: "a", 1: "b"}, set()])
def test_paths_container_must_be_list_or_tuple(container):
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        quality_report_trend(container)


@pytest.mark.parametrize("length", [0, 1])
def test_paths_must_have_at_least_two(length):
    with pytest.raises(ValueError, match="^paths must contain at least 2 items$"):
        quality_report_trend(["a"] * length)


def test_item_non_str_typeerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        quality_report_trend(["a", 1])


def test_item_empty_str_valueerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        quality_report_trend(["", "b"])


def test_item_validation_index_order(monkeypatch):
    install_loader(monkeypatch, [report(), report(), report()])
    # The first bad item wins even if a later one is also bad.
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        quality_report_trend([1, ""])


def test_no_load_calls_when_validation_fails(monkeypatch):
    calls = install_loader(monkeypatch, [report(), report()])
    with pytest.raises(ValueError):
        quality_report_trend(["only"])
    assert calls == []


def test_load_called_once_per_path_in_order(monkeypatch):
    calls = install_loader(
        monkeypatch,
        [report(coverage_delta=0.1), report(coverage_delta=0.2)],
    )
    quality_report_trend(["p0", "p1"])
    assert calls == ["p0", "p1"]


def test_load_exception_propagates_unchanged(monkeypatch):
    boom = ValueError("file does not contain a valid quality trend report: x")
    install_loader(monkeypatch, [report(), boom])
    with pytest.raises(ValueError, match="^file does not contain"):
        quality_report_trend(["a", "b"])


def test_count_mismatch_valueerror(monkeypatch):
    install_loader(monkeypatch, [report(count=3), report(count=4)])
    with pytest.raises(ValueError, match="summary.count 4 does not match 3"):
        quality_report_trend(["a", "b"])


def test_count_mismatch_checked_before_computing_changes(monkeypatch):
    calls = install_loader(
        monkeypatch,
        [
            report(count=3, coverage_delta=0.1),
            report(count=3, coverage_delta=0.2),
            report(count=2, coverage_delta=0.3),
        ],
    )
    with pytest.raises(ValueError, match="summary.count 2 does not match 3"):
        quality_report_trend(["a", "b", "c"])
    # Every path is still loaded exactly once.
    assert calls == ["a", "b", "c"]


def test_df_positive_fails(monkeypatch):
    install_loader(
        monkeypatch,
        [report(failed=1, coverage_delta=0.1, quality="fail"),
         report(failed=2, coverage_delta=0.5, quality="fail")],
    )
    result = quality_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["failed_delta"] == 1
    assert item["coverage_delta"] == 0.4
    assert item["quality"] == "fail"
    assert result["quality"] == "fail"


def test_dc_negative_fails(monkeypatch):
    install_loader(
        monkeypatch,
        [report(failed=2, coverage_delta=0.5, quality="fail"),
         report(failed=1, coverage_delta=0.1, quality="fail")],
    )
    result = quality_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["failed_delta"] == -1
    assert item["coverage_delta"] == -0.4
    assert item["quality"] == "fail"


def test_fail_to_pass_with_unchanging_metrics_passes(monkeypatch):
    install_loader(
        monkeypatch,
        [report(failed=1, coverage_delta=0.1, quality="fail"),
         report(failed=0, coverage_delta=0.1, quality="pass")],
    )
    result = quality_report_trend(["a", "b"])
    assert result["changes"][0]["quality"] == "pass"
    assert result["changes"][0]["failed_delta"] == -1
    assert result["changes"][0]["coverage_delta"] == 0.0
    assert result["quality"] == "pass"


def test_pass_to_fail_transition_fails(monkeypatch):
    # Construct reports the on-disk loader would reject (quality
    # disagreeing with failed), which is exactly why the transition
    # clause is evaluated explicitly.
    install_loader(
        monkeypatch,
        [report(failed=0, coverage_delta=0.1, quality="pass"),
         report(failed=0, coverage_delta=0.1, quality="fail")],
    )
    result = quality_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["failed_delta"] == 0
    assert item["coverage_delta"] == 0.0
    assert item["quality"] == "fail"
    assert result["quality"] == "fail"


def test_all_pass_overall(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(failed=0, coverage_delta=0.1, quality="pass"),
            report(failed=0, coverage_delta=0.2, quality="pass"),
            report(failed=0, coverage_delta=0.3, quality="pass"),
        ],
    )
    result = quality_report_trend(["a", "b", "c"])
    assert [item["quality"] for item in result["changes"]] == [
        "pass",
        "pass",
    ]
    assert result["quality"] == "pass"


def test_coverage_delta_rounded_to_six(monkeypatch):
    raw = 1.0 / 3.0
    install_loader(
        monkeypatch,
        [report(coverage_delta=0.0), report(coverage_delta=raw)],
    )
    result = quality_report_trend(["a", "b"])
    assert result["changes"][0]["coverage_delta"] == round(raw, 6)


def test_negative_zero_normalized(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(coverage_delta=0.1),
            report(coverage_delta=0.1),
        ],
    )
    result = quality_report_trend(["a", "b"])
    value = result["changes"][0]["coverage_delta"]
    assert value == 0.0
    assert math.copysign(1.0, value) == 1.0


def test_worst_minimizes_unrounded_tuple(monkeypatch):
    # coverage summaries: 0.0 -> -0.1 -> -0.3 -> -0.5
    # i=1: dc=-0.1, df=5 -> key (-0.1, -5, 1)
    # i=2: dc=-0.2, df=0 -> key (-0.2,  0, 2)
    # i=3: dc=-0.2, df=2 -> key (-0.2, -2, 3)  <- -2 beats 0
    install_loader(
        monkeypatch,
        [
            report(failed=0, coverage_delta=0.0, quality="pass"),
            report(failed=5, coverage_delta=-0.1, quality="fail"),
            report(failed=5, coverage_delta=-0.3, quality="fail"),
            report(failed=7, coverage_delta=-0.5, quality="fail"),
        ],
    )
    result = quality_report_trend(["a", "b", "c", "d"])
    assert result["worst"] is result["changes"][2]
    assert result["worst"]["index"] == 3
    assert result["worst"]["failed_delta"] == 2
    assert result["worst"]["coverage_delta"] == -0.2


def test_worst_tie_breaks_by_then_index(monkeypatch):
    # Equal unrounded dc and df -> smallest i wins (first occurrence).
    install_loader(
        monkeypatch,
        [
            report(coverage_delta=0.0),
            report(coverage_delta=0.1),
            report(coverage_delta=0.2),
        ],
    )
    result = quality_report_trend(["a", "b", "c"])
    assert result["worst"] is result["changes"][0]
    assert result["worst"]["index"] == 1


def test_worst_uses_unrounded_delta(monkeypatch):
    # Two deltas that both round to the same 6-decimal value but differ
    # unrounded: the worst choice must follow the unrounded ordering.
    tiny = 1e-12
    r0 = report(coverage_delta=0.0)
    r1 = report(coverage_delta=tiny)             # i=1: dc = 1e-12
    r2 = report(coverage_delta=tiny + 5e-13)     # i=2: dc = 5e-13
    install_loader(monkeypatch, [r0, r1, r2])
    result = quality_report_trend(["a", "b", "c"])
    # Both rounded deltas are 0.0; unrounded keys:
    # i=1: (1e-12, 0, 1), i=2: (5e-13, 0, 2) -> i=2 is smaller.
    assert result["changes"][0]["coverage_delta"] == 0.0
    assert result["changes"][1]["coverage_delta"] == 0.0
    assert result["worst"] is result["changes"][1]


def test_worst_is_original_dict_not_copy(monkeypatch):
    install_loader(
        monkeypatch,
        [report(coverage_delta=0.0),
         report(coverage_delta=-0.5, failed=1, quality="fail")],
    )
    result = quality_report_trend(["a", "b"])
    assert result["worst"] is result["changes"][0]


def test_no_extra_keys_and_no_sorting(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(failed=0, coverage_delta=0.5, quality="pass"),
            report(failed=1, coverage_delta=0.1, quality="fail"),
            report(failed=0, coverage_delta=0.9, quality="pass"),
        ],
    )
    result = quality_report_trend(["a", "b", "c"])
    assert [item["index"] for item in result["changes"]] == [1, 2]
    for item in result["changes"]:
        assert set(item.keys()) == {
            "index",
            "failed_delta",
            "coverage_delta",
            "quality",
        }
    assert set(result.keys()) == {"changes", "worst", "quality"}


def test_inputs_not_modified(monkeypatch):
    paths = ["a", "b"]
    reports = [report(coverage_delta=0.1), report(coverage_delta=0.2)]
    install_loader(monkeypatch, reports)
    quality_report_trend(paths)
    assert paths == ["a", "b"]
    assert reports[0] == report(coverage_delta=0.1)
    assert reports[1] == report(coverage_delta=0.2)


def _dump(report_obj):
    return json.dumps(
        report_obj,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write(tmp_path, name, report_obj):
    path = tmp_path / name
    path.write_bytes(_dump(report_obj))
    return str(path)


def test_real_files_roundtrip(tmp_path):
    p1 = _write(
        tmp_path,
        "r1.json",
        report(count=2, failed=0, coverage_delta=0.25, quality="pass"),
    )
    p2 = _write(
        tmp_path,
        "r2.json",
        report(count=2, failed=1, coverage_delta=0.1, quality="fail"),
    )
    result = quality_report_trend([p1, p2])
    assert result == {
        "changes": (
            {
                "index": 1,
                "failed_delta": 1,
                "coverage_delta": -0.15,
                "quality": "fail",
            },
        ),
        "worst": {
            "index": 1,
            "failed_delta": 1,
            "coverage_delta": -0.15,
            "quality": "fail",
        },
        "quality": "fail",
    }


def test_real_files_count_mismatch(tmp_path):
    p1 = _write(tmp_path, "r1.json", report(count=2))
    p2 = _write(tmp_path, "r2.json", report(count=3))
    with pytest.raises(ValueError, match="summary.count"):
        quality_report_trend((p1, p2))
