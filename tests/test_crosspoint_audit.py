"""Tests for crosspoint.audit multi-tolerance reporting."""

import math

import pytest

from ocean_sonar import crosspoint
from ocean_sonar.crosspoint import audit, report

# differences: 0.5 and -0.7
CROSSINGS = [(0.0, 0.0, 10.0, 9.5), (1.0, 1.0, 8.0, 8.7)]

REPORT_KEYS = [
    "count",
    "bias",
    "rmse",
    "max_abs",
    "within_tolerance",
    "within_ratio",
    "stdev",
    "quality",
]


def test_multiple_tolerances_return_tuple_of_report_dicts():
    tolerances = [0.5, 0.7, 1.0]
    result = audit(CROSSINGS, tolerances)

    assert isinstance(result, tuple)
    assert len(result) == 3
    for item, tolerance in zip(result, tolerances):
        assert item == report(CROSSINGS, tolerance)
        assert list(item.keys()) == REPORT_KEYS

    # abs(-0.7) > 0.5 but <= 0.7, and 0.5 itself is within via <=.
    assert result[0]["within_tolerance"] == 1
    assert result[0]["quality"] == "fail"
    assert result[1]["within_tolerance"] == 2
    assert result[1]["quality"] == "pass"
    assert result[2]["within_tolerance"] == 2
    assert result[2]["quality"] == "pass"


def test_boundary_tolerance_is_inclusive():
    result = audit(CROSSINGS, [0.5])
    assert result[0]["within_tolerance"] == 1
    assert result[0] == report(CROSSINGS, 0.5)


def test_duplicate_tolerances_kept_and_not_deduplicated():
    result = audit(CROSSINGS, [0.5, 0.5])
    assert len(result) == 2
    assert result[0] == result[1] == report(CROSSINGS, 0.5)


def test_tolerance_order_preserved_without_sorting():
    tolerances = [1.0, 0.5, 1.0]
    result = audit(CROSSINGS, tolerances)
    assert [item["within_tolerance"] for item in result] == [2, 1, 2]
    assert result[0] == result[2]


def test_int_tolerances_and_tuple_crossings_and_tolerances():
    crossings = tuple(CROSSINGS)
    result = audit(crossings, (1, 2))
    assert isinstance(result, tuple)
    assert result == (report(crossings, 1), report(crossings, 2))


def test_values_match_report_rounding_and_negative_zero_rules():
    crossings = [(0.0, 0.0, 5.0, 5.0)]
    result = audit(crossings, [0.25])
    assert result[0] == report(crossings, 0.25)
    assert result[0]["bias"] == 0.0
    assert math.copysign(1.0, result[0]["bias"]) == 1.0
    assert result[0]["stdev"] == 0.0
    assert result[0]["within_ratio"] == 1.0


def test_inputs_not_modified():
    crossings = [
        [0.0, 0.0, 10.0, 9.5],
        [1.0, 1.0, 8, 8.7],
    ]
    tolerances = [0.5, 1, 0.7]
    crossings_before = [list(point) for point in crossings]
    tolerances_before = list(tolerances)

    audit(crossings, tolerances)

    assert crossings == crossings_before
    assert tolerances == tolerances_before
    assert isinstance(crossings[0], list)


def test_report_called_once_per_tolerance_in_input_order(monkeypatch):
    calls = []

    def fake_report(crossings_arg, tolerance):
        calls.append((crossings_arg, tolerance))
        return {"tolerance": tolerance}

    monkeypatch.setattr(crosspoint, "report", fake_report)
    tolerances = [1.0, 0.5, 2.0]
    result = audit(CROSSINGS, tolerances)

    assert [tolerance for _, tolerance in calls] == [1.0, 0.5, 2.0]
    assert all(crossings_arg is CROSSINGS for crossings_arg, _ in calls)
    assert result == ({"tolerance": 1.0}, {"tolerance": 0.5}, {"tolerance": 2.0})


def test_report_exception_propagates_unchanged(monkeypatch):
    def boom(crossings_arg, tolerance):
        if tolerance == 0.5:
            raise RuntimeError("boom")
        return {}

    monkeypatch.setattr(crosspoint, "report", boom)
    with pytest.raises(RuntimeError, match="boom"):
        audit(CROSSINGS, [1.0, 0.5, 2.0])


def test_crossings_type_error_precedes_tolerances_type_error():
    with pytest.raises(TypeError, match="crossings must be a list or tuple"):
        audit("not-a-sequence", "not-a-sequence")


def test_crossings_empty_error_precedes_tolerances_empty_error():
    with pytest.raises(ValueError, match="crossings must be non-empty"):
        audit([], [])


def test_crossings_item_error_precedes_tolerances_element_error():
    bad_crossings = [("x", 0.0, 1.0, 1.0)]
    with pytest.raises(TypeError, match=r"crossings\[0\]: x must be a non-bool int or float"):
        audit(bad_crossings, [True])


def test_crossings_item_order_uses_evaluate_contract():
    bad_crossings = [(0.0, 0.0, 10.0, 9.5), (0.0, 0.0, -1.0, 1.0)]
    with pytest.raises(ValueError, match=r"crossings\[1\]: d1 must be >= 0"):
        audit(bad_crossings, [1.0])


def test_tolerances_container_type_error():
    with pytest.raises(TypeError, match="tolerances must be a list or tuple"):
        audit(CROSSINGS, {0.5})


def test_tolerances_empty_value_error():
    with pytest.raises(ValueError, match="tolerances must be non-empty"):
        audit(CROSSINGS, ())


@pytest.mark.parametrize("bad", [True, False, "0.5", None, 1 + 2j])
def test_tolerance_element_type_error(bad):
    with pytest.raises(
        TypeError, match=r"tolerances\[0\]: must be a non-bool int or float"
    ):
        audit(CROSSINGS, [bad])


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_tolerance_element_non_finite_value_error(bad):
    with pytest.raises(ValueError, match=r"tolerances\[0\]: must be finite"):
        audit(CROSSINGS, [bad])


@pytest.mark.parametrize("bad", [0, 0.0, -1, -0.25])
def test_tolerance_element_non_positive_value_error(bad):
    with pytest.raises(ValueError, match=r"tolerances\[0\]: must be > 0"):
        audit(CROSSINGS, [bad])


def test_tolerance_error_index_prefix():
    with pytest.raises(TypeError, match=r"tolerances\[2\]: must be a non-bool int or float"):
        audit(CROSSINGS, [0.5, 1.0, True])


def test_tolerance_validation_stops_at_first_error():
    # Index 1 fails positivity; the bool at index 2 must never be checked.
    with pytest.raises(ValueError, match=r"tolerances\[1\]: must be > 0"):
        audit(CROSSINGS, [0.5, 0.0, True])


def test_tolerance_type_error_precedes_finite_error():
    with pytest.raises(TypeError, match=r"tolerances\[0\]: must be a non-bool int or float"):
        audit(CROSSINGS, [[float("inf")]])
