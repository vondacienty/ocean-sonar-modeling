"""Tests for tide.batch result shaping, limit validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import tide


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    data = tide.batch(
        [0.5, 1.0], [10.0, 12.0], [0, 1], [1.0, 3.0], datum=0.5, limit=2.0
    )
    assert data == (
        b'{"results":[[8.5,-1.5,true],[9.5,-2.5,false]],'
        b'"summary":{"count":2,"pass_count":1,'
        b'"max_abs_adjustment":2.5,"quality":"fail"}}'
    )


def test_batch_key_order():
    document = decode(tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0]))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "count",
        "pass_count",
        "max_abs_adjustment",
        "quality",
    ]


def test_batch_all_pass_quality_and_defaults():
    document = decode(tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0]))
    # reduced = 10 - 2 + 0 = 8.0, a = -2.0 exceeds the default limit 1.0.
    assert document["summary"]["quality"] == "fail"
    document = decode(
        tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], limit=2.0)
    )
    assert document["results"] == [[8.0, -2.0, True]]
    assert document["summary"] == {
        "count": 1,
        "pass_count": 1,
        "max_abs_adjustment": 2.0,
        "quality": "pass",
    }


def test_batch_datum_default_is_zero():
    document = decode(tide.batch([0.0], [5.0], [0, 1], [1.0, 1.0]))
    assert document["results"] == [[4.0, -1.0, True]]


def test_batch_adjustment_negative_zero_normalized():
    # reduce rounds 5.0000004 to 5.0, so a = round(5.0 - 5.0000004, 6)
    # is -0.0 before normalization.
    data = tide.batch([0.0], [5.0000004], [0, 1], [0.0, 0.0])
    assert b"-0.0" not in data
    document = decode(data)
    assert document["results"] == [[5.0, 0.0, True]]
    assert document["summary"]["max_abs_adjustment"] == 0.0


def test_batch_max_abs_adjustment_uses_absolute_values():
    document = decode(
        tide.batch([0.0, 1.0], [10.0, 10.0], [0, 1], [0.0, 4.0], limit=10.0)
    )
    assert document["results"] == [[10.0, 0.0, True], [6.0, -4.0, True]]
    assert document["summary"]["max_abs_adjustment"] == 4.0


def test_batch_calls_reduce_exactly_once(monkeypatch):
    calls = []
    real_reduce = tide.reduce

    def spy(*args):
        calls.append(args)
        return real_reduce(*args)

    monkeypatch.setattr(tide, "reduce", spy)
    tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], datum=0.5, limit=2.0)
    assert calls == [([0.5], [10.0], [0, 1], [1.0, 3.0], 0.5)]


def test_batch_reduce_exception_propagates_before_limit_validation():
    # Both inputs invalid: the reduce error must win over the limit error.
    with pytest.raises(TypeError, match="times must be a list or tuple"):
        tide.batch("bad", [10.0], [0, 1], [1.0, 3.0], limit=-1.0)
    with pytest.raises(ValueError, match=r"observation\[0\]: depth must be >= 0"):
        tide.batch([0.5], [-1.0], [0, 1], [1.0, 3.0], limit=math.nan)


@pytest.mark.parametrize("limit", [True, False, "1", None, [1.0]])
def test_batch_limit_type_error(limit):
    with pytest.raises(TypeError, match="limit must be a non-bool int or float"):
        tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], limit=limit)


@pytest.mark.parametrize("limit", [math.nan, math.inf, -math.inf])
def test_batch_limit_finite_error(limit):
    with pytest.raises(ValueError, match="limit must be finite"):
        tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], limit=limit)


def test_batch_limit_huge_non_negative_int_accepted():
    # Only floats are finiteness-checked; a huge non-negative int that
    # cannot even be converted to float is a legal (permissive) limit.
    document = decode(
        tide.batch([0.0, 1.0], [10.0, 10.0], [0, 1], [0.0, 4.0], limit=10**10000)
    )
    assert document["results"] == [[10.0, 0.0, True], [6.0, -4.0, True]]
    assert document["summary"]["quality"] == "pass"


def test_batch_limit_huge_negative_int_rejected():
    with pytest.raises(ValueError, match="limit must be >= 0"):
        tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], limit=-(10**10000))


def test_batch_limit_negative_error():
    with pytest.raises(ValueError, match="limit must be >= 0"):
        tide.batch([0.5], [10.0], [0, 1], [1.0, 3.0], limit=-0.5)


def test_batch_limit_zero_allowed():
    document = decode(
        tide.batch([0.0], [5.0], [0, 1], [0.0, 0.0], limit=0)
    )
    assert document["results"] == [[5.0, 0.0, True]]
    assert document["summary"]["quality"] == "pass"


def test_batch_inputs_not_modified():
    times = [0.5, 1.0]
    depths = [10.0, 12.0]
    tide_times = [0, 1]
    levels = [1.0, 3.0]
    snapshot = [list(v) for v in (times, depths, tide_times, levels)]
    tide.batch(times, depths, tide_times, levels, datum=0.5, limit=2.0)
    assert [times, depths, tide_times, levels] == snapshot
