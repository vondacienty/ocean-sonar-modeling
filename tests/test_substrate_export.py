"""Tests for substrate.export."""

from __future__ import annotations

import os

import pytest

from ocean_sonar import substrate as substrate_mod
from ocean_sonar.substrate import batch, export

ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]


@pytest.fixture
def batch_path(tmp_path):
    path = tmp_path / "batch.json"
    path.write_bytes(batch(ANALYSIS, INTENSITIES))
    return str(path)


def test_in___all__():
    assert "export" in substrate_mod.__all__


def test_success_writes_canonical_bytes_and_returns_them(tmp_path, batch_path):
    output = str(tmp_path / "copy.json")
    result = export(batch_path, output)
    expected = batch(ANALYSIS, INTENSITIES)
    assert isinstance(result, bytes)
    assert result == expected
    with open(output, "rb") as handle:
        assert handle.read() == expected


def test_input_file_not_modified(tmp_path, batch_path):
    before = open(batch_path, "rb").read()
    export(batch_path, str(tmp_path / "copy.json"))
    assert open(batch_path, "rb").read() == before


def test_overwrites_existing_output(tmp_path, batch_path):
    output = tmp_path / "copy.json"
    output.write_bytes(b"old contents")
    result = export(batch_path, str(output))
    assert output.read_bytes() == result


def test_calls_load_exactly_once(monkeypatch, tmp_path, batch_path):
    calls = []
    original = substrate_mod.load

    def counting(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(substrate_mod, "load", counting)
    output = str(tmp_path / "copy.json")
    export(batch_path, output)
    assert calls == [batch_path]


def test_load_validation_runs_before_output_validation(tmp_path, batch_path):
    missing = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        export(missing, 123)
    with pytest.raises(TypeError, match="path must be a str"):
        export(123, 456)
    with pytest.raises(ValueError, match="path must not be empty"):
        export("", "")


def test_load_exception_propagates_unchanged(monkeypatch, tmp_path, batch_path):
    def raising(path):
        raise ValueError("boom")

    monkeypatch.setattr(substrate_mod, "load", raising)
    with pytest.raises(ValueError, match="^boom$"):
        export(batch_path, str(tmp_path / "copy.json"))


def test_invalid_batch_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError, match="file is not valid JSON"):
        export(str(path), str(tmp_path / "copy.json"))
    assert not (tmp_path / "copy.json").exists()


def test_output_non_str_typeerror(tmp_path, batch_path):
    with pytest.raises(TypeError, match="output must be a str"):
        export(batch_path, 123)


def test_output_empty_valueerror(tmp_path, batch_path):
    with pytest.raises(ValueError, match="output must not be empty"):
        export(batch_path, "")


def test_output_same_as_input_valueerror(tmp_path, batch_path):
    with pytest.raises(ValueError, match="same file"):
        export(batch_path, batch_path)


def test_output_samefile_via_symlink(tmp_path, batch_path):
    link = str(tmp_path / "batch-link.json")
    os.symlink(batch_path, link)
    with pytest.raises(ValueError, match="same file"):
        export(batch_path, link)
    with pytest.raises(ValueError, match="same file"):
        export(link, batch_path)


def test_output_samefile_via_hard_link(tmp_path, batch_path):
    hard = str(tmp_path / "batch-hard.json")
    os.link(batch_path, hard)
    with pytest.raises(ValueError, match="same file"):
        export(batch_path, hard)


def test_output_resolves_to_input_through_nonexistent_component(tmp_path, batch_path):
    os.symlink(tmp_path, tmp_path / "selflink")
    equivalent = str(tmp_path / "selflink" / "missing" / ".." / "batch.json")
    assert not os.path.exists(equivalent)
    with pytest.raises(ValueError, match="same file"):
        export(batch_path, equivalent)


def test_no_temp_file_left_after_success(tmp_path, batch_path):
    export(batch_path, str(tmp_path / "copy.json"))
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_existing_output_unchanged_when_replace_fails(
    monkeypatch, tmp_path, batch_path
):
    output = tmp_path / "copy.json"
    original_bytes = b"do not touch"
    output.write_bytes(original_bytes)

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        export(batch_path, str(output))
    assert output.read_bytes() == original_bytes
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_input_unchanged_when_write_fails(monkeypatch, tmp_path, batch_path):
    before = open(batch_path, "rb").read()
    output = tmp_path / "copy.json"
    output.write_bytes(b"old")

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        export(batch_path, str(output))
    assert open(batch_path, "rb").read() == before


def test_oserror_from_write_propagates(monkeypatch, tmp_path, batch_path):
    def fail_replace(src, dst):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="nope"):
        export(batch_path, str(tmp_path / "copy.json"))
