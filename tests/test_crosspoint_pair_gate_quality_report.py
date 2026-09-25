"""Tests for crosspoint.pair_gate_quality_report."""

import copy
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    pair_gate_quality,
    pair_gate_quality_report,
)

FIRST = [
    (0.0, 0.0, 10.0),
    (1.0, 0.0, 5.0),
    (2.0, 0.0, 8.0),
]
SECOND = [
    (0.0, 0.0, 10.25),  # r = -0.25
    (1.0, 0.0, 4.75),   # r = 0.25
    (2.0, 0.0, 7.5),    # r = 0.5
]
TOLERANCES = [0.5, 1.0]


def _sentinel_report(coverage=0.5, score=80.0, quality="pass"):
    return {
        "report": {
            "summary": {"coverage_product": coverage},
            "score_report": {"score_report": {"score": score}},
        },
        "checks": {},
        "quality": quality,
    }


def test_happy_path_structure_and_values():
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)

    quality = pair_gate_quality(FIRST, SECOND, TOLERANCES)
    assert result["report"] == quality
    assert result["quality"] == quality["quality"] == "pass"

    assert list(result.keys()) == ["report", "thresholds", "margins", "quality"]
    assert list(result["thresholds"].keys()) == ["min_coverage", "min_score"]
    assert list(result["margins"].keys()) == [
        "coverage_margin",
        "score_margin",
    ]

    summary = quality["report"]["summary"]
    score = quality["report"]["score_report"]["score_report"]["score"]
    assert result["thresholds"] == {"min_coverage": 1.0, "min_score": 100.0}
    assert result["margins"] == {
        "coverage_margin": round(summary["coverage_product"] - 1.0, 6),
        "score_margin": round(score - 100.0, 6),
    }


def test_thresholds_round_and_convert_to_float():
    result = pair_gate_quality_report(
        FIRST, SECOND, TOLERANCES, min_coverage=1, min_score=100
    )
    assert result["thresholds"] == {"min_coverage": 1.0, "min_score": 100.0}
    assert {type(v) for v in result["thresholds"].values()} == {float}

    result = pair_gate_quality_report(
        FIRST, SECOND, TOLERANCES, min_coverage=1 / 3, min_score=1 / 3
    )
    assert result["thresholds"] == {
        "min_coverage": round(1 / 3, 6),
        "min_score": round(1 / 3, 6),
    }


def test_threshold_negative_zero_normalized():
    result = pair_gate_quality_report(
        FIRST, SECOND, TOLERANCES, min_coverage=-0.0, min_score=-0.0
    )
    for value in result["thresholds"].values():
        assert value == 0.0
        assert math.copysign(1.0, value) == 1.0


def test_margin_negative_zero_normalized():
    sentinel = _sentinel_report(coverage=-0.0, score=-0.0)

    def fake_quality(*args, **kwargs):
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_quality
    try:
        result = pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, min_coverage=0.0, min_score=0.0
        )
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert result["margins"] == {"coverage_margin": 0.0, "score_margin": 0.0}
    for value in result["margins"].values():
        assert math.copysign(1.0, value) == 1.0


def test_report_identity_and_quality_identity():
    sentinel = _sentinel_report(quality="fail")

    def fake_quality(*args, **kwargs):
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_quality
    try:
        result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert result["report"] is sentinel
    assert result["quality"] is sentinel["quality"]


def test_called_exactly_once_with_full_arguments():
    calls = []
    sentinel = _sentinel_report()

    def fake_quality(
        first,
        second,
        tolerances,
        match_tolerance=1.0,
        min_coverage=1.0,
        min_score=100.0,
    ):
        calls.append(
            (first, second, tolerances, match_tolerance, min_coverage, min_score)
        )
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_quality
    try:
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, 0.25, 0.4, 70
        )
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert calls == [
        (FIRST, SECOND, TOLERANCES, 0.25, 0.4, 70),
        (FIRST, SECOND, TOLERANCES, 1.0, 1.0, 100.0),
    ]


