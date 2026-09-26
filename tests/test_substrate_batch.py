"""Tests for substrate.batch validation, classification and JSON bytes."""

import json

import pytest

from ocean_sonar import substrate


def decode(data):
    assert isinstance(data, bytes)
    return json.loads(data.decode("utf-8"))


def test_batch_basic_exact_bytes():
    data = substrate.batch(
        [(3.0, 0.5), (6.0, 0.5), (3.0, 2.0), (6.0, 2.0)],
        [0.4, 0.4, 0.6, 0.6],
    )
    assert data == (
        b'{"results":[["mud",1.0],["gravel",1.0],["rock",1.0],["rock",1.0]],'
        b'"summary":{"count":4,"unknown":0,"quality":"pass"}}'
    )


def test_batch_class_bits():
    # (g, a) = 00 mud, 01 sand, 10 gravel, 11 rock.
    document = decode(
        substrate.batch(
            [(5.0, 1.0), (5.0, 1.0), (5.0, 1.0), (5.0, 1.0)],
            [0.4, 0.5, 0.4, 0.5],
        )
    )
    assert [row[0] for row in document["results"]] == [
        "mud",
        "sand",
        "mud",
        "sand",
    ]
    document = decode(
        substrate.batch(
            [(5.0, 1.0), (5.0, 1.0), (6.0, 0.0), (6.0, 0.0)],
            [0.4, 0.5, 0.4, 0.5],
        )
    )
    assert [row[0] for row in document["results"]] == [
        "mud",
        "sand",
        "gravel",
        "rock",
    ]


def test_batch_thresholds_are_strict_or_inclusive_as_specified():
    # p > 5 / q > 1 are strict; intensity >= 0.5 includes the boundary.
    document = decode(substrate.batch([(5.0, 1.0)], [0.5]))
    assert document["results"] == [["sand", 1.0]]
    document = decode(substrate.batch([(5.0, 1.000001)], [0.0]))
    assert document["results"] == [["gravel", 1.0]]


def test_batch_missing_p_or_intensity_is_unknown():
    document = decode(
        substrate.batch(
            [(None, None), (None, 0.3), (1.0, 0.0), (1.0, 0.0)],
            [0.7, 0.7, None, 0.4],
        )
    )
    assert document["results"] == [
        ["unknown", 0.0],
        ["unknown", 0.0],
        ["unknown", 0.0],
        ["mud", 1.0],
    ]
    assert document["summary"] == {"count": 4, "unknown": 3, "quality": "fail"}


def test_batch_quality_pass_only_when_no_unknown():
    document = decode(substrate.batch([(1.0, 0.0)], [0.2]))
    assert document["summary"] == {"count": 1, "unknown": 0, "quality": "pass"}
    document = decode(substrate.batch([(None, None)], [0.2]))
    assert document["summary"] == {"count": 1, "unknown": 1, "quality": "fail"}


def test_batch_accepts_tuples_and_ints():
    document = decode(substrate.batch(((1, 0), (6, 2)), (0, 1)))
    assert document["results"] == [["mud", 1.0], ["rock", 1.0]]


def test_batch_inputs_not_modified():
    analysis = [[3.0, 0.5], [None, None]]
    intensities = [0.4, None]
    substrate.batch(analysis, intensities)
    assert analysis == [[3.0, 0.5], [None, None]]
    assert intensities == [0.4, None]


def test_batch_analysis_container_type():
    with pytest.raises(TypeError, match="analysis must be a list or tuple"):
        substrate.batch("x", [])


def test_batch_analysis_non_empty():
    with pytest.raises(ValueError, match="analysis must be non-empty"):
        substrate.batch([], [])


def test_batch_grid_container_type():
    with pytest.raises(TypeError, match=r"analysis\[0\]: must be a list or tuple"):
        substrate.batch([1], [0.5])


def test_batch_grid_two_elements():
    with pytest.raises(ValueError, match=r"analysis\[0\]: must have 2 elements"):
        substrate.batch([(1.0,)], [0.5])


def test_batch_p_type():
    with pytest.raises(
        TypeError, match=r"analysis\[0\]: p must be a non-bool int or float"
    ):
        substrate.batch([(True, 0.0)], [0.5])


def test_batch_p_finite():
    with pytest.raises(ValueError, match=r"analysis\[0\]: p must be finite"):
        substrate.batch([(float("inf"), 0.0)], [0.5])


def test_batch_p_non_negative():
    with pytest.raises(ValueError, match=r"analysis\[0\]: p must be >= 0"):
        substrate.batch([(-1.0, 0.0)], [0.5])


def test_batch_q_checked_when_p_none():
    with pytest.raises(
        TypeError, match=r"analysis\[0\]: q must be a non-bool int or float"
    ):
        substrate.batch([(None, "x")], [0.5])
    with pytest.raises(ValueError, match=r"analysis\[0\]: q must be >= 0"):
        substrate.batch([(None, -0.1)], [0.5])


def test_batch_q_none_rejected_when_p_present():
    with pytest.raises(
        TypeError, match=r"analysis\[0\]: q must be a non-bool int or float"
    ):
        substrate.batch([(1.0, None)], [0.5])


def test_batch_grid_error_index():
    with pytest.raises(ValueError, match=r"analysis\[1\]: p must be >= 0"):
        substrate.batch([(1.0, 0.0), (-2.0, 0.0)], [0.5, 0.5])


def test_batch_analysis_checked_before_intensities():
    with pytest.raises(ValueError, match="analysis must be non-empty"):
        substrate.batch([], "not-a-list")
    with pytest.raises(TypeError, match=r"analysis\[0\]: must be a list or tuple"):
        substrate.batch([1], "not-a-list")


def test_batch_intensities_container_type():
    with pytest.raises(TypeError, match="intensities must be a list or tuple"):
        substrate.batch([(1.0, 0.0)], 0.5)


def test_batch_intensities_equal_length():
    with pytest.raises(
        ValueError, match="analysis and intensities must have equal length"
    ):
        substrate.batch([(1.0, 0.0)], [0.5, 0.6])


def test_batch_intensity_type():
    with pytest.raises(
        TypeError, match=r"intensities\[0\]: must be a non-bool int or float"
    ):
        substrate.batch([(1.0, 0.0)], [False])


def test_batch_intensity_finite():
    with pytest.raises(ValueError, match=r"intensities\[0\]: must be finite"):
        substrate.batch([(1.0, 0.0)], [float("nan")])


def test_batch_intensity_range():
    with pytest.raises(ValueError, match=r"intensities\[0\]: must be in \[0, 1\]"):
        substrate.batch([(1.0, 0.0)], [1.5])
    with pytest.raises(ValueError, match=r"intensities\[1\]: must be in \[0, 1\]"):
        substrate.batch([(1.0, 0.0), (1.0, 0.0)], [0.5, -0.1])


def test_batch_intensity_boundaries_allowed():
    document = decode(substrate.batch([(1.0, 0.0), (1.0, 0.0)], [0, 1]))
    assert document["summary"]["quality"] == "pass"
