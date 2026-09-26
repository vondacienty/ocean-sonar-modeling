"""Tests for strip.batch result shaping, adjustment validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import strip

STRIPS = [
    [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
    [(0.0, 0.0, 12.0), (10.0, 0.0, 22.0)],
]


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    data = strip.batch(STRIPS)
    assert data == (
        b'{"results":[[0.0,0.0,10.0],[10.0,0.0,20.0],'
        b'[0.0,0.0,10.0],[10.0,0.0,20.0]],'
        b'"summary":{"strip_count":2,"point_count":4,"pass_count":1,'
        b'"max_abs_adjustment":2.0,"quality":"fail"}}'
    )


def test_batch_key_order():
    document = decode(strip.batch(STRIPS))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "strip_count",
        "point_count",
        "pass_count",
        "max_abs_adjustment",
        "quality",
    ]


def test_batch_results_are_merged_triples_in_order():
    strips = [
        [(0.0, 0.0, 10.0)],
        [(0.0, 0.0, 11.0), (1.0, 0.0, 12.0)],
    ]
    document = decode(strip.batch(strips, max_adjustment=2.0))
    assert document["results"] == [
        [0.0, 0.0, 10.0],
        [0.0, 0.0, 9.5],
        [1.0, 0.0, 10.5],
    ]
    assert document["summary"] == {
        "strip_count": 2,
        "point_count": 3,
        "pass_count": 2,
        "max_abs_adjustment": 1.5,
        "quality": "pass",
    }


def test_batch_counts_and_stat_types():
    data = strip.batch(STRIPS)
    document = decode(data)
    summary = document["summary"]
    assert summary["strip_count"] == 2
    assert summary["point_count"] == 4
    assert summary["pass_count"] == 1
    assert summary["max_abs_adjustment"] == 2.0
    # Count fields are JSON ints, the maximum a JSON float.
    assert type(json.loads(data)["summary"]["strip_count"]) is int
    assert type(json.loads(data)["summary"]["point_count"]) is int
    assert type(json.loads(data)["summary"]["pass_count"]) is int
    assert type(json.loads(data)["summary"]["max_abs_adjustment"]) is float
    assert all(
        type(row[0]) is float and type(row[1]) is float and type(row[2]) is float
        for row in document["results"]
    )


def test_batch_quality_pass_when_all_adjustments_within_limit():
    document = decode(strip.batch(STRIPS, max_adjustment=2.0))
    assert document["summary"]["pass_count"] == 2
    assert document["summary"]["quality"] == "pass"


def test_batch_quality_fail_just_below_limit():
    # abs(a) <= limit passes; 1.999999 < 2.0 fails.
    document = decode(strip.batch(STRIPS, max_adjustment=1.999999))
    assert document["summary"]["quality"] == "fail"


def test_batch_zero_adjustment_bound_allowed():
    strips = [
        [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
        [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
    ]
    document = decode(strip.batch(strips, max_adjustment=0))
    assert document["summary"]["max_abs_adjustment"] == 0.0
    assert document["summary"]["quality"] == "pass"
    assert b"-0.0" not in strip.batch(strips, max_adjustment=0)


def test_batch_negative_adjustment():
    # Strip 2 reads exactly 1 m too shallow: its mean adjustment is -1.0.
    strips = [
        [(0.0, 0.0, 10.0), (1.0, 0.0, 20.0)],
        [(0.0, 0.0, 9.0), (1.0, 0.0, 19.0)],
    ]
    document = decode(strip.batch(strips, max_adjustment=0.5))
    assert document["summary"]["max_abs_adjustment"] == 1.0
    assert document["summary"]["pass_count"] == 1
    assert document["summary"]["quality"] == "fail"


def test_batch_negative_zero_adjustment_normalized():
    # The second strip's mean adjustment rounds to a negative zero.
    strips = [
        [(0.0, 0.0, 10.0)],
        [(0.0, 0.0, 9.9999999), (1.0, 0.0, 9.9999997)],
    ]
    data = strip.batch(strips)
    document = decode(data)
    assert document["summary"]["max_abs_adjustment"] == 0.0
    assert document["summary"]["quality"] == "pass"
    assert b"-0.0" not in data


def test_batch_tolerance_passed_through():
    strips = [
        [(0.0, 0.0, 10.0)],
        [(1.5, 0.0, 11.0), (0.0, 1.5, 12.0)],
    ]
    with pytest.raises(ValueError, match=r"at least 2 matches required"):
        strip.batch(strips, tolerance=1.0)
    document = decode(strip.batch(strips, tolerance=2.0))
    assert document["summary"]["point_count"] == 3


def test_batch_calls_merge_exactly_once(monkeypatch):
    calls = []
    real_merge = strip.merge

    def spy(*args):
        calls.append(args)
        return real_merge(*args)

    monkeypatch.setattr(strip, "merge", spy)
    strip.batch(STRIPS, tolerance=2.0, max_adjustment=3.0)
    assert calls == [(STRIPS, 2.0)]


def test_batch_merge_exception_propagates_before_adjustment_validation():
    with pytest.raises(TypeError, match="strips must be a list or tuple"):
        strip.batch("bad", max_adjustment=-1.0)
    with pytest.raises(ValueError, match="at least 2 elements"):
        strip.batch([[(0.0, 0.0, 1.0)]], max_adjustment=-1.0)


@pytest.mark.parametrize("limit", [True, False, "1.0", None, [1.0]])
def test_batch_max_adjustment_type_error(limit):
    with pytest.raises(
        TypeError, match="max_adjustment must be a non-bool int or float"
    ):
        strip.batch(STRIPS, max_adjustment=limit)


@pytest.mark.parametrize("limit", [math.nan, math.inf, -math.inf])
def test_batch_max_adjustment_non_finite_float_error(limit):
    with pytest.raises(ValueError, match="max_adjustment must be finite"):
        strip.batch(STRIPS, max_adjustment=limit)


@pytest.mark.parametrize("limit", [-1, -0.000001, -(10 ** 100)])
def test_batch_max_adjustment_negative_error(limit):
    with pytest.raises(ValueError, match="max_adjustment must be >= 0"):
        strip.batch(STRIPS, max_adjustment=limit)


def test_batch_huge_int_max_adjustment_allowed():
    # Ints of any magnitude are still ints; finiteness only applies to
    # floats, so a huge non-negative int is a valid limit.
    document = decode(strip.batch(STRIPS, max_adjustment=10 ** 100))
    assert document["summary"]["quality"] == "pass"


def test_batch_inputs_not_modified():
    strips = [
        [(0.0, 0.0, 10.0), (10.0, 0.0, 20.0)],
        [(0.0, 0.0, 12.0), (10.0, 0.0, 22.0)],
    ]
    snapshot = [[list(point) for point in s] for s in strips]
    strip.batch(strips, tolerance=2.0, max_adjustment=3.0)
    assert [[list(point) for point in s] for s in strips] == snapshot


def test_batch_result_is_bytes():
    data = strip.batch(STRIPS)
    assert isinstance(data, bytes)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")
