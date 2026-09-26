"""Tests for attitude.batch result shaping, limit validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import attitude


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    # A single zero-attitude observation: adjustment 0.0, within limit 1.0.
    data = attitude.batch([[1, 2, 3, 0, 0, 0]])
    assert data == (
        b'{"results":[[1.0,2.0,3.0,0.0,true]],'
        b'"summary":{"count":1,"pass_count":1,'
        b'"max_abs_adjustment":0.0,"quality":"pass"}}'
    )


def test_batch_heave_adjustment_and_fail_quality():
    # Heave 2.5 reduces depth 10 to 7.5 -> adjustment -2.5.
    document = decode(attitude.batch([[0, 0, 10, 0, 0, 2.5]]))
    assert document["results"] == [[0.0, 0.0, 7.5, -2.5, False]]
    assert document["summary"] == {
        "count": 1,
        "pass_count": 0,
        "max_abs_adjustment": 2.5,
        "quality": "fail",
    }


def test_batch_key_order():
    document = decode(attitude.batch([[1, 2, 3, 0, 0, 0]]))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "count",
        "pass_count",
        "max_abs_adjustment",
        "quality",
    ]


def test_batch_calls_correct_exactly_once(monkeypatch):
    calls = []
    real_correct = attitude.correct

    def spy(*args):
        calls.append(args)
        return real_correct(*args)

    monkeypatch.setattr(attitude, "correct", spy)
    attitude.batch([[1, 2, 3, 0, 0, 0]], limit=2.0)
    assert calls == [([[1, 2, 3, 0, 0, 0]],)]


@pytest.mark.parametrize("limit", [True, False, "1", None, [1.0]])
def test_batch_limit_type_error(limit):
    with pytest.raises(TypeError, match="limit must be a non-bool int or float"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=limit)


@pytest.mark.parametrize("limit", [math.nan, math.inf, -math.inf])
def test_batch_limit_finite_error(limit):
    with pytest.raises(ValueError, match="limit must be finite"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=limit)


def test_batch_limit_negative_error():
    with pytest.raises(ValueError, match="limit must be >= 0"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=-0.5)


def test_batch_limit_huge_non_negative_int_allowed():
    # Regression: finiteness is only checked for floats, so a non-negative
    # int of any magnitude is a valid limit and every flag is within it.
    document = decode(
        attitude.batch([[0, 0, 10, 0, 0, 2.5]], limit=10 ** 100)
    )
    assert document["results"] == [[0.0, 0.0, 7.5, -2.5, True]]
    assert document["summary"]["quality"] == "pass"
    document = decode(
        attitude.batch([[0, 0, 10, 0, 0, 2.5]], limit=10 ** 1000)
    )
    assert document["results"][0][4] is True
    assert document["summary"]["quality"] == "pass"


def test_batch_inputs_not_modified():
    observations = [[0, 0, 10, 0, 0, 2.5]]
    snapshot = [list(item) for item in observations]
    attitude.batch(observations, limit=2.0)
    assert observations == snapshot
