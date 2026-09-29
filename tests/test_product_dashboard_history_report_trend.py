"""Tests for product.dashboard_history_report_trend."""

import math

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    dashboard_history_report_trend,
    serialize_dashboard_history,
    serialize_dashboard_history_report,
)


def report(snapshots=3, stability=1.0, volatility=0.0, quality="pass"):
    return {
        "schema_version": 1,
        "source": {"path": "history.json", "inputs": ("a", "b", "c")},
        "history": {
            "count": snapshots,
            "changes": (),
            "regressed": 0,
            "worst": {"index": 1},
            "quality": quality,
        },
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
    assert "dashboard_history_report_trend" in product_mod.__all__
    assert (
        product_mod.dashboard_history_report_trend
        is dashboard_history_report_trend
    )


def test_result_key_order(monkeypatch):
    install_loader(monkeypatch, [report(), report(stability=0.5)])
    result = dashboard_history_report_trend(["a", "b"])
    assert list(result.keys()) == [
        "count",
        "changes",
        "regressed",
        "worst",
        "quality",
    ]


def test_count_value_and_type(monkeypatch):
    install_loader(
        monkeypatch,
        [report(), report(), report(), report()],
    )
    result = dashboard_history_report_trend(["a", "b", "c", "d"])
    assert result["count"] == 4
    assert type(result["count"]) is int
    assert type(result["regressed"]) is int


def test_changes_item_key_order_and_types(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.1, volatility=0.2),
         report(stability=0.3, volatility=0.4)],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert len(result["changes"]) == 1
    item = result["changes"][0]
    assert list(item.keys()) == [
        "index",
        "stability_delta",
        "volatility_delta",
        "quality",
    ]
    assert type(item["index"]) is int
    assert type(item["stability_delta"]) is float
    assert type(item["volatility_delta"]) is float
    assert type(item["quality"]) is str


def test_changes_is_tuple_and_index_values(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(),
            report(stability=0.2),
            report(stability=0.3),
            report(stability=0.4),
        ],
    )
    result = dashboard_history_report_trend(("p0", "p1", "p2", "p3"))
    assert isinstance(result["changes"], tuple)
    assert [item["index"] for item in result["changes"]] == [1, 2, 3]


@pytest.mark.parametrize("container", ["x", b"ab", {0: "a", 1: "b"}, set()])
def test_paths_container_must_be_list_or_tuple(container):
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        dashboard_history_report_trend(container)


@pytest.mark.parametrize("length", [0, 1])
def test_paths_must_have_at_least_two(length):
    with pytest.raises(ValueError, match="^paths must contain at least 2 items$"):
        dashboard_history_report_trend(["a"] * length)


def test_item_non_str_typeerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        dashboard_history_report_trend(["a", 1])


def test_item_empty_str_valueerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        dashboard_history_report_trend(["", "b"])


def test_item_validation_index_order(monkeypatch):
    install_loader(monkeypatch, [report(), report(), report()])
    # The first bad item wins even if a later one is also bad.
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        dashboard_history_report_trend([1, ""])


def test_no_load_calls_when_validation_fails(monkeypatch):
    calls = install_loader(monkeypatch, [report(), report()])
    with pytest.raises(ValueError):
        dashboard_history_report_trend(["only"])
    assert calls == []


def test_load_called_once_per_path_in_order(monkeypatch):
    calls = install_loader(
        monkeypatch,
        [report(stability=0.1), report(stability=0.2)],
    )
    dashboard_history_report_trend(["p0", "p1"])
    assert calls == ["p0", "p1"]


def test_load_exception_propagates_unchanged(monkeypatch):
    boom = ValueError(
        "file does not contain a valid dashboard history report: x"
    )
    install_loader(monkeypatch, [report(), boom])
    with pytest.raises(ValueError, match="^file does not contain"):
        dashboard_history_report_trend(["a", "b"])


def test_snapshots_mismatch_valueerror(monkeypatch):
    install_loader(monkeypatch, [report(snapshots=3), report(snapshots=4)])
    with pytest.raises(
        ValueError, match="summary.snapshots 4 does not match 3"
    ):
        dashboard_history_report_trend(["a", "b"])


def test_snapshots_mismatch_checked_before_computing_changes(monkeypatch):
    calls = install_loader(
        monkeypatch,
        [
            report(snapshots=3),
            report(snapshots=3),
            report(snapshots=2),
        ],
    )
    with pytest.raises(
        ValueError, match="summary.snapshots 2 does not match 3"
    ):
        dashboard_history_report_trend(["a", "b", "c"])
    # Every path is still loaded exactly once.
    assert calls == ["a", "b", "c"]


