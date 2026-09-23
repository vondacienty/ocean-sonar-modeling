"""Tests for crosspoint.audit."""

import copy
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import audit, evaluate, report

CROSSINGS = [
    (0.0, 0.0, 10.0, 10.25),  # r = -0.25
    (1.0, 1.0, 5.0, 4.75),    # r = 0.25
    (2.0, 2.0, 8.0, 7.5),     # r = 0.5
]

EXPECTED_KEYS = [
    "count",
    "bias",
    "rmse",
    "max_abs",
    "within_tolerance",
    "within_ratio",
    "stdev",
    "quality",
]


def test_multiple_tolerances():
    tolerances = [0.1, 0.25, 0.5, 1.0]
    result = audit(CROSSINGS, tolerances)

    assert isinstance(result, tuple)
    assert len(result) == len(tolerances)
    for item, tolerance in zip(result, tolerances):
        assert item == report(CROSSINGS, tolerance)
        assert list(item.keys()) == EXPECTED_KEYS

    within = [item["within_tolerance"] for item in result]
    assert within == [0, 2, 3, 3]
    assert [item["quality"] for item in result] == ["fail", "fail", "pass", "pass"]


def test_tuple_inputs():
    tolerances = (0.2, 0.5)
    crossings = tuple(CROSSINGS)
    result = audit(crossings, tolerances)

    assert isinstance(result, tuple)
    assert result == (report(crossings, 0.2), report(crossings, 0.5))


def test_int_tolerances_accepted():
    result = audit(CROSSINGS, [1])
    assert result == (report(CROSSINGS, 1),)
    assert result[0]["quality"] == "pass"


def test_duplicate_tolerances_call_report_each_time():
    calls = []
    original = crosspoint_mod.report

    def spy(crossings, tolerance=0.5):
        calls.append(tolerance)
        return original(crossings, tolerance)

    crosspoint_mod.report = spy
    try:
        result = audit(CROSSINGS, [0.2, 0.2, 0.2])
    finally:
        crosspoint_mod.report = original

    assert calls == [0.2, 0.2, 0.2]
    assert len(result) == 3
    assert result[0] == result[1] == result[2] == report(CROSSINGS, 0.2)


def test_boundary_tolerance_is_inclusive():
    # |r| = 0.5 exactly for the third crosspoint; boundary must count.
    result = audit(CROSSINGS, [0.5])
    assert result[0]["within_tolerance"] == 3
    assert result[0]["quality"] == "pass"

    result = audit(CROSSINGS, [0.499999])
    assert result[0]["within_tolerance"] == 2
    assert result[0]["quality"] == "fail"


def test_tolerance_boundary_zero_rejected():
    with pytest.raises(ValueError, match=r"^tolerances\[0\]: must be > 0$"):
        audit(CROSSINGS, [0])


def test_inputs_not_modified():
    crossings = copy.deepcopy(CROSSINGS)
    tolerances = [0.1, 0.5, 1.0]
    crossings_snapshot = copy.deepcopy(crossings)
    tolerances_snapshot = copy.deepcopy(tolerances)

    audit(crossings, tolerances)

    assert crossings == crossings_snapshot
    assert tolerances == tolerances_snapshot


def test_values_match_report_rounding_and_negative_zero():
    # Symmetric differences give bias that rounds to negative zero.
    crossings = [(0.0, 0.0, 10.0, 10.25), (1.0, 1.0, 5.0, 4.75)]
    result = audit(crossings, [0.5])
    expected = report(crossings, 0.5)
    assert result == (expected,)
    assert math.copysign(1.0, result[0]["bias"]) == 1.0
    assert result[0]["bias"] == 0.0


def test_tolerances_wrong_container_type():
    with pytest.raises(TypeError, match="^tolerances must be a list or tuple$"):
        audit(CROSSINGS, {0.5})
    with pytest.raises(TypeError, match="^tolerances must be a list or tuple$"):
        audit(CROSSINGS, "0.5")


def test_tolerances_empty():
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        audit(CROSSINGS, [])
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        audit(CROSSINGS, ())


