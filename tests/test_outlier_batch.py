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


def test_batch_counts_and_stat_types():
    data = outlier.batch([1, 2, 3, 100])
    document = decode(data)
    summary = document["summary"]
    assert summary["count"] == 4
    assert summary["outlier_count"] == 1
    assert summary["outlier_ratio"] == 0.25
    assert summary["max_score"] == 65.762751
    # Count fields are JSON ints, statistics JSON floats.
    assert type(json.loads(data)["summary"]["count"]) is int
    assert type(json.loads(data)["summary"]["outlier_count"]) is int
    assert type(json.loads(data)["summary"]["outlier_ratio"]) is float
    assert type(json.loads(data)["summary"]["max_score"]) is float
    assert all(
        type(row[0]) is bool and type(row[1]) is float and type(row[2]) is float
        for row in document["results"]
    )


def test_batch_no_outliers_ratio_zero():
    document = decode(outlier.batch([2.0, 3.0, 4.0]))
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
    assert b"-0.0" not in outlier.batch([2.0, 3.0, 4.0])


def test_batch_quality_pass_when_ratio_within_limit():
    # 1 of 4 flagged -> ratio 0.25.
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0.25))
    assert document["summary"]["quality"] == "pass"
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0.3))
    assert document["summary"]["quality"] == "pass"


def test_batch_quality_fail_just_below_ratio():
    # Strict comparison: only k/n <= limit passes; 0.24 < 0.25 fails.
    document = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0.24))
    assert document["summary"]["quality"] == "fail"


def test_batch_zero_and_one_ratio_bounds_allowed():
    flagged = decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=0))
    assert flagged["summary"]["quality"] == "fail"
    assert decode(outlier.batch([1, 2, 3, 100], max_outlier_ratio=1))["summary"][
        "quality"
    ] == "pass"
    assert decode(outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=0))["summary"][
        "quality"
    ] == "pass"


def test_batch_ratio_is_rounded_six_decimals():
    # Two MAD-zero groups in seven depths: [2,2,2,2,2,9,9] flags two of
    # seven -> round(2/7, 6) = 0.285714.
    document = decode(outlier.batch([2, 2, 2, 2, 2, 9, 9]))
    assert document["summary"]["outlier_count"] == 2
    assert document["summary"]["outlier_ratio"] == round(2 / 7, 6)
    assert document["summary"]["outlier_ratio"] == 0.285714


def test_batch_ratio_one_third():
    # [5,5,9]: MAD zero, one of three flagged -> ratio round(1/3, 6).
    document = decode(outlier.batch([5, 5, 9]))
    assert document["summary"]["outlier_count"] == 1
    assert document["summary"]["outlier_ratio"] == round(1 / 3, 6)
    assert document["summary"]["quality"] == "fail"


def test_batch_threshold_passed_through():
    # threshold 0.5 additionally flags the 1 in [1,2,3,100]: k=2, ratio 0.5.
    document = decode(
        outlier.batch([1, 2, 3, 100], threshold=0.5, max_outlier_ratio=0.5)
    )
    assert [row[0] for row in document["results"]] == [True, False, False, True]
    assert document["summary"]["outlier_count"] == 2
    assert document["summary"]["outlier_ratio"] == 0.5
    assert document["summary"]["quality"] == "pass"


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
    with pytest.raises(TypeError, match="depths must be a list or tuple"):
        outlier.batch("bad", max_outlier_ratio=2.0)
    with pytest.raises(ValueError, match="at least 3"):
        outlier.batch([1, 2], max_outlier_ratio=-1.0)


@pytest.mark.parametrize("ratio", [True, False, "0.1", None, [0.1]])
def test_batch_ratio_type_error(ratio):
    with pytest.raises(
        TypeError, match="max_outlier_ratio must be a non-bool int or float"
    ):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


@pytest.mark.parametrize("ratio", [math.nan, math.inf, -math.inf])
def test_batch_ratio_non_finite_float_error(ratio):
    with pytest.raises(ValueError, match="max_outlier_ratio must be finite"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


@pytest.mark.parametrize("ratio", [-1, -0.000001, 1.000001, 2])
def test_batch_ratio_out_of_bounds_error(ratio):
    with pytest.raises(ValueError, match="max_outlier_ratio must be in \\[0, 1\\]"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=ratio)


def test_batch_huge_int_ratio_bounds():
    # Ints of any magnitude are still ints; bounds [0, 1] reject large
    # magnitudes with ValueError, never an OverflowError or finiteness
    # complaint (finiteness only applies to floats).
    with pytest.raises(ValueError, match="max_outlier_ratio must be in \\[0, 1\\]"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=10 ** 100)
    with pytest.raises(ValueError, match="max_outlier_ratio must be in \\[0, 1\\]"):
        outlier.batch([2.0, 3.0, 4.0], max_outlier_ratio=-(10 ** 100))


def test_batch_inputs_not_modified():
    depths = [100, 1, 3, 2]
    snapshot = list(depths)
    outlier.batch(depths, threshold=0.5, max_outlier_ratio=0.2)
    assert depths == snapshot


def test_batch_result_is_bytes():
    data = outlier.batch([2.0, 3.0, 4.0])
    assert isinstance(data, bytes)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")
