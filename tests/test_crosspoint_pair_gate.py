"""Tests for crosspoint.pair_gate."""

import copy

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import gate, pair, pair_gate

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


def test_happy_path_matches_pair_then_gate():
    result = pair_gate(FIRST, SECOND, TOLERANCES)

    expected_pairs = pair(FIRST, SECOND, 1.0)
    expected_gate = gate(expected_pairs, TOLERANCES, 1.0, 1.0)

    assert result == {
        "pairs": expected_pairs,
        "report": expected_gate,
        "quality": expected_gate["quality"],
    }
    assert list(result.keys()) == ["pairs", "report", "quality"]
    assert result["quality"] == "pass"


def test_nested_key_orders():
    result = pair_gate(FIRST, SECOND, TOLERANCES)
    gated = result["report"]

    assert list(gated.keys()) == ["report", "checks", "quality"]
    assert list(gated["checks"].keys()) == [
        "mean_ratio",
        "max_rmse",
        "within_ok",
        "rmse_ok",
    ]
    assert list(gated["report"].keys()) == ["dashboard", "summary", "quality"]


def test_pairs_and_report_are_original_objects():
    sentinel_pairs = object()
    sentinel_gate = {"quality": "pass"}
    calls = {"pair": [], "gate": []}

    def fake_pair(first, second, tolerance=1.0):
        calls["pair"].append((first, second, tolerance))
        return sentinel_pairs

    def fake_gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
        calls["gate"].append(
            (crossings, tolerances, min_mean_ratio, max_rmse_limit)
        )
        return sentinel_gate

    crosspoint_mod.pair = fake_pair
    crosspoint_mod.gate = fake_gate
    try:
        result = pair_gate(FIRST, SECOND, TOLERANCES, 0.25, 0.5, 0.9)
    finally:
        crosspoint_mod.pair = pair
        crosspoint_mod.gate = gate

    assert calls["pair"] == [(FIRST, SECOND, 0.25)]
    assert calls["gate"] == [(sentinel_pairs, TOLERANCES, 0.5, 0.9)]
    assert result["pairs"] is sentinel_pairs
    assert result["report"] is sentinel_gate
    assert result["quality"] == "pass"


def test_pair_and_gate_each_called_exactly_once():
    calls = []
    original_pair = crosspoint_mod.pair
    original_gate = crosspoint_mod.gate

    def spy_pair(first, second, tolerance=1.0):
        calls.append("pair")
        return original_pair(first, second, tolerance)

    def spy_gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
        calls.append("gate")
        return original_gate(crossings, tolerances, min_mean_ratio, max_rmse_limit)

    crosspoint_mod.pair = spy_pair
    crosspoint_mod.gate = spy_gate
    try:
        pair_gate(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair = original_pair
        crosspoint_mod.gate = original_gate

    assert calls == ["pair", "gate"]


def test_default_arguments():
    calls = {}
    original_pair = crosspoint_mod.pair
    original_gate = crosspoint_mod.gate

    def spy_pair(first, second, tolerance=1.0):
        calls["match_tolerance"] = tolerance
        return original_pair(first, second, tolerance)

    def spy_gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
        calls["min_mean_ratio"] = min_mean_ratio
        calls["max_rmse_limit"] = max_rmse_limit
        return original_gate(crossings, tolerances, min_mean_ratio, max_rmse_limit)

    crosspoint_mod.pair = spy_pair
    crosspoint_mod.gate = spy_gate
    try:
        pair_gate(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair = original_pair
        crosspoint_mod.gate = original_gate

    assert calls == {
        "match_tolerance": 1.0,
        "min_mean_ratio": 1.0,
        "max_rmse_limit": 1.0,
    }


def test_gate_not_called_when_pair_raises():
    def boom_gate(*args, **kwargs):
        raise AssertionError("gate should not be called")

    crosspoint_mod.gate = boom_gate
    try:
        with pytest.raises(ValueError, match="^first must be non-empty$"):
            pair_gate([], SECOND, TOLERANCES)
    finally:
        crosspoint_mod.gate = gate


def test_pair_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    def boom_pair(first, second, tolerance=1.0):
        raise Boom("pair failed")

    crosspoint_mod.pair = boom_pair
    try:
        with pytest.raises(Boom, match="^pair failed$"):
            pair_gate(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.pair = pair


def test_gate_exception_propagates_unchanged():
    class Boom(Exception):
        pass

    paired = pair(FIRST, SECOND, 1.0)

    def boom_gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0):
        raise Boom("gate failed")

    crosspoint_mod.gate = boom_gate
    try:
        with pytest.raises(Boom, match="^gate failed$"):
            pair_gate(FIRST, SECOND, TOLERANCES)
    finally:
        crosspoint_mod.gate = gate

    # Sanity: the exception only fires once pair has produced crossings.
    assert paired


def test_pair_validated_before_gate():
    # match_tolerance (validated last inside pair) beats bad tolerances,
    # because the whole pair stage runs before gate.
    with pytest.raises(ValueError, match="^tolerance must be > 0$"):
        pair_gate(FIRST, SECOND, "bad", match_tolerance=0)
    with pytest.raises(TypeError, match="^first must be a list or tuple$"):
        pair_gate({1}, SECOND, [])


def test_gate_validation_reached_after_pair_succeeds():
    with pytest.raises(ValueError, match="^tolerances must be non-empty$"):
        pair_gate(FIRST, SECOND, [])
    with pytest.raises(TypeError, match="^min_mean_ratio must be a non-bool int or float$"):
        pair_gate(FIRST, SECOND, TOLERANCES, min_mean_ratio=True)


def test_no_pairs_matched_raises():
    second = [(100.0, 100.0, 1.0)]
    with pytest.raises(ValueError, match="^no points matched within tolerance$"):
        pair_gate(FIRST, second, TOLERANCES, match_tolerance=0.1)


def test_inputs_not_modified():
    first = copy.deepcopy(FIRST)
    second = copy.deepcopy(SECOND)
    tolerances = copy.deepcopy(TOLERANCES)
    snapshots = copy.deepcopy((first, second, tolerances))

    pair_gate(first, second, tolerances, 0.75, 0.9, 0.8)

    assert (first, second, tolerances) == snapshots


def test_quality_fail_propagated():
    result = pair_gate(FIRST, SECOND, [0.1])
    assert result["quality"] == "fail"
    assert result["report"]["quality"] == "fail"


def test_pairs_rounded_floats_with_negative_zero_normalized():
    import math

    # Coordinates at the origin round to 0.0 and must never be -0.0.
    result = pair_gate(FIRST, SECOND, TOLERANCES)
    assert result["pairs"] == pair(FIRST, SECOND, 1.0)
    for item in result["pairs"]:
        assert all(isinstance(value, float) for value in item)
        assert all(math.copysign(1.0, value) == 1.0 for value in item if value == 0.0)


def test_pair_gate_exported_in_all():
    assert "pair_gate" in crosspoint_mod.__all__
    assert crosspoint_mod.pair_gate is pair_gate