def test_tolerance_wrong_element_type():
    with pytest.raises(TypeError, match=r"^tolerances\[0\]: must be a non-bool int or float$"):
        audit(CROSSINGS, ["0.5"])
    with pytest.raises(TypeError, match=r"^tolerances\[1\]: must be a non-bool int or float$"):
        audit(CROSSINGS, [0.5, True])
    with pytest.raises(TypeError, match=r"^tolerances\[1\]: must be a non-bool int or float$"):
        audit(CROSSINGS, [0.5, None])


def test_tolerance_non_finite():
    with pytest.raises(ValueError, match=r"^tolerances\[0\]: must be finite$"):
        audit(CROSSINGS, [float("inf")])
    with pytest.raises(ValueError, match=r"^tolerances\[1\]: must be finite$"):
        audit(CROSSINGS, [0.5, float("-inf")])
    with pytest.raises(ValueError, match=r"^tolerances\[1\]: must be finite$"):
        audit(CROSSINGS, [0.5, float("nan")])


def test_tolerance_non_positive():
    with pytest.raises(ValueError, match=r"^tolerances\[0\]: must be > 0$"):
        audit(CROSSINGS, [-0.5])
    with pytest.raises(ValueError, match=r"^tolerances\[1\]: must be > 0$"):
        audit(CROSSINGS, [0.5, -1])


def test_first_bad_tolerance_wins():
    with pytest.raises(TypeError, match=r"^tolerances\[1\]: must be a non-bool int or float$"):
        audit(CROSSINGS, [0.5, "bad", -1.0])
    with pytest.raises(ValueError, match=r"^tolerances\[2\]: must be > 0$"):
        audit(CROSSINGS, [0.5, 0.6, -1.0, "also bad"])


def test_crossings_validated_before_tolerances():
    # Bad crossings container beats bad tolerances container.
    with pytest.raises(TypeError, match="^crossings must be a list or tuple$"):
        audit({0.5}, "bad")
    # Empty crossings beats even a badly typed tolerances container.
    with pytest.raises(ValueError, match="^crossings must be non-empty$"):
        audit([], "bad")
    # Bad crossings item beats bad tolerances item/container.
    with pytest.raises(TypeError, match=r"^crossings\[0\]: must be a list or tuple$"):
        audit([object()], ["bad"])
    with pytest.raises(ValueError, match=r"^crossings\[0\]: must have 4 elements$"):
        audit([(1.0, 2.0, 3.0)], [])
    with pytest.raises(TypeError, match=r"^crossings\[0\]: x must be a non-bool int or float$"):
        audit([("x", 0.0, 1.0, 1.0)], [-1.0])
    with pytest.raises(ValueError, match=r"^crossings\[0\]: d1 must be >= 0$"):
        audit([(0.0, 0.0, -1.0, 1.0)], [-1.0])
    # First bad crossing index wins over tolerances errors.
    with pytest.raises(TypeError, match=r"^crossings\[1\]: must be a list or tuple$"):
        audit([CROSSINGS[0], object()], ["bad"])


def test_tolerances_validated_before_any_report_call():
    calls = []

    def boom(crossings, tolerance=0.5):
        calls.append(tolerance)
        raise AssertionError("report should not be called")

    crosspoint_mod.report = boom
    try:
        with pytest.raises((TypeError, ValueError)):
            audit(CROSSINGS, [0.5, "bad"])
    finally:
        crosspoint_mod.report = report

    assert calls == []


def test_report_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    def fake_report(crossings, tolerance=0.5):
        if tolerance == 0.5:
            return {"ok": True}
        raise Boom(tolerance)

    crosspoint_mod.report = fake_report
    try:
        with pytest.raises(Boom):
            audit(CROSSINGS, [0.5, 0.6])
    finally:
        crosspoint_mod.report = report


def test_evaluate_and_report_behaviour_unchanged():
    assert list(evaluate(CROSSINGS, 0.5).keys()) == [
        "count",
        "bias",
        "rmse",
        "max_abs",
        "within_tolerance",
        "quality",
    ]
    assert list(report(CROSSINGS, 0.5).keys()) == EXPECTED_KEYS
    with pytest.raises(ValueError, match="tolerance must be > 0"):
        evaluate(CROSSINGS, 0)
    with pytest.raises(ValueError, match="tolerance must be finite"):
        report(CROSSINGS, float("nan"))


def test_audit_exported_in_all():
    assert "audit" in crosspoint_mod.__all__
    assert crosspoint_mod.audit is audit
