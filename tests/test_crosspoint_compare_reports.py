"""Tests for crosspoint.compare_reports."""

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import compare_reports


def make_summary(degraded, coverage_delta, score_delta, quality):
    """Build a load_trend_report-shaped summary (worst is unused here)."""
    return {
        "file_count": 2,
        "changes": 1,
        "degraded": degraded,
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "worst": (0, 1, 0, 0, 0.0, 0.0),
        "quality": quality,
    }


def make_report(sources, summary):
    return {"sources": list(sources), "summary": summary}


SOURCES = ["a.json", "b.json"]


@pytest.fixture
def report_loader(monkeypatch):
    """Patch load_trend_report to serve queued reports; tracks loaded paths."""
    state = {"loaded": []}

    def install(reports):
        queue = list(reports)

        def fake_load_trend_report(path):
            state["loaded"].append(path)
            return queue.pop(0)

        monkeypatch.setattr(
            crosspoint_mod, "load_trend_report", fake_load_trend_report
        )

    install.loaded = state["loaded"]
    return install


EXPECTED_TOP_KEYS = ["changes", "worst", "quality"]
EXPECTED_CHANGE_KEYS = [
    "index",
    "degraded_delta",
    "coverage_delta",
    "score_delta",
    "quality",
]


def test_compare_reports_basic(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(1, 0.1, 1.0, "fail")),
        make_report(SOURCES, make_summary(1, 0.05, 0.5, "fail")),
    ]
    report_loader(reports)
    paths = ["r0.json", "r1.json", "r2.json"]

    result = compare_reports(list(paths))

    assert report_loader.loaded == paths
    assert list(result.keys()) == EXPECTED_TOP_KEYS
    assert isinstance(result["changes"], tuple)
    assert len(result["changes"]) == 2

    first = result["changes"][0]
    assert list(first.keys()) == EXPECTED_CHANGE_KEYS
    assert first == {
        "index": 1,
        "degraded_delta": 1,
        "coverage_delta": 0.1,
        "score_delta": 1.0,
        "quality": "fail",
    }
    assert type(first["index"]) is int
    assert type(first["degraded_delta"]) is int
    assert type(first["coverage_delta"]) is float
    assert type(first["score_delta"]) is float

    second = result["changes"][1]
    assert second == {
        "index": 2,
        "degraded_delta": 0,
        "coverage_delta": -0.05,
        "score_delta": -0.5,
        "quality": "fail",
    }

    # Worst uses the unrounded tuple (ds, dc, -dd, i): i=2 has ds=-0.5.
    assert result["worst"] is second
    assert result["quality"] == "fail"


