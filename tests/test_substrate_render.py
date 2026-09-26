"""Tests for substrate.render."""

from __future__ import annotations

import json

import pytest

from ocean_sonar import substrate as substrate_mod
from ocean_sonar.substrate import batch, render

ANALYSIS = [[3.0, 0.5], [6.0, 0.5], [None, None], [6.0, 2.0]]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]

EXPECTED = (
    "SUBSTRATE=4,1,fail\n"
    "RESULT[0]=mud,1.000000\n"
    "RESULT[1]=rock,1.000000\n"
    "RESULT[2]=unknown,0.000000\n"
    "RESULT[3]=rock,1.000000"
)


@pytest.fixture
def batch_path(tmp_path):
    path = tmp_path / "batch.json"
    path.write_bytes(batch(ANALYSIS, INTENSITIES))
    return str(path)


def test_in___all__():
    assert "render" in substrate_mod.__all__


def test_render_failing_batch(tmp_path, batch_path):
    text = render(batch_path)
    assert isinstance(text, str)
    assert not text.endswith("\n")
    assert text == EXPECTED


def test_render_passing_batch(tmp_path):
    path = tmp_path / "batch.json"
    path.write_bytes(batch([[1.0, 0.0]], [0.2]))
    text = render(str(path))
    assert text == "SUBSTRATE=1,0,pass\nRESULT[0]=mud,1.000000"


def test_render_all_unknown(tmp_path):
    path = tmp_path / "batch.json"
    path.write_bytes(batch([[None, None], [None, 0.5]], [None, 0.3]))
    text = render(str(path))
    assert text == (
        "SUBSTRATE=2,2,fail\n"
        "RESULT[0]=unknown,0.000000\n"
        "RESULT[1]=unknown,0.000000"
    )


def test_results_rendered_in_stored_order(tmp_path):
    document = {
        "results": [
            ["sand", 1.0],
            ["gravel", 1.0],
            ["rock", 1.0],
            ["mud", 1.0],
            ["unknown", 0.0],
        ],
        "summary": {"count": 5, "unknown": 1, "quality": "fail"},
    }
    path = tmp_path / "batch.json"
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    text = render(str(path))
    assert text == (
        "SUBSTRATE=5,1,fail\n"
        "RESULT[0]=sand,1.000000\n"
        "RESULT[1]=gravel,1.000000\n"
        "RESULT[2]=rock,1.000000\n"
        "RESULT[3]=mud,1.000000\n"
        "RESULT[4]=unknown,0.000000"
    )


def test_render_file_not_modified(tmp_path, batch_path):
    before = open(batch_path, "rb").read()
    render(batch_path)
    assert open(batch_path, "rb").read() == before


def test_calls_load_exactly_once(monkeypatch, tmp_path, batch_path):
    calls = []
    original = substrate_mod.load

    def counting(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(substrate_mod, "load", counting)
    assert render(batch_path) == EXPECTED
    assert calls == [batch_path]


def test_load_exception_propagates_unchanged(monkeypatch, tmp_path, batch_path):
    def raising(path):
        raise ValueError("boom")

    monkeypatch.setattr(substrate_mod, "load", raising)
    with pytest.raises(ValueError, match="^boom$"):
        render(batch_path)


def test_path_type_error():
    with pytest.raises(TypeError, match="path must be a str"):
        render(1)


def test_path_empty_error():
    with pytest.raises(ValueError, match="path must not be empty"):
        render("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        render(str(tmp_path / "missing.json"))


def test_directory(tmp_path):
    with pytest.raises(IsADirectoryError):
        render(str(tmp_path))


def test_corrupted_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError, match="file is not valid JSON"):
        render(str(path))
