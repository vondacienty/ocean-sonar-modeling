"""Tests for attitude.batch result shaping, limit validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import attitude


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    # Zero attitude, heave 2.5: D = 10 - 2.5 = 7.5, a = 7.5 - 10 = -2.5.
    data = attitude.batch([[0, 0, 10, 0, 0, 2.5]], limit=1.0)
    assert data == (
        b'{"results":[[0.0,0.0,7.5,-2.5,false]],'
        b'"summary":{"count":1,"pass_count":0,'
        b'"max_abs_adjustment":2.5,"quality":"fail"}}'
    )


def test_batch_key_order():
    document = decode(attitude.batch([[1, 2, 3, 0, 0, 0]]))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "count",
        "pass_count",
        "max_abs_adjustment",
        "quality",
    ]


def test_batch_results_take_X_Y_D_from_correct():
    s = math.sin(math.radians(45))
    c = math.cos(math.radians(45))
    document = decode(attitude.batch([[0, 0, 1, 45, 45, 0]], limit=10.0))
    ((X, Y, D, a, w),) = document["results"]
    assert (X, Y, D) == (
        round(c * s, 6),
        round(-s * 1, 6),
        round(c * c, 6),
    )
    assert a == D - 1
    assert w is True


def test_batch_all_pass_quality_and_defaults():
    # Identity observation: adjustment 0.0 fits the default limit 1.0.
    document = decode(attitude.batch([[1, 2, 3, 0, 0, 0]]))
    assert document["results"] == [[1.0, 2.0, 3.0, 0.0, True]]
    assert document["summary"] == {
        "count": 1,
        "pass_count": 1,
        "max_abs_adjustment": 0.0,
        "quality": "pass",
    }


def test_batch_mixed_pass_and_fail():
    document = decode(
        attitude.batch(
            [[0, 0, 10, 0, 0, 0.5], [0, 0, 10, 0, 0, 2.5]], limit=1.0
        )
    )
    assert document["results"] == [
        [0.0, 0.0, 9.5, -0.5, True],
        [0.0, 0.0, 7.5, -2.5, False],
    ]
    assert document["summary"] == {
        "count": 2,
        "pass_count": 1,
        "max_abs_adjustment": 2.5,
        "quality": "fail",
    }


def test_batch_adjustment_negative_zero_normalized():
    # correct rounds 5.0000004 to 5.0, so a = round(5.0 - 5.0000004, 6)
    # is -0.0 before normalization.
    data = attitude.batch([[0, 0, 5.0000004, 0, 0, 0]])
    assert b"-0.0" not in data
    document = decode(data)
    assert document["results"] == [[0.0, 0.0, 5.0, 0.0, True]]
    assert document["summary"]["max_abs_adjustment"] == 0.0


def test_batch_max_abs_adjustment_uses_absolute_values():
    document = decode(
        attitude.batch(
            [[0, 0, 10, 0, 0, 0], [0, 0, 10, 0, 0, -4.0]], limit=10.0
        )
    )
    # Negative heave adds to depth: D = 14, a = 4.0.
    assert document["results"] == [
        [0.0, 0.0, 10.0, 0.0, True],
        [0.0, 0.0, 14.0, 4.0, True],
    ]
    assert document["summary"]["max_abs_adjustment"] == 4.0


def test_batch_calls_correct_exactly_once(monkeypatch):
    calls = []
    real_correct = attitude.correct

    def spy(observations):
        calls.append(observations)
        return real_correct(observations)

    monkeypatch.setattr(attitude, "correct", spy)
    observations = [[1, 2, 3, 0, 0, 0]]
    attitude.batch(observations, limit=2.0)
    assert calls == [observations]


def test_batch_correct_exception_propagates_before_limit_validation():
    # Both inputs invalid: the correct error must win over the limit error.
    with pytest.raises(TypeError, match="observations must be a list or tuple"):
        attitude.batch("bad", limit=-1.0)
    with pytest.raises(ValueError, match=r"observation\[0\]: d must be >= 0"):
        attitude.batch([[0, 0, -1.0, 0, 0, 0]], limit=math.nan)


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


def test_batch_limit_zero_allowed():
    document = decode(attitude.batch([[1, 2, 3, 0, 0, 0]], limit=0))
    assert document["results"] == [[1.0, 2.0, 3.0, 0.0, True]]
    assert document["summary"]["quality"] == "pass"


def test_batch_limit_huge_non_negative_int_accepted():
    document = decode(
        attitude.batch(
            [[0, 0, 10, 0, 0, 0], [0, 0, 10, 0, 0, -4.0]], limit=10**10000
        )
    )
    assert document["results"][1][4] is True
    assert document["summary"]["quality"] == "pass"


def test_batch_limit_huge_negative_int_rejected():
    with pytest.raises(ValueError, match="limit must be >= 0"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=-(10**10000))


def test_batch_inputs_not_modified():
    observations = [[0, 0, 10, 0, 0, 2.5], [1, 2, 3, 4, 5, 6]]
    snapshot = [list(o) for o in observations]
    attitude.batch(observations, limit=2.0)
    assert observations == snapshot
