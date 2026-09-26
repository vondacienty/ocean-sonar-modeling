"""Tests for attitude.batch shaping, limit validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import attitude


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    data = attitude.batch([[1, 2, 3, 0, 0, 0]])
    assert data == (
        b'{"results":[[1.0,2.0,3.0,0.0,true]],'
        b'"summary":{"count":1,"pass_count":1,'
        b'"max_abs_adjustment":0.0,"quality":"pass"}}'
    )


def test_batch_huge_non_negative_int_limit_passes():
    # Regression: finiteness is checked only for floats, so a huge
    # non-negative int limit of any magnitude must be accepted and every
    # finite adjustment must be within it.
    observations = [[0, 0, 10, 0, 0, 2.5]]
    data = attitude.batch(observations, limit=10**100)
    document = decode(data)
    assert document["results"][0] == [0.0, 0.0, 7.5, -2.5, True]
    assert document["summary"]["max_abs_adjustment"] == 2.5
    assert document["summary"]["quality"] == "pass"


def test_batch_huge_negative_int_limit_rejected():
    with pytest.raises(ValueError, match="limit must be >= 0"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=-(10**100))


def test_batch_infinite_float_limit_rejected():
    with pytest.raises(ValueError, match="limit must be finite"):
        attitude.batch([[1, 2, 3, 0, 0, 0]], limit=math.inf)
