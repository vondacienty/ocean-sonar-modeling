"""Tests for product.export_quality_trend."""

from __future__ import annotations

import json
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    export_quality_trend,
    serialize_quality_trend,
)


def dump_report(report):
    return json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def valid_report(**changes):
    report = {
        "layers": 2,
        "total": 4,
        "valid": 3,
        "coverage": 0.75,
        "terrain_exceed": 1,
        "unknown": 0,
        "worst": 1,
        "crosspoint": "pass",
        "quality": "fail",
    }
    report.update(changes)
    return report


def write_report(path, report):
    path.write_bytes(dump_report(report))
    return str(path)


@pytest.fixture
def report_paths(tmp_path):
    p0 = write_report(tmp_path / "r0.json", valid_report())
    p1 = write_report(
        tmp_path / "r1.json",
        valid_report(
            valid=4,
            coverage=1.0,
            terrain_exceed=0,
            unknown=0,
            worst=0,
            crosspoint="pass",
            quality="pass",
        ),
    )
    return [p0, p1]


def test_in___all__():
    assert "export_quality_trend" in product_mod.__all__
    assert product_mod.export_quality_trend is export_quality_trend


def test_success_writes_bytes_and_returns_them(tmp_path, report_paths):
    output = str(tmp_path / "trend.json")
    result = export_quality_trend(report_paths, output)
    expected = serialize_quality_trend(report_paths)
    assert isinstance(result, bytes)
    assert result == expected
    document = json.loads(result)
    assert list(document.keys()) == ["changes", "worst", "quality"]
    with open(output, "rb") as handle:
        assert handle.read() == result


def test_inputs_not_modified(tmp_path, report_paths):
    before = [open(path, "rb").read() for path in report_paths]
    export_quality_trend(report_paths, str(tmp_path / "trend.json"))
    after = [open(path, "rb").read() for path in report_paths]
    assert after == before


def test_calls_serialize_quality_trend_exactly_once(
    monkeypatch, tmp_path, report_paths
):
    calls = []
    original = product_mod.serialize_quality_trend

    def counting(paths):
        calls.append(list(paths))
        return original(paths)

    monkeypatch.setattr(product_mod, "serialize_quality_trend", counting)
    export_quality_trend(report_paths, str(tmp_path / "trend.json"))
    assert calls == [list(report_paths)]


def test_paths_validation_runs_before_output_validation():
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        export_quality_trend(123, 456)
    with pytest.raises(ValueError, match="paths must contain at least 2 items"):
        export_quality_trend(["only.json"], 456)


def test_paths_item_prefix_propagates(tmp_path, report_paths):
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        export_quality_trend([report_paths[0], 123], str(tmp_path / "o.json"))
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        export_quality_trend(["", report_paths[1]], str(tmp_path / "o.json"))


def test_serialize_exception_propagates_unchanged(monkeypatch, tmp_path):
    def raising(paths):
        raise ValueError("boom")

    monkeypatch.setattr(product_mod, "serialize_quality_trend", raising)
    with pytest.raises(ValueError, match="^boom$"):
        export_quality_trend(["a.json", "b.json"], str(tmp_path / "o.json"))


def test_output_non_str_typeerror(tmp_path, report_paths):
    with pytest.raises(TypeError, match="output must be a str"):
        export_quality_trend(report_paths, 123)


def test_output_empty_valueerror(tmp_path, report_paths):
    with pytest.raises(ValueError, match="output must not be empty"):
        export_quality_trend(report_paths, "")


def test_output_same_as_input_valueerror(tmp_path, report_paths):
    with pytest.raises(ValueError, match="same file"):
        export_quality_trend(report_paths, report_paths[1])


def test_output_samefile_via_symlink(tmp_path, report_paths):
    link = str(tmp_path / "report-link.json")
    os.symlink(report_paths[0], link)
    paths = [link, report_paths[1]]
    with pytest.raises(ValueError, match="same file"):
        export_quality_trend(paths, report_paths[0])


def test_output_samefile_via_hard_link(tmp_path, report_paths):
    hard = str(tmp_path / "report-hard.json")
    os.link(report_paths[0], hard)
    with pytest.raises(ValueError, match="same file"):
        export_quality_trend(report_paths, hard)


def test_no_temp_file_left_after_success(tmp_path, report_paths):
    export_quality_trend(report_paths, str(tmp_path / "trend.json"))
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_existing_output_unchanged_when_replace_fails(
    monkeypatch, tmp_path, report_paths
):
    output = tmp_path / "trend.json"
    original_bytes = b"do not touch"
    output.write_bytes(original_bytes)

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        export_quality_trend(report_paths, str(output))
    assert output.read_bytes() == original_bytes
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_oserror_from_write_propagates(monkeypatch, tmp_path, report_paths):
    def fail_replace(src, dst):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="nope"):
        export_quality_trend(report_paths, str(tmp_path / "trend.json"))


def test_missing_input_file(tmp_path, report_paths):
    missing = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        export_quality_trend(
            [report_paths[0], missing], str(tmp_path / "trend.json")
        )
