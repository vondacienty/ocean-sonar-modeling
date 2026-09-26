"""Tests for crosspoint.export_audit_report."""

from __future__ import annotations

import json
import os

import pytest

from ocean_sonar import crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    export_audit_report,
    serialize_audit,
    serialize_audit_report,
)


def write_comparison(path, changes):
    """Write a canonical serialize_comparison-shaped JSON file."""
    quality = "fail" if any(c["quality"] == "fail" for c in changes) else "pass"
    document = {"changes": changes, "worst": changes[0], "quality": quality}
    with open(path, "wb") as handle:
        handle.write(
            json.dumps(
                document,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    return str(path)


def change(index, degraded_delta, coverage_delta, score_delta, quality):
    return {
        "index": index,
        "degraded_delta": degraded_delta,
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "quality": quality,
    }


@pytest.fixture
def audit_path(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json", [change(1, 1, -0.2, -0.5, "fail")]
    )
    path = tmp_path / "audit.json"
    path.write_bytes(serialize_audit([p0, p1]))
    return str(path)


def test_in___all__():
    assert "export_audit_report" in crosspoint_mod.__all__


def test_success_writes_bytes_and_returns_them(tmp_path, audit_path):
    output = str(tmp_path / "report.json")
    result = export_audit_report(audit_path, output)
    expected = serialize_audit_report(audit_path)
    assert isinstance(result, bytes)
    assert result == expected
    with open(output, "rb") as handle:
        assert handle.read() == expected


def test_audit_file_not_modified(tmp_path, audit_path):
    before = open(audit_path, "rb").read()
    export_audit_report(audit_path, str(tmp_path / "report.json"))
    assert open(audit_path, "rb").read() == before


def test_overwrites_existing_output(tmp_path, audit_path):
    output = tmp_path / "report.json"
    output.write_bytes(b"old contents")
    result = export_audit_report(audit_path, str(output))
    assert output.read_bytes() == result


def test_calls_serialize_audit_report_exactly_once(monkeypatch, tmp_path, audit_path):
    calls = []
    original = crosspoint_mod.serialize_audit_report

    def counting(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(crosspoint_mod, "serialize_audit_report", counting)
    output = str(tmp_path / "report.json")
    result = export_audit_report(audit_path, output)
    assert calls == [audit_path]
    assert result == original(audit_path)


def test_audit_validation_runs_before_output_validation(tmp_path, audit_path):
    bad_audit = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        export_audit_report(bad_audit, 123)
    with pytest.raises(TypeError, match="path must be a str"):
        export_audit_report(123, 456)
    with pytest.raises(ValueError, match="path must not be empty"):
        export_audit_report("", "")


def test_serialize_exception_propagates_unchanged(monkeypatch, tmp_path, audit_path):
    def raising(path):
        raise ValueError("boom")

    monkeypatch.setattr(crosspoint_mod, "serialize_audit_report", raising)
    with pytest.raises(ValueError, match="^boom$"):
        export_audit_report(audit_path, str(tmp_path / "report.json"))


def test_output_non_str_typeerror(tmp_path, audit_path):
    with pytest.raises(TypeError, match="output must be a str"):
        export_audit_report(audit_path, 123)


def test_output_empty_valueerror(tmp_path, audit_path):
    with pytest.raises(ValueError, match="output must not be empty"):
        export_audit_report(audit_path, "")


def test_output_same_as_audit_valueerror(tmp_path, audit_path):
    with pytest.raises(ValueError, match="same file"):
        export_audit_report(audit_path, audit_path)


def test_output_samefile_via_symlink(tmp_path, audit_path):
    link = str(tmp_path / "audit-link.json")
    os.symlink(audit_path, link)
    with pytest.raises(ValueError, match="same file"):
        export_audit_report(audit_path, link)
    with pytest.raises(ValueError, match="same file"):
        export_audit_report(link, audit_path)


def test_output_samefile_via_hard_link(tmp_path, audit_path):
    hard = str(tmp_path / "audit-hard.json")
    os.link(audit_path, hard)
    with pytest.raises(ValueError, match="same file"):
        export_audit_report(audit_path, hard)


def test_output_resolves_to_audit_through_nonexistent_component(tmp_path, audit_path):
    # ``selflink`` points back at tmp_path; the middle component does not
    # exist, so os.path.exists(output) is False while realpath resolves
    # back to the audit — exercising the normalized-string fallback.
    os.symlink(tmp_path, tmp_path / "selflink")
    equivalent = str(tmp_path / "selflink" / "missing" / ".." / "audit.json")
    assert not os.path.exists(equivalent)
    with pytest.raises(ValueError, match="same file"):
        export_audit_report(audit_path, equivalent)


def test_output_in_other_directory_is_fine(tmp_path, audit_path):
    other = tmp_path / "nested" / "deep"
    other.mkdir(parents=True)
    output = str(other / "report.json")
    result = export_audit_report(audit_path, output)
    assert open(output, "rb").read() == result


def test_no_temp_file_left_after_success(tmp_path, audit_path):
    output = str(tmp_path / "report.json")
    export_audit_report(audit_path, output)
    leftovers = [
        name for name in os.listdir(tmp_path)
        if name.endswith(".tmp")
    ]
    assert leftovers == []


def test_existing_output_unchanged_when_replace_fails(
    monkeypatch, tmp_path, audit_path
):
    output = tmp_path / "report.json"
    original_bytes = b"do not touch"
    output.write_bytes(original_bytes)

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        export_audit_report(audit_path, str(output))
    assert output.read_bytes() == original_bytes
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_audit_unchanged_when_write_fails(monkeypatch, tmp_path, audit_path):
    before = open(audit_path, "rb").read()
    output = tmp_path / "report.json"
    output.write_bytes(b"old")

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        export_audit_report(audit_path, str(output))
    assert open(audit_path, "rb").read() == before


def test_oserror_from_write_propagates(monkeypatch, tmp_path, audit_path):
    def fail_replace(src, dst):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="nope"):
        export_audit_report(audit_path, str(tmp_path / "report.json"))
