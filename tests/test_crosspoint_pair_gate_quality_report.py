"""Tests for crosspoint.pair_gate_quality_report."""

import copy
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import pair_gate_quality, pair_gate_quality_report

FIRST = [
    (0.0, 0.0, 10.0),
    (1.0, 0.0, 5.0),
    (2.0, 0.0, 8.0),
]
SECOND = [
    (0.0, 0.0, 10.0),
    (1.0, 0.0, 5.0),
    (2.0, 0.0, 8.0),
]
TOLERANCES = [0.5, 1.0]


def test_happy_path_perfect_match_passes():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)

    assert result["quality"] == "pass"
    assert result["thresholds"] == {"min_coverage": 1.0, "min_score": 100.0}
    assert result["margins"] == {"coverage_margin": 0.0, "score_margin": 0.0}
    assert result["report"] == pair_gate_quality(FIRST, SECOND, TOLERANCES)


def test_key_orders():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)

    assert list(result.keys()) == ["report", "thresholds", "margins", "quality"]
    assert list(result["thresholds"].keys()) == ["min_coverage", "min_score"]
    assert list(result["margins"].keys()) == ["coverage_margin", "score_margin"]


def test_thresholds_and_margins_values():
    result = pair_gate_quality_report(
        FIRST, SECOND, TOLERANCES, 1.0, 0.5, 40.0
    )

    assert result["thresholds"] == {"min_coverage": 0.5, "min_score": 40.0}
    assert result["margins"] == {"coverage_margin": 0.5, "score_margin": 60.0}
    assert result["quality"] == "pass"


def test_int_thresholds_become_floats():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, 1, 100)

    assert result["thresholds"] == {"min_coverage": 1.0, "min_score": 100.0}
    assert type(result["thresholds"]["min_coverage"]) is float
    assert type(result["thresholds"]["min_score"]) is float


def test_threshold_boundaries_accepted():
    for min_coverage, min_score in ((0, 0), (0.0, 0.0), (1, 100), (1.0, 100.0)):
        result = pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, 1.0, min_coverage, min_score
        )
        assert result["thresholds"]["min_coverage"] == float(min_coverage)
        assert result["thresholds"]["min_score"] == float(min_score)


def test_negative_zero_thresholds_normalized():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, -0.0, -0.0)

    assert result["thresholds"] == {"min_coverage": 0.0, "min_score": 0.0}
    for value in result["thresholds"].values():
        assert math.copysign(1.0, value) == 1.0


def test_zero_margins_are_positive_zero():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)

    for value in result["margins"].values():
        assert value == 0.0
        assert math.copysign(1.0, value) == 1.0


def test_quality_fail_propagated():
    second = [(0.0, 0.0, 10.25), (1.0, 0.0, 4.75), (2.0, 0.0, 7.5)]
    result = pair_gate_quality_report(FIRST, second, [0.1])

    assert result["quality"] == "fail"
    assert result["report"]["quality"] == "fail"
    assert result["margins"]["score_margin"] == -100.0


@pytest.mark.parametrize("value", [True, False, "0.5", None, [0.5]])
def test_min_coverage_type_errors(value):
    with pytest.raises(
        TypeError, match="^min_coverage must be a non-bool int or float$"
    ):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, 1.0, value, 100.0
        )


@pytest.mark.parametrize("value", [True, False, "50", None, [50.0]])
def test_min_score_type_errors(value):
    with pytest.raises(
        TypeError, match="^min_score must be a non-bool int or float$"
    ):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, 1.0, value)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_min_coverage_non_finite(value):
    with pytest.raises(ValueError, match="^min_coverage must be finite$"):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, 1.0, value, 100.0
        )


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_min_score_non_finite(value):
    with pytest.raises(ValueError, match="^min_score must be finite$"):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, 1.0, value)


@pytest.mark.parametrize("value", [-0.1, 1.1, 2, -(10 ** 400), 10 ** 400])
def test_min_coverage_out_of_range(value):
    with pytest.raises(ValueError, match="^min_coverage must be in \\[0, 1\\]$"):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, 1.0, value, 100.0
        )


