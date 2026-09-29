"""Tests for product.dashboard_history_report_trend."""

import json
import math

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import dashboard_history_report_trend


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
    assert "dashboard_history_report_trend" in product_mod.__all__
    assert (
        product_mod.dashboard_history_report_trend
        is dashboard_history_report_trend
    )


def test_result_key_order(monkeypatch):
    install_loader(
        monkeypatch, [report(), report(stability=0.6, volatility=0.05)]
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert list(result.keys()) == [
        "count",
        "changes",
        "regressed",
        "worst",
        "quality",
    ]


def test_changes_item_key_order_and_types(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.2),
         report(stability=0.6, volatility=0.1)],
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
            report(stability=0.1),
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
    with pytest.raises(
        ValueError, match="^paths must contain at least 2 items$"
    ):
        dashboard_history_report_trend(["a"] * length)


def test_item_non_str_typeerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        dashboard_history_report_trend(["a", 1])


def test_item_empty_str_valueerror_with_prefix(monkeypatch):
    install_loader(monkeypatch, [report(), report()])
    with pytest.raises(
        ValueError, match=r"^paths\[0\]: must not be empty$"
    ):
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
    install_loader(
        monkeypatch, [report(snapshots=3), report(snapshots=4)]
    )
    with pytest.raises(
        ValueError, match="summary.snapshots 4 does not match 3"
    ):
        dashboard_history_report_trend(["a", "b"])


