"""Tests for report.load_dashboard_summary."""

import json

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.report import load_dashboard_summary, serialize_dashboard_summary

CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]
LAYERS = [
    (1.0, 2, 2, [(1.0, 0.5), (2.0, 0.0), (4.0, 1.0), (0.0, 0.0)]),
]
TOLERANCES = [0.1, 0.5, 1.0]

DATA = serialize_dashboard_summary(CROSSINGS, TOLERANCES, LAYERS)
GOOD = json.loads(DATA)


def _write(tmp_path, data, name="summary.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _mutated(**changes):
    value = dict(GOOD)
    value.update(changes)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_load_dashboard_summary_exported():
    assert "load_dashboard_summary" in report_mod.__all__
    assert report_mod.load_dashboard_summary is load_dashboard_summary


def test_roundtrip(tmp_path):
    path = _write(tmp_path, DATA)
    summary = load_dashboard_summary(path)
    assert isinstance(summary, dict)
    assert list(summary.keys()) == [
        "tolerance_count",
        "pass_count",
        "fail_count",
        "first_pass_index",
        "terrain_total",
        "terrain_valid",
        "terrain_coverage",
        "quality_score",
    ]
    assert summary == GOOD
    for key in (
        "tolerance_count",
        "pass_count",
        "fail_count",
        "first_pass_index",
        "terrain_total",
        "terrain_valid",
    ):
        assert type(summary[key]) is int
    assert type(summary["terrain_coverage"]) is float
    assert type(summary["quality_score"]) is float


def test_roundtrip_no_pass(tmp_path):
    data = serialize_dashboard_summary(
        [(0.0, 0.0, 10.0, 9.0)], [0.5], [(1.0, 1, 1, [(None, None)])]
    )
    summary = load_dashboard_summary(_write(tmp_path, data))
    assert summary["pass_count"] == 0
    assert summary["first_pass_index"] is None
    assert summary["terrain_valid"] == 0
    assert summary["terrain_coverage"] == 0.0
    assert summary["quality_score"] == 0.0
    assert type(summary["terrain_coverage"]) is float
    assert type(summary["quality_score"]) is float


def test_file_not_modified(tmp_path):
    path = _write(tmp_path, DATA)
    load_dashboard_summary(path)
    with open(path, "rb") as handle:
        assert handle.read() == DATA


def test_path_type_error():
    with pytest.raises(TypeError):
        load_dashboard_summary(42)
    with pytest.raises(TypeError):
        load_dashboard_summary(None)
    with pytest.raises(TypeError):
        load_dashboard_summary(b"summary.json")


def test_path_empty_value_error():
    with pytest.raises(ValueError):
        load_dashboard_summary("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dashboard_summary(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_dashboard_summary(str(tmp_path))


def test_bom_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, b"\xef\xbb\xbf" + DATA))


def test_trailing_newline_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, DATA + b"\n"))


def test_invalid_utf8(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, DATA[:-2] + b"\xff\xfe"))


def test_invalid_json(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, b"{"))


def test_non_object_json(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, b"[1,2,3]"))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, b"42"))


def test_nan_infinity_constants_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(quality_score=float("nan"))))
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(tmp_path, _mutated(terrain_coverage=float("inf")))
        )


def test_key_order_rejected(tmp_path):
    keys = list(GOOD)
    reordered = {key: GOOD[key] for key in keys[1:] + keys[:1]}
    data = json.dumps(reordered, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, data))


def test_missing_and_extra_keys(tmp_path):
    missing = {key: GOOD[key] for key in GOOD if key != "quality_score"}
    data = json.dumps(missing, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, data))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(extra=1)))


def test_count_type_errors(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(tolerance_count=True)))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(pass_count=1.0)))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(terrain_total="4")))


def test_count_range_errors(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(tolerance_count=0)))
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(tmp_path, _mutated(pass_count=GOOD["tolerance_count"] + 1))
        )
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(pass_count=-1)))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(terrain_total=0)))
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(tmp_path, _mutated(terrain_valid=GOOD["terrain_total"] + 1))
        )


def test_fail_count_relation(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(tmp_path, _mutated(fail_count=GOOD["fail_count"] + 1))
        )


def test_first_pass_index_checks(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(first_pass_index=-1)))
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(
                tmp_path,
                _mutated(first_pass_index=GOOD["tolerance_count"]),
            )
        )
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(first_pass_index=True)))


def test_ratio_type_and_value_checks(tmp_path):
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(terrain_coverage=1)))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(terrain_coverage=0.5)))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(quality_score="66.6")))
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, _mutated(quality_score=0.0)))


def test_noncanonical_bytes_rejected(tmp_path):
    # whitespace added by a non-compact encoder
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, json.dumps(GOOD).encode("utf-8")))
    # negative zero must be normalized to 0.0
    with pytest.raises(ValueError):
        load_dashboard_summary(
            _write(tmp_path, _mutated(terrain_coverage=-0.0))
        )
    # non-canonical float representation
    with pytest.raises(ValueError):
        load_dashboard_summary(_write(tmp_path, DATA.replace(b"1.0", b"1.00", 1)))
