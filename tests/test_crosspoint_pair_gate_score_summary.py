"""Tests for crosspoint.pair_gate_score_summary."""

import copy
import inspect
import typing

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    pair_gate_score_report,
    pair_gate_score_summary,
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


def test_pair_gate_score_report_signature():
    signature = inspect.signature(pair_gate_score_report)

    assert list(signature.parameters) == [
        "first",
        "second",
        "tolerances",
        "match_tolerance",
        "min_mean_ratio",
        "max_rmse_limit",
    ]
    assert signature.parameters["match_tolerance"].default == 1.0
    assert signature.parameters["min_mean_ratio"].default == 1.0
    assert signature.parameters["max_rmse_limit"].default == 1.0
    assert typing.get_type_hints(pair_gate_score_report)["return"] is dict


def test_pair_gate_score_summary_signature():
    signature = inspect.signature(pair_gate_score_summary)

    assert list(signature.parameters) == [
        "first",
        "second",
        "tolerances",
        "match_tolerance",
        "min_mean_ratio",
        "max_rmse_limit",
    ]
    assert signature.parameters["match_tolerance"].default == 1.0
    assert signature.parameters["min_mean_ratio"].default == 1.0
    assert signature.parameters["max_rmse_limit"].default == 1.0
    assert typing.get_type_hints(pair_gate_score_summary)["return"] is dict


def test_happy_path_matches_score_report():
    result = pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    expected = pair_gate_score_report(FIRST, SECOND, TOLERANCES)

    assert list(result.keys()) == ["score_report", "summary", "quality"]
    assert result["score_report"] == expected
    assert result["quality"] == "pass"


def test_summary_key_order_and_values():
    result = pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    report = result["score_report"]
    summary = result["summary"]

    assert list(summary.keys()) == [
        "coverage_product",
        "score_margin",
        "matched",
        "pair_quality",
    ]
    assert summary["coverage_product"] == report["metrics"]["coverage_product"]
    assert summary["score_margin"] == report["metrics"]["score_margin"]
    assert summary["matched"] == report["score_report"]["matching"]["matched"]
    assert summary["pair_quality"] == report["score_report"]["pair_gate"]["quality"]


def test_summary_value_types():
    summary = pair_gate_score_summary(FIRST, SECOND, TOLERANCES)["summary"]

    assert isinstance(summary["coverage_product"], float)
    assert isinstance(summary["score_margin"], float)
    assert isinstance(summary["matched"], int)
    assert not isinstance(summary["matched"], bool)
    assert isinstance(summary["pair_quality"], str)


def test_score_report_is_original_object_and_called_once():
    sentinel_metrics = {"coverage_product": 1.0, "score_margin": 0.0}
    sentinel_report = {
        "metrics": sentinel_metrics,
        "score_report": {
            "matching": {"matched": 3},
            "pair_gate": {"quality": "pass"},
        },
        "quality": "pass",
    }
    calls = []

    def fake_report(
        first,
        second,
        tolerances,
        match_tolerance=1.0,
        min_mean_ratio=1.0,
        max_rmse_limit=1.0,
    ):
        calls.append(
            (first, second, tolerances, match_tolerance, min_mean_ratio, max_rmse_limit)
        )
        return sentinel_report

    original = crosspoint_mod.pair_gate_score_report
    crosspoint_mod.pair_gate_score_report = fake_report
    try:
        result = pair_gate_score_summary(FIRST, SECOND, TOLERANCES, 0.25, 0.5, 0.9)
    finally:
        crosspoint_mod.pair_gate_score_report = original

    assert calls == [(FIRST, SECOND, TOLERANCES, 0.25, 0.5, 0.9)]
    assert result["score_report"] is sentinel_report
    assert result["summary"] == {
        "coverage_product": 1.0,
        "score_margin": 0.0,
        "matched": 3,
        "pair_quality": "pass",
    }
    assert result["quality"] == "pass"


def test_default_arguments_forwarded():
    calls = []
    original = crosspoint_mod.pair_gate_score_report

    def spy_report(*args):
        calls.append(args)
        return original(*args)

    crosspoint_mod.pair_gate_score_report = spy_report
    try:
        pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_score_report = original

    assert calls == [(FIRST, SECOND, TOLERANCES, 1.0, 1.0, 1.0)]


def test_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    def boom_report(*args, **kwargs):
        raise Boom("report failed")

    original = crosspoint_mod.pair_gate_score_report
    crosspoint_mod.pair_gate_score_report = boom_report
    try:
        with pytest.raises(Boom, match="^report failed$"):
            pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_score_report = original


def test_validation_matches_score_report():
    with pytest.raises(ValueError, match="^first must be non-empty$"):
        pair_gate_score_summary([], SECOND, TOLERANCES)
    with pytest.raises(TypeError, match="^first must be a list or tuple$"):
        pair_gate_score_summary({1}, SECOND, TOLERANCES)
    with pytest.raises(ValueError, match="^tolerance must be > 0$"):
        pair_gate_score_summary(FIRST, SECOND, TOLERANCES, match_tolerance=0)
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        pair_gate_score_summary(FIRST, SECOND, [])
    with pytest.raises(
        TypeError, match="^min_mean_ratio must be a non-bool int or float$"
    ):
        pair_gate_score_summary(FIRST, SECOND, TOLERANCES, min_mean_ratio=True)
    with pytest.raises(ValueError, match="^first\\[0\\]: d must be >= 0$"):
        pair_gate_score_summary([(0.0, 0.0, -1.0)], SECOND, TOLERANCES)


def test_inputs_not_modified():
    first = copy.deepcopy(FIRST)
    second = copy.deepcopy(SECOND)
    tolerances = copy.deepcopy(TOLERANCES)
    snapshots = copy.deepcopy((first, second, tolerances))

    pair_gate_score_summary(first, second, tolerances, 0.75, 0.9, 0.8)

    assert (first, second, tolerances) == snapshots


def test_quality_fail_when_report_fails():
    result = pair_gate_score_summary(FIRST, SECOND, [0.1])

    assert result["score_report"]["quality"] == "fail"
    assert result["summary"]["score_margin"] != 0.0
    assert result["quality"] == "fail"


def test_quality_fail_when_pair_gate_fails():
    sentinel_report = {
        "metrics": {"coverage_product": 1.0, "score_margin": 0.0},
        "score_report": {
            "matching": {"matched": 3},
            "pair_gate": {"quality": "fail"},
        },
        "quality": "pass",
    }

    original = crosspoint_mod.pair_gate_score_report
    crosspoint_mod.pair_gate_score_report = lambda *args: sentinel_report
    try:
        result = pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_score_report = original

    assert result["summary"]["pair_quality"] == "fail"
    assert result["quality"] == "fail"


def test_quality_fail_when_score_margin_nonzero():
    sentinel_report = {
        "metrics": {"coverage_product": 1.0, "score_margin": 0.5},
        "score_report": {
            "matching": {"matched": 3},
            "pair_gate": {"quality": "pass"},
        },
        "quality": "pass",
    }

    original = crosspoint_mod.pair_gate_score_report
    crosspoint_mod.pair_gate_score_report = lambda *args: sentinel_report
    try:
        result = pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair_gate_score_report = original

    assert result["summary"]["score_margin"] == 0.5
    assert result["quality"] == "fail"


def test_pair_gate_score_summary_exported_in_all():
    assert "pair_gate_score_summary" in crosspoint_mod.__all__
    assert crosspoint_mod.pair_gate_score_summary is pair_gate_score_summary