def test_compare_reports_pass_when_unchanged(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json"])
    assert result["changes"] == (
        {
            "index": 1,
            "degraded_delta": 0,
            "coverage_delta": 0.0,
            "score_delta": 0.0,
            "quality": "pass",
        },
    )
    assert result["worst"] is result["changes"][0]
    assert result["quality"] == "pass"


def test_compare_reports_fail_to_pass_is_pass(report_loader):
    reports = [
        make_report(SOURCES, make_summary(1, -0.1, -1.0, "fail")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json"])
    assert result["changes"][0] == {
        "index": 1,
        "degraded_delta": -1,
        "coverage_delta": 0.1,
        "score_delta": 1.0,
        "quality": "pass",
    }
    assert result["quality"] == "pass"


def test_compare_reports_pass_to_fail_alone_fails(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "fail")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json"])
    assert result["changes"][0]["quality"] == "fail"
    assert result["quality"] == "fail"


def test_compare_reports_top_quality_requires_all_pass(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.1, 1.0, "pass")),
        make_report(SOURCES, make_summary(1, 0.2, 2.0, "fail")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json", "r2.json"])
    assert result["changes"][0]["quality"] == "pass"
    assert result["changes"][1]["quality"] == "fail"
    assert result["quality"] == "fail"


def test_compare_reports_degraded_increase_alone_fails(report_loader):
    reports = [
        make_report(SOURCES, make_summary(1, 0.0, 0.0, "fail")),
        make_report(SOURCES, make_summary(2, 0.0, 0.0, "fail")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json"])
    assert result["changes"][0]["degraded_delta"] == 1
    assert result["changes"][0]["quality"] == "fail"


def test_compare_reports_negative_zero_normalized(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, -0.0, -0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json"])
    change = result["changes"][0]
    assert change["coverage_delta"] == 0.0
    assert change["score_delta"] == 0.0
    import math

    assert math.copysign(1.0, change["coverage_delta"]) == 1.0
    assert math.copysign(1.0, change["score_delta"]) == 1.0
    # -0.0 is not less than zero, so the comparison passes.
    assert change["quality"] == "pass"
    assert result["quality"] == "pass"


def test_compare_reports_worst_uses_unrounded_deltas(report_loader):
    # 0.3 - 0.1 == 0.19999999999999998 (rounds to 0.2)
    # 0.5 - 0.3 == 0.2 exactly; both rounded dc values are 0.2.
    reports = [
        make_report(SOURCES, make_summary(0, 0.1, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.3, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.5, 0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json", "r2.json"])
    assert result["changes"][0]["coverage_delta"] == 0.2
    assert result["changes"][1]["coverage_delta"] == 0.2
    assert result["worst"]["index"] == 1
    assert result["worst"] is result["changes"][0]


def test_compare_reports_worst_tie_prefers_lower_index(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(["r0.json", "r1.json", "r2.json"])
    assert result["worst"] is result["changes"][0]
    assert result["worst"]["index"] == 1


def test_compare_reports_tuple_paths(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)

    result = compare_reports(("r0.json", "r1.json"))
    assert result["quality"] == "pass"


def test_compare_reports_paths_container_validation():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        compare_reports({})
    with pytest.raises(TypeError):
        compare_reports("a/b")


def test_compare_reports_paths_count_validation():
    with pytest.raises(ValueError, match="at least 2 items"):
        compare_reports([])
    # Count is checked before item types.
    with pytest.raises(ValueError, match="at least 2 items"):
        compare_reports([123])


def test_compare_reports_paths_item_validation():
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        compare_reports(["a", 5])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        compare_reports(["", "b"])
    # Items are checked in index order.
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        compare_reports([None, ""])


def test_compare_reports_loads_each_path_once_in_order(report_loader):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.1, 1.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.2, 2.0, "pass")),
    ]
    report_loader(reports)
    paths = ["r0.json", "r1.json", "r2.json"]

    compare_reports(paths)
    assert report_loader.loaded == paths


def test_compare_reports_load_exception_propagates(report_loader):
    class Boom(Exception):
        pass

    def fake_load_trend_report(path):
        if path == "r1.json":
            raise Boom("disk on fire")
        return make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass"))

    import unittest.mock

    with unittest.mock.patch.object(
        crosspoint_mod, "load_trend_report", side_effect=fake_load_trend_report
    ) as mocked:
        with pytest.raises(Boom, match="disk on fire"):
            compare_reports(["r0.json", "r1.json", "r2.json"])
        assert mocked.call_count == 2


def test_compare_reports_missing_file_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        compare_reports(
            [str(tmp_path / "nope1.json"), str(tmp_path / "nope2.json")]
        )


def test_compare_reports_sources_mismatch_value_error(report_loader):
    reports = [
        make_report(["a.json", "b.json"], make_summary(0, 0.0, 0.0, "pass")),
        make_report(["a.json", "c.json"], make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)
    with pytest.raises(ValueError, match="sources"):
        compare_reports(["r0.json", "r1.json"])


def test_compare_reports_sources_order_mismatch_value_error(report_loader):
    reports = [
        make_report(["a.json", "b.json"], make_summary(0, 0.0, 0.0, "pass")),
        make_report(["b.json", "a.json"], make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)
    with pytest.raises(ValueError, match="sources"):
        compare_reports(["r0.json", "r1.json"])


def test_compare_reports_sources_length_mismatch_value_error(report_loader):
    reports = [
        make_report(["a.json", "b.json"], make_summary(0, 0.0, 0.0, "pass")),
        make_report(["a.json"], make_summary(1, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)
    with pytest.raises(ValueError, match="sources"):
        compare_reports(["r0.json", "r1.json"])


def test_compare_reports_inputs_and_reports_not_modified(report_loader):
    first = make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass"))
    second = make_report(SOURCES, make_summary(1, 0.1, 1.0, "fail"))
    import copy

    snapshots = [copy.deepcopy(first), copy.deepcopy(second)]
    report_loader(snapshots)
    paths = ["r0.json", "r1.json"]

    compare_reports(list(paths))

    assert paths == ["r0.json", "r1.json"]
    assert snapshots[0] == first
    assert snapshots[1] == second


def test_compare_reports_exported():
    assert hasattr(crosspoint_mod, "compare_reports")
    assert "compare_reports" in crosspoint_mod.__all__
    assert crosspoint_mod.compare_reports is compare_reports
