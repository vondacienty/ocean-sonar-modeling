"""Tests for substrate.load."""

import json

import pytest

from ocean_sonar import substrate

ANALYSIS = [(3.0, 0.5), (6.0, 0.5), (None, None), (6.0, 2.0)]
INTENSITIES = [0.4, 0.6, 0.7, 0.6]

DOCUMENT = {
    "results": [["mud", 1.0], ["rock", 1.0], ["unknown", 0.0], ["rock", 1.0]],
    "summary": {"count": 4, "unknown": 1, "quality": "fail"},
}


def write_document(path, document=DOCUMENT, raw=None):
    if raw is None:
        raw = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    path.write_bytes(raw)
    return str(path)


def test_load_round_trip(tmp_path):
    data = substrate.batch(ANALYSIS, INTENSITIES)
    path = tmp_path / "batch.json"
    path.write_bytes(data)
    result = substrate.load(str(path))
    assert result == DOCUMENT
    assert list(result.keys()) == ["results", "summary"]
    assert list(result["summary"].keys()) == ["count", "unknown", "quality"]
    assert result["results"][0] == ["mud", 1.0]


def test_load_pass_quality(tmp_path):
    data = substrate.batch([(1.0, 0.0)], [0.2])
    path = tmp_path / "batch.json"
    path.write_bytes(data)
    result = substrate.load(str(path))
    assert result["summary"] == {"count": 1, "unknown": 0, "quality": "pass"}


def test_load_file_not_modified(tmp_path):
    path = write_document(tmp_path / "batch.json")
    before = (tmp_path / "batch.json").read_bytes()
    substrate.load(path)
    assert (tmp_path / "batch.json").read_bytes() == before


def test_load_path_type():
    with pytest.raises(TypeError, match="path must be a str"):
        substrate.load(1)


def test_load_path_empty():
    with pytest.raises(ValueError, match="path must not be empty"):
        substrate.load("")


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        substrate.load(str(tmp_path / "missing.json"))


def test_load_directory(tmp_path):
    with pytest.raises(IsADirectoryError):
        substrate.load(str(tmp_path))


def test_load_bom_rejected(tmp_path):
    raw = b"\xef\xbb\xbf" + json.dumps(DOCUMENT).encode("utf-8")
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="must not start with a UTF-8 BOM"):
        substrate.load(path)


def test_load_trailing_newline_rejected(tmp_path):
    raw = json.dumps(DOCUMENT).encode("utf-8") + b"\n"
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="must not end with a trailing newline"):
        substrate.load(path)


def test_load_invalid_utf8(tmp_path):
    path = write_document(tmp_path / "batch.json", raw=b"\xff\xfe")
    with pytest.raises(ValueError, match="file is not valid UTF-8"):
        substrate.load(path)


def test_load_invalid_json(tmp_path):
    path = write_document(tmp_path / "batch.json", raw=b"{not json")
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load(path)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_load_non_finite_constant_rejected(tmp_path, constant):
    raw = (
        '{"results":[["mud",1.0]],"summary":{"count":1,"unknown":0,'
        '"quality":"pass"},"extra":' + constant + "}"
    ).encode("utf-8")
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load(path)


def test_load_nan_confidence_rejected(tmp_path):
    raw = b'{"results":[["mud",NaN]],"summary":{"count":1,"unknown":0,"quality":"pass"}}'
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load(path)


def test_load_duplicate_keys_rejected(tmp_path):
    raw = (
        b'{"results":[["mud",1.0]],"results":[["mud",1.0]],'
        b'"summary":{"count":1,"unknown":0,"quality":"pass"}}'
    )
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load(path)


def test_load_non_object_rejected(tmp_path):
    path = write_document(tmp_path / "batch.json", raw=b"[1,2,3]")
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_top_level_key_order(tmp_path):
    raw = b'{"summary":{"count":1,"unknown":0,"quality":"pass"},"results":[["mud",1.0]]}'
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_results_non_empty(tmp_path):
    document = {"results": [], "summary": {"count": 0, "unknown": 0, "quality": "pass"}}
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_result_item_not_list(tmp_path):
    document = {
        "results": [["mud", 1.0], "mud"],
        "summary": {"count": 2, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_result_item_length(tmp_path):
    document = {
        "results": [["mud", 1.0, 2.0]],
        "summary": {"count": 1, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_class_enum(tmp_path):
    document = {
        "results": [["clay", 1.0]],
        "summary": {"count": 1, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_confidence_must_be_float(tmp_path):
    document = {
        "results": [["mud", 1]],
        "summary": {"count": 1, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_confidence_relation(tmp_path):
    document = {
        "results": [["unknown", 1.0]],
        "summary": {"count": 1, "unknown": 1, "quality": "fail"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)
    document = {
        "results": [["mud", 0.0]],
        "summary": {"count": 1, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_confidence_negative_zero_rejected(tmp_path):
    raw = b'{"results":[["unknown",-0.0]],"summary":{"count":1,"unknown":1,"quality":"fail"}}'
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_summary_key_order(tmp_path):
    raw = (
        b'{"results":[["mud",1.0]],'
        b'"summary":{"unknown":0,"count":1,"quality":"pass"}}'
    )
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_summary_count_type(tmp_path):
    raw = b'{"results":[["mud",1.0]],"summary":{"count":1.0,"unknown":0,"quality":"pass"}}'
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_summary_count_relation(tmp_path):
    document = {
        "results": [["mud", 1.0]],
        "summary": {"count": 2, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_summary_unknown_relation(tmp_path):
    document = {
        "results": [["mud", 1.0], ["unknown", 0.0]],
        "summary": {"count": 2, "unknown": 0, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_summary_quality_relation(tmp_path):
    document = {
        "results": [["unknown", 0.0]],
        "summary": {"count": 1, "unknown": 1, "quality": "pass"},
    }
    path = write_document(tmp_path / "batch.json", document)
    with pytest.raises(ValueError, match="file does not contain a valid batch"):
        substrate.load(path)


def test_load_non_canonical_bytes_rejected(tmp_path):
    raw = json.dumps(DOCUMENT, indent=2).encode("utf-8")
    path = write_document(tmp_path / "batch.json", raw=raw)
    with pytest.raises(
        ValueError, match="file bytes do not match the canonical batch output"
    ):
        substrate.load(path)