def test_snapshots_mismatch_checked_before_computing_changes(monkeypatch):
    calls = install_loader(
        monkeypatch,
        [
            report(snapshots=3, stability=0.1),
            report(snapshots=3, stability=0.2),
            report(snapshots=2, stability=0.3),
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
        [report(stability=0.9, quality="pass"),
         report(stability=0.8, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == -0.1
    assert item["volatility_delta"] == 0.0
    assert item["quality"] == "fail"
    assert result["quality"] == "fail"
    assert result["regressed"] == 1


def test_dv_positive_fails(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.0, quality="pass"),
         report(stability=0.5, volatility=0.2, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.0
    assert item["volatility_delta"] == 0.2
    assert item["quality"] == "fail"


def test_fail_to_pass_with_unchanging_metrics_passes(monkeypatch):
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.1, quality="fail"),
         report(stability=0.6, volatility=0.05, quality="pass")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["changes"][0]["quality"] == "pass"
    assert result["changes"][0]["stability_delta"] == 0.1
    assert result["changes"][0]["volatility_delta"] == -0.05
    assert result["quality"] == "pass"
    assert result["regressed"] == 0


def test_pass_to_fail_transition_fails(monkeypatch):
    # Stability improves and volatility drops, but quality still flips
    # pass -> fail: the transition clause must force a fail verdict.
    install_loader(
        monkeypatch,
        [report(stability=0.5, volatility=0.2, quality="pass"),
         report(stability=0.8, volatility=0.05, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    item = result["changes"][0]
    assert item["stability_delta"] == 0.3
    assert item["volatility_delta"] == -0.15
    assert item["quality"] == "fail"
    assert result["quality"] == "fail"


def test_fail_to_fail_with_improving_metrics_passes(monkeypatch):
    # No pass->fail transition and no metric regression -> pass even
    # though both snapshots are individually "fail".
    install_loader(
        monkeypatch,
        [report(stability=0.2, volatility=0.4, quality="fail"),
         report(stability=0.3, volatility=0.3, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["changes"][0]["quality"] == "pass"
    assert result["quality"] == "pass"


def test_all_pass_overall(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.1, volatility=0.5, quality="pass"),
            report(stability=0.2, volatility=0.4, quality="pass"),
            report(stability=0.3, volatility=0.3, quality="pass"),
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
         report(stability=raw, volatility=raw)],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["changes"][0]["stability_delta"] == round(raw, 6)
    assert result["changes"][0]["volatility_delta"] == round(raw, 6)


def test_negative_zero_normalized(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.1, volatility=0.1),
            report(stability=0.1, volatility=0.1),
        ],
    )
    result = dashboard_history_report_trend(["a", "b"])
    for name in ("stability_delta", "volatility_delta"):
        value = result["changes"][0][name]
        assert value == 0.0
        assert math.copysign(1.0, value) == 1.0


def test_worst_minimizes_unrounded_tuple(monkeypatch):
    # Equal ds=-0.5 for all three pairs, so -dv decides:
    # i=1: ds=-0.5, dv= 0.25 -> key (-0.5, -0.25, 1)
    # i=2: ds=-0.5, dv=-0.25 -> key (-0.5,  0.25, 2)
    # i=3: ds=-0.5, dv= 0.5  -> key (-0.5, -0.5,  3) <- smallest
    install_loader(
        monkeypatch,
        [
            report(stability=1.0, volatility=0.0, quality="pass"),
            report(stability=0.5, volatility=0.25, quality="fail"),
            report(stability=0.0, volatility=0.0, quality="fail"),
            report(stability=-0.5, volatility=0.5, quality="fail"),
        ],
    )
    result = dashboard_history_report_trend(["a", "b", "c", "d"])
    assert result["worst"] is result["changes"][2]
    assert result["worst"]["index"] == 3
    assert result["worst"]["stability_delta"] == -0.5
    assert result["worst"]["volatility_delta"] == 0.5


def test_worst_tie_breaks_by_index(monkeypatch):
    # Equal unrounded ds and dv -> smallest i wins (first occurrence).
    install_loader(
        monkeypatch,
        [
            report(stability=0.0, volatility=0.0),
            report(stability=0.0, volatility=0.0),
            report(stability=0.0, volatility=0.0),
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
        [report(stability=0.5), report(stability=0.4, quality="fail")],
    )
    result = dashboard_history_report_trend(["a", "b"])
    assert result["worst"] is result["changes"][0]


def test_count_is_number_of_snapshots(monkeypatch):
    install_loader(
        monkeypatch,
        [report(snapshots=4), report(snapshots=4), report(snapshots=4)],
    )
    result = dashboard_history_report_trend(["a", "b", "c"])
    assert result["count"] == 3


def test_no_extra_keys_and_no_sorting(monkeypatch):
    install_loader(
        monkeypatch,
        [
            report(stability=0.5, volatility=0.1, quality="pass"),
            report(stability=0.4, volatility=0.2, quality="fail"),
            report(stability=0.6, volatility=0.05, quality="pass"),
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
        report(stability=0.2, volatility=0.1),
    ]
    install_loader(monkeypatch, reports)
    dashboard_history_report_trend(paths)
    assert paths == ["a", "b"]
    assert reports[0] == report(stability=0.1, volatility=0.2)
    assert reports[1] == report(stability=0.2, volatility=0.1)


def _dump(report_obj):
    return json.dumps(
        report_obj,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _valid_report(snapshots, stability, volatility):
    # Build a file accepted by the real load_dashboard_history_report:
    # regressed and history must agree with stability/quality. With one
    # change (snapshots=2), stability = 1 - regressed/1 and quality is
    # "pass" iff regressed == 0.
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


def _write(tmp_path, name, report_obj):
    path = tmp_path / name
    path.write_bytes(_dump(report_obj))
    return str(path)


def test_real_files_roundtrip(tmp_path):
    # First snapshot: one regression (stability 0.0, volatility 0.5).
    # Second snapshot: no regression (stability 1.0, volatility 0.0).
    # ds > 0 and dv < 0 and the quality transition is fail -> pass, so
    # the comparison passes.
    p1 = _write(
        tmp_path, "r1.json", _valid_report(2, 0.0, 0.5)
    )
    p2 = _write(
        tmp_path, "r2.json", _valid_report(2, 1.0, 0.0)
    )
    result = dashboard_history_report_trend([p1, p2])
    assert result == {
        "count": 2,
        "changes": (
            {
                "index": 1,
                "stability_delta": 1.0,
                "volatility_delta": -0.5,
                "quality": "pass",
            },
        ),
        "regressed": 0,
        "worst": {
            "index": 1,
            "stability_delta": 1.0,
            "volatility_delta": -0.5,
            "quality": "pass",
        },
        "quality": "pass",
    }


def test_real_files_snapshots_mismatch(tmp_path):
    p1 = _write(
        tmp_path, "r1.json", _valid_report(2, 1.0, 0.0)
    )
    # A 3-snapshot report needs a self-consistent history with 2 changes;
    # easiest is to trigger the mismatch with a minimally different file,
    # so hand-craft one with snapshots=3 by reusing the 2-snapshot body
    # patched through the monkeypatched loader path is not possible here;
    # instead use the actual loader validation which rejects before the
    # snapshots comparison only on malformed files. Build a consistent
    # 3-snapshot file:
    def valid3():
        change = {
            "index": 1,
            "passed_delta": 0,
            "regressed_delta": 0,
            "ratio_delta": 0.0,
            "quality": "pass",
        }
        change2 = {
            "index": 2,
            "passed_delta": 0,
            "regressed_delta": 0,
            "ratio_delta": 0.0,
            "quality": "pass",
        }
        return {
            "schema_version": 1,
            "source": {"path": "in.json", "inputs": ["a", "b", "c"]},
            "history": {
                "count": 3,
                "changes": [change, change2],
                "regressed": 0,
                "worst": change,
                "quality": "pass",
            },
            "summary": {
                "snapshots": 3,
                "regressed": 0,
                "stability": 1.0,
                "volatility": 0.0,
                "longest_regression": 0,
                "worst_index": 1,
            },
            "quality": "pass",
        }

    p2 = _write(tmp_path, "r2.json", valid3())
    with pytest.raises(ValueError, match="summary.snapshots"):
        dashboard_history_report_trend((p1, p2))