def test_ds_negative_fails(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.6, volatility=0.2, quality="pass"),
         report(stability=0.5, volatility=0.1, quality="pass")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == -0.1
    assert item["volatility_delta"] == -0.1
    assert item["quality"] == "fail"
    assert result["regressed"] == 1
    assert result["quality"] == "fail"


def test_dv_positive_fails_even_when_ds_positive(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.1, quality="pass"),
         report(stability=0.6, volatility=0.2, quality="pass")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.1
    assert item["volatility_delta"] == 0.1
    assert item["quality"] == "fail"


def test_improving_metrics_pass_even_on_fail_to_pass_transition(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.5, quality="fail"),
         report(stability=0.6, volatility=0.4, quality="pass")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.1
    assert item["volatility_delta"] == -0.1
    assert item["quality"] == "pass"
    assert result["regressed"] == 0
    assert result["quality"] == "pass"


def test_pass_to_fail_transition_fails(monkeypatch):
    # Construct reports the on-disk loader would reject (quality
    # disagreeing with the metrics), which is exactly why the transition
    # clause is evaluated explicitly.
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.5, quality="pass"),
         report(stability=0.5, volatility=0.5, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.0
    assert item["volatility_delta"] == 0.0
    assert item["quality"] == "fail"
    assert result["quality"] == "fail"


def test_zero_deltas_pass_to_pass_is_pass(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.25, quality="pass"),
         report(stability=0.5, volatility=0.25, quality="pass")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["changes"][0]["quality"] == "pass"
    assert result["regressed"] == 0
    assert result["quality"] == "pass"


def test_regressed_counts_fails(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.9, volatility=0.1, quality="pass"),
            report(stability=0.8, volatility=0.2, quality="fail"),
            report(stability=0.7, volatility=0.3, quality="fail"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c"])
    assert [item["quality"] for item in result["changes"]] == [
        "fail",
        "fail",
    ]
    assert result["regressed"] == 2
    assert result["quality"] == "fail"


def test_all_pass_overall(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.1, volatility=0.9, quality="pass"),
            report(stability=0.2, volatility=0.8, quality="pass"),
            report(stability=0.3, volatility=0.7, quality="pass"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c"])
    assert [item["quality"] for item in result["changes"]] == [
        "pass",
        "pass",
    ]
    assert result["quality"] == "pass"


def test_deltas_rounded_to_six(monkeypatch):
    raw = 1.0 / 3.0
    install_loader(
        monkeypatch,
        [report(stability=0.0, volatility=0.0),
         report(stability=raw, volatility=raw, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == round(raw, 6)
    assert item["volatility_delta"] == round(raw, 6)


def test_negative_zero_normalized(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.1, volatility=0.2),
            report(stability=0.1, volatility=0.2),
        ],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.0
    assert item["volatility_delta"] == 0.0
    assert math.copysign(1.0, item["stability_delta"]) == 1.0
    assert math.copysign(1.0, item["volatility_delta"]) == 1.0


def test_worst_minimizes_unrounded_tuple(monkeypatch):
    # i=1: ds=-0.1, dv=0.5 -> key (-0.1, -0.5, 1)
    # i=2: ds=-0.2, dv=0.1 -> key (-0.2, -0.1, 2)
    # i=3: ds=-0.2, dv=0.3 -> key (-0.2, -0.3, 3)  <- -0.3 beats -0.1
    install_loader(
        monkeypatch,
        [
            report(stability=0.0, volatility=0.0, quality="pass"),
            report(stability=-0.1, volatility=0.5, quality="fail"),
            report(stability=-0.3, volatility=0.6, quality="fail"),
            report(stability=-0.5, volatility=0.9, quality="fail"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c", "d"])
    assert result["worst"] is result["changes"][2]
    assert result["worst"]["index"] == 3
    assert result["worst"]["stability_delta"] == -0.2
    assert result["worst"]["volatility_delta"] == 0.3


def test_worst_tie_breaks_by_index(monkeypatch):
    # Equal unrounded ds and dv -> smallest i wins (first occurrence).
    install_loader(
        monkeypatch,
        [
            report(stability=0.0, volatility=0.0),
            report(stability=0.1, volatility=0.1, quality="fail"),
            report(stability=0.2, volatility=0.2, quality="fail"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c"])
    assert result["worst"] is result["changes"][0]
    assert result["worst"]["index"] == 1


def test_worst_uses_unrounded_delta(monkeypatch):
    # Two deltas that both round to the same 6-decimal value but differ
    # unrounded: the worst choice must follow the unrounded ordering.
    tiny = 1e-12
    r0 = report(stability=0.0)
    r1 = report(stability=tiny)             # i=1: ds = 1e-12
    r2 = report(stability=tiny + 5e-13)     # i=2: ds = 5e-13
    install_loader(monkeypatch, [r0, r1, r2])
    result = dashboard_history_report_trend(["a", "b", "c"])
    # Both rounded deltas are 0.0; unrounded keys:
    # i=1: (1e-12, 0, 1), i=2: (5e-13, 0, 2) -> i=2 is smaller.
    assert result["changes"][0]["stability_delta"] == 0.0
    assert result["changes"][1]["stability_delta"] == 0.0
    assert result["worst"] is result["changes"][1]


def test_worst_is_original_dict_not_copy(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.0),
         report(stability=-0.5, volatility=0.5, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["worst"] is result["changes"][0]


def test_no_extra_keys_and_no_sorting(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.9, volatility=0.1, quality="pass"),
            report(stability=0.5, volatility=0.5, quality="fail"),
            report(stability=0.8, volatility=0.2, quality="pass"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c"])
    assert [item["index"] for item in result["changes"]] == [1, 2]
    for item in result["changes"]:
        assert set(item.keys()) == {
            "index",
            "stability_delta",
            "volatility_delta",
            "quality",
        }
    assert set(result.keys()) == {
        "count",
        "changes",
        "regressed",
        "worst",
        "quality",
    }


def test_inputs_not_modified(monkeypatch):
    paths = ["a", "b"]
    reports = [
        report(stability=0.1, volatility=0.2),
        report(stability=0.3, volatility=0.4),
    ]
    install_loader(monkeypatch, reports)
    dashboard_history_report_trend(paths)
    assert paths == ["a", "b"]
    assert reports[0] == report(stability=0.1, volatility=0.2)
    assert reports[1] == report(stability=0.3, volatility=0.4)


def trend_item(
    index,
    failed_delta=0,
    regressed_delta=0,
    passed_delta=0,
    quality="pass",
):
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


def write_report(tmp_path, dash_paths, name):
    history_path = tmp_path / f"{name}.history.json"
    history_path.write_bytes(serialize_dashboard_history(dash_paths))
    data = serialize_dashboard_history_report(
        str(history_path), dash_paths
    )
    report_path = tmp_path / name
    report_path.write_bytes(data)
    return str(report_path)


def test_real_files_roundtrip(tmp_path):
    # Two trend dashboards with one change each: a passing dashboard
    # with ratio 1.0 and a failing one with ratio 0.0.
    dash_pass = dashboard_doc([trend_item(1, 0, 0, 0, "pass")])
    dash_fail = dashboard_doc(
        [trend_item(1, failed_delta=1, regressed_delta=1,
                    passed_delta=-1, quality="fail")]
    )
    d1 = write_dashboard(tmp_path, dash_pass, "dash1.json")
    d2 = write_dashboard(tmp_path, dash_pass, "dash2.json")
    d3 = write_dashboard(tmp_path, dash_fail, "dash3.json")

    # Report 1: ratio 1.0 -> 1.0, one passing change.
    # Report 2: ratio 1.0 -> 0.0, one failing change.
    r1 = write_report(tmp_path, [d1, d2], "r1.json")
    r2 = write_report(tmp_path, [d1, d3], "r2.json")

    result = dashboard_history_report_trend([r1, r2])
    assert result == {
        "count": 2,
        "changes": (
            {
                "index": 1,
                "stability_delta": -1.0,
                "volatility_delta": 1.0,
                "quality": "fail",
            },
        ),
        "regressed": 1,
        "worst": {
            "index": 1,
            "stability_delta": -1.0,
            "volatility_delta": 1.0,
            "quality": "fail",
        },
        "quality": "fail",
    }


def test_real_files_snapshots_mismatch(tmp_path):
    dash_pass = dashboard_doc([trend_item(1, 0, 0, 0, "pass")])
    d1 = write_dashboard(tmp_path, dash_pass, "dash1.json")
    d2 = write_dashboard(tmp_path, dash_pass, "dash2.json")
    d3 = write_dashboard(tmp_path, dash_pass, "dash3.json")

    r_two = write_report(tmp_path, [d1, d2], "two.json")
    r_three = write_report(tmp_path, [d1, d2, d3], "three.json")

    with pytest.raises(ValueError, match="summary.snapshots"):
        dashboard_history_report_trend((r_two, r_three))
