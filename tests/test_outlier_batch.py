"""Tests for outlier.batch result shaping, ratio validation and JSON bytes."""

import json
import math

import pytest

from ocean_sonar import outlier


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    data = outlier.batch([1, 2, 3, 100])
    assert data == (
        b'{"results":[[false,1.011735,1.0],[false,0.337245,2.0],'
        b'[false,0.337245,3.0],[true,65.762751,100.0]],'
        b'"summary":{"count":4,"outlier_count":1,"outlier_ratio":0.25,'
        b'"max_score":65.762751,"quality":"fail"}}'
    )


def test_batch_key_order():
    document = decode(outlier.batch([1, 2, 3, 100]))
    assert list(document) == ["results", "summary"]
    assert list(document["summary"]) == [
        "count",
        "outlier_count",
        "outlier_ratio",
        "max_score",
        "quality",
    ]


def test_batch_results_in_detect_order():
    document = decode(outlier.batch([100, 1, 3, 2]))
    assert document["results"] == [
        [True, 65.762751, 100.0],
        [False, 1.011735, 1.0],
        [False, 0.337245, 3.0],
        [False, 0.337245, 2.0],
    ]


def test_batch_all_clean_pass_with_defaults():
    # [2, 3, 4]: no flags even at the default threshold, ratio 0.0.
    data = outlier.batch([2.0, 3.0, 4.0])
    document = decode(data)
    assert document["results"] == [
        [False, 0.67449, 2.0],
        [False, 0.0, 3.0],
        [False, 0.67449, 4.0],
    ]
    assert document["summary"] == {
        "count": 3,
        "outlier_count": 0,
        "outlier_ratio": 0.0,
        "max_score": 0.67449,
        "quality": "pass",
    }
    assert b"-0.0" not in data


def test_batch_quality_boundary_equal_ratio_passes():
    # 1 of 4 outliers -> exactly 0.25; the gate is <= so it passes.
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0.25))
    assert document["summary"]["outlier_ratio"] == 0.25
    assert document["summary"]["quality"] == "pass"


def test_batch_quality_just_above_ratio_fails():
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0.24))
    assert document["summary"]["quality"] == "fail"


def test_batch_ratio_zero_and_one_allowed():
    document = decode(outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=0))
    assert document["summary"]["quality"] == "pass"
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=1))
    assert document["summary"]["quality"] == "pass"


def test_batch_threshold_passed_through():
    # threshold=0.5 flags the depth 1 as well -> 2 of 4 outliers.
    document = decode(outlier.batch([1, 2, 3, 100], threshold=0.5))
    assert document["results"][0][0] is True
    assert document["summary"]["outlier_count"] == 2
    assert document["summary"]["outlier_ratio"] == 0.5
    assert document["summary"]["quality"] == "fail"


def test_batch_counts_are_ints_and_stats_are_floats():
    document = decode(outlier.batch([2.0, 3.0, 4.0]))
    summary = document["summary"]
    assert type(summary["count"]) is int
    assert type(summary["outlier_count"]) is int
    assert type(summary["outlier_ratio"]) is float
    assert type(summary["max_score"]) is float
    for item in document["results"]:
        assert type(item[0]) is bool
        assert type(item[1]) is float
        assert type(item[2]) is float


def test_batch_ratio_rounded_to_six_decimals():
    # 1 outlier of 3 -> 1/3 rounded to 0.333333; full-precision 1/3 is
    # still within the default 0.1 gate, so quality fails.
    data = outlier.batch([5, 5, 9])
    assert b'"outlier_ratio":0.333333' in data


def test_batch_mad_zero_max_score():
    # MAD 0: the single spike scores round(threshold + 1, 6) = 4.5.
    document = decode(outlier.batch([5, 5, 5, 5, 9]))
    assert document["summary"]["outlier_count"] == 1
    assert document["summary"]["max_score"] == 4.5


def test_batch_no_trailing_newline_or_bom():
    data = outlier.batch([2.0, 3.0, 4.0])
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")


def test_batch_calls_detect_exactly_once(monkeypatch):
    calls = []
    real_detect = outlier.detect

    def spy(*args):
        calls.append(args)
        return real_detect(*args)

    monkeypatch.setattr(outlier, "detect", spy)
    outlier.batch([1, 2, 3, 100], threshold=2.0, max_outlier_ratio=0.5)
    assert calls == [([1, 2, 3, 100], 2.0)]


def test_batch_detect_exception_propagates_before_ratio_validation():
    # Both invalid: the detect error wins over the ratio error.
    with pytest.raises(TypeError, match="depths must be a list or tuple"):
        outlier.batch("bad", max_outlier_ratio=2.0)
    with pytest.raises(ValueError, match="at least 3"):
        outlier.batch([1, 2], max_outlier_ratio=-1.0)


def test_batch_threshold_error_propagates_from_detect():
    with pytest.raises(TypeError, match="threshold must be a non-bool int or float"):
        outlier.batch([1, 2, 3], threshold="3.5")
    with pytest.raises(ValueError, match="threshold must be > 0"):
        outlier.batch([1, 2, 3], threshold=0)


@pytest.mark.parametrize("ratio", [True, False, "0.1", None, [0.1]])
def test_batch_ratio_type_error(ratio):
    with pytest.raises(
        TypeError, match="max_outlier_ratio must be a non-bool int or float"
    ):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


@pytest.mark.parametrize("ratio", [math.nan, math.inf, -math.inf])
def test_batch_ratio_finite_error(ratio):
    with pytest.raises(ValueError, match="max_outlier_ratio must be finite"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


@pytest.mark.parametrize("ratio", [-0.1, 1.1, 2, -1])
def test_batch_ratio_range_error(ratio):
    with pytest.raises(ValueError, match="max_outlier_ratio must be in \\[0, 1\\]"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


def test_batch_inputs_not_modified():
    depths = [100, 1, 3, 2]
    snapshot = list(depths)
    outlier.batch(depths)
    assert depths == snapshot