def test_margins_use_nested_paths_without_recomputation():
    sentinel = _sentinel_report(coverage=0.5, score=80.0)

    def fake_quality(*args, **kwargs):
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_quality
    try:
        result = pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, min_coverage=0.4, min_score=70
        )
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert result["margins"] == {
        "coverage_margin": 0.1,
        "score_margin": 10.0,
    }
    assert result["quality"] == "pass"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_coverage": 0},
        {"min_coverage": 1},
        {"min_coverage": 0.0},
        {"min_coverage": 1.0},
        {"min_score": 0},
        {"min_score": 100},
        {"min_score": 0.0},
        {"min_score": 100.0},
    ],
)
def test_threshold_boundaries_accepted(kwargs):
    result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES, **kwargs)
    assert set(result["thresholds"].keys()) == {"min_coverage", "min_score"}


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"min_coverage": True}, "min_coverage must be a non-bool int or float"),
        ({"min_coverage": False}, "min_coverage must be a non-bool int or float"),
        ({"min_coverage": "1"}, "min_coverage must be a non-bool int or float"),
        ({"min_coverage": [1]}, "min_coverage must be a non-bool int or float"),
        ({"min_score": True}, "min_score must be a non-bool int or float"),
        ({"min_score": None}, "min_score must be a non-bool int or float"),
        ({"min_coverage": math.nan}, "min_coverage must be finite"),
        ({"min_coverage": math.inf}, "min_coverage must be finite"),
        ({"min_score": math.nan}, "min_score must be finite"),
        ({"min_score": -math.inf}, "min_score must be finite"),
        ({"min_coverage": -0.1}, "min_coverage must be in \\[0, 1\\]"),
        ({"min_coverage": 1.1}, "min_coverage must be in \\[0, 1\\]"),
        ({"min_score": -0.1}, "min_score must be in \\[0, 100\\]"),
        ({"min_score": 100.1}, "min_score must be in \\[0, 100\\]"),
        ({"min_coverage": 10 ** 400}, "min_coverage must be in \\[0, 1\\]"),
        ({"min_score": 10 ** 400}, "min_score must be in \\[0, 100\\]"),
    ],
)
def test_invalid_thresholds_raise(kwargs, match):
    with pytest.raises((TypeError, ValueError), match=match):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, **kwargs)


def test_bool_rejected_as_type_error_not_value_error():
    with pytest.raises(TypeError):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, min_coverage=True)
    with pytest.raises(TypeError):
        pair_gate_quality_report(FIRST, SECOND, TOLERANCES, min_score=False)


def test_min_coverage_validated_before_min_score():
    # Both invalid: the min_coverage error must win.
    with pytest.raises(TypeError, match="min_coverage"):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, min_coverage="x", min_score="y"
        )
    with pytest.raises(ValueError, match="min_coverage must be finite"):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, min_coverage=math.nan, min_score=math.nan
        )
    # A valid min_coverage lets the min_score error surface.
    with pytest.raises(ValueError, match="min_score must be in"):
        pair_gate_quality_report(
            FIRST, SECOND, TOLERANCES, min_coverage=1.0, min_score=101
        )


def test_pair_gate_quality_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    def boom(*args, **kwargs):
        raise Boom("quality failed")

    crosspoint_mod.pair_gate_quality = boom
    try:
        with pytest.raises(Boom, match="^quality failed$"):
            pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality


def test_upstream_validation_propagates():
    with pytest.raises(ValueError, match="^first must be non-empty$"):
        pair_gate_quality_report([], SECOND, TOLERANCES)
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        pair_gate_quality_report(FIRST, SECOND, [])


def test_inputs_not_modified():
    first = copy.deepcopy(FIRST)
    second = copy.deepcopy(SECOND)
    tolerances = copy.deepcopy(TOLERANCES)
    snapshots = copy.deepcopy((first, second, tolerances))

    pair_gate_quality_report(
        first, second, tolerances, 0.75, 0.5, 90.0
    )

    assert (first, second, tolerances) == snapshots


def test_returned_report_not_mutated():
    sentinel = _sentinel_report()
    sentinel_keys_before = list(sentinel.keys())

    def fake_quality(*args, **kwargs):
        return sentinel

    crosspoint_mod.pair_gate_quality = fake_quality
    try:
        result = pair_gate_quality_report(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_quality = pair_gate_quality

    assert list(result["report"].keys()) == sentinel_keys_before


def test_exported_in_all():
    assert "pair_gate_quality_report" in crosspoint_mod.__all__
    assert crosspoint_mod.pair_gate_quality_report is pair_gate_quality_report