@pytest.mark.parametrize("value", [-0.1, 100.1, 101, -(10 ** 400), 10 ** 400])
def test_min_score_out_of_range(value):
    with pytest.raises(ValueError, match="^min_score must be in \\[0, 100\\]$"):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, 1.0, value)


def test_min_coverage_validated_before_min_score():
    with pytest.raises(
        TypeError, match="^min_coverage must be a non-bool int or float$"
    ):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, "x", "y")
    with pytest.raises(ValueError, match="^min_coverage must be in \\[0, 1\\]$"):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 1.0, 2.0, "y")


def test_pair_gate_quality_called_exactly_once_with_all_arguments():
    calls = []
    original = crosspoint_mod.pair_gate_quality

    def spy(first, second, tolerances, match_tolerance=1.0,
            min_coverage=1.0, min_score=100.0):
        calls.append(
            (first, second, tolerances, match_tolerance, min_coverage, min_score)
        )
        return original(
            first, second, tolerances, match_tolerance, min_coverage, min_score
        )

    crosspoint_mod.pair_gate_quality = spy
    try:
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 0.25, 0.5, 90.0)
    finally:
        crosspoint_mod.pair_gate_quality = original

    assert calls == [(FIRST, SECOND, TOLERANCES, 0.25, 0.5, 90.0)]


def test_default_arguments_forwarded():
    calls = []
    original = crosspoint_mod.pair_gate_quality

    def spy(first, second, tolerances, match_tolerance=1.0,
            min_coverage=1.0, min_score=100.0):
        calls.append((match_tolerance, min_coverage, min_score))
        return original(
            first, second, tolerances, match_tolerance, min_coverage, min_score
        )

    crosspoint_mod.pair_gate_quality = spy
    try:
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = original

    assert calls == [(1.0, 1.0, 100.0)]


def test_report_identity_and_quality_from_result():
    sentinel = {
        "report": {
            "summary": {"coverage_product": 0.75},
            "score_report": {"score_report": {"score": 80.0}},
        },
        "checks": {"coverage_ok": True, "score_ok": True},
        "quality": "fail",
    }
    calls = []

    def fake_pair_gate_quality(first, second, tolerances, match_tolerance=1.0,
                               min_coverage=1.0, min_score=100.0):
        calls.append(
            (first, second, tolerances, match_tolerance, min_coverage, min_score)
        )
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_pair_gate_quality
    try:
        result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES, 0.5, 0.5, 50.0)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert calls == [(FIRST, SECOND, TOLERANCES, 0.5, 0.5, 50.0)]
    assert result["report"] is sentinel
    assert result["quality"] == "fail"
    assert result["thresholds"] == {"min_coverage": 0.5, "min_score": 50.0}
    assert result["margins"] == {"coverage_margin": 0.25, "score_margin": 30.0}


def test_pair_gate_quality_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    def boom_pair_gate_quality(*args, **kwargs):
        raise Boom("pair_gate_quality failed")

    crosspoint_mod.pair_gate_quality = boom_pair_gate_quality
    try:
        with pytest.raises(Boom, match="^pair_gate_quality failed$"):
            pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality


def test_inner_validation_exceptions_propagate():
    with pytest.raises(ValueError, match="^first must be non-empty$"):
        pair_gate_quality_report([], SECOND, TOLERANCES)
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        pair_gate_quality_report(FIRST, SECOND, [])
    with pytest.raises(TypeError, match="^tolerance must be a non-bool int or float$"):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, match_tolerance="x")


def test_inputs_not_modified():
    first = copy.deepcopy(FIRST)
    second = copy.deepcopy(SECOND)
    tolerances = copy.deepcopy(TOLERANCES)
    snapshots = copy.deepcopy((first, second, tolerances))

    pair_gate_quality_report(first, second, tolerances, 0.75, 0.9, 80.0)

    assert (first, second, tolerances) == snapshots


def test_pair_gate_quality_report_exported_in_all():
    assert "pair_gate_quality_report" in crosspoint_mod.__all__
    assert crosspoint_mod.pair_gate_quality_report is pair_gate_quality_report
