"""Tests for substrate.dump_aggregate and substrate.load_aggregate."""

import json

import pytest

from ocean_sonar import substrate

ANALYSIS_1 = [(3.0, 0.5), (6.0, 0.5), (None, None)]
INTENSITIES_1 = [0.4, 0.6, 0.7]
ANALYSIS_2 = [(1.0, 0.0), (2.0, 2.0)]
INTENSITIES_2 = [0.2, 0.9]


def write_batch(tmp_path, name, analysis, intensities):
    path = tmp_path / name
    path.write_bytes(substrate.batch(analysis, intensities))
    return str(path)


def write_aggregate(tmp_path, paths, name="aggregate.json"):
    path = tmp_path / name
    path.write_bytes(substrate.dump_aggregate(paths))
    return str(path)


def two_batches(tmp_path):
    first = write_batch(tmp_path, "b1.json", ANALYSIS_1, INTENSITIES_1)
    second = write_batch(tmp_path, "b2.json", ANALYSIS_2, INTENSITIES_2)
    return [first, second]


def test_dump_aggregate_round_trip(tmp_path):
    paths = two_batches(tmp_path)
    data = substrate.dump_aggregate(paths)
    assert isinstance(data, bytes)
    path = tmp_path / "aggregate.json"
    path.write_bytes(data)
    result = substrate.load_aggregate(str(path))
    assert result == substrate.aggregate(paths)
    assert list(result.keys()) == ["batches", "summary"]
    assert isinstance(result["batches"], tuple)
    assert len(result["batches"]) == 2
    assert list(result["summary"].keys()) == [
        "batch_count",
        "result_count",
        "unknown",
        "counts",
        "unknown_ratio",
        "worst_batch_index",
        "quality",
    ]
    assert list(result["summary"]["counts"].keys()) == [
        "unknown",
        "mud",
        "sand",
        "gravel",
        "rock",
    ]


def test_dump_aggregate_summary_values(tmp_path):
    paths = two_batches(tmp_path)
    document = json.loads(substrate.dump_aggregate(paths).decode("utf-8"))
    assert document["summary"] == {
        "batch_count": 2,
        "result_count": 5,
        "unknown": 1,
        "counts": {"unknown": 1, "mud": 2, "sand": 0, "gravel": 0, "rock": 2},
        "unknown_ratio": 0.2,
        "worst_batch_index": 0,
        "quality": "fail",
    }


def test_dump_aggregate_calls_aggregate_once(tmp_path, monkeypatch):
    paths = two_batches(tmp_path)
    calls = []
    real_aggregate = substrate.aggregate

    def counting_aggregate(value):
        calls.append(value)
        return real_aggregate(value)

    monkeypatch.setattr(substrate, "aggregate", counting_aggregate)
    substrate.dump_aggregate(paths)
    assert calls == [paths]


def test_dump_aggregate_exceptions_propagate(tmp_path):
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        substrate.dump_aggregate(1)
    with pytest.raises(ValueError, match="paths must have at least 2 items"):
        substrate.dump_aggregate([str(tmp_path / "only.json")])
    with pytest.raises(TypeError, match="paths\\[0\\]: must be a str"):
        substrate.dump_aggregate([1, "x"])
    with pytest.raises(FileNotFoundError):
        substrate.dump_aggregate(
            [str(tmp_path / "a.json"), str(tmp_path / "b.json")]
        )


def test_dump_aggregate_quality_pass(tmp_path):
    first = write_batch(tmp_path, "b1.json", [(1.0, 0.0)], [0.2])
    second = write_batch(tmp_path, "b2.json", [(2.0, 2.0)], [0.9])
    document = json.loads(
        substrate.dump_aggregate([first, second]).decode("utf-8")
    )
    assert document["summary"]["unknown_ratio"] == 0.0
    assert document["summary"]["quality"] == "pass"


def test_dump_aggregate_worst_batch_index_tie(tmp_path):
    first = write_batch(tmp_path, "b1.json", [(None, None)], [0.1])
    second = write_batch(tmp_path, "b2.json", [(None, None)], [None])
    document = json.loads(
        substrate.dump_aggregate([first, second]).decode("utf-8")
    )
    assert document["summary"]["worst_batch_index"] == 0
    assert document["summary"]["quality"] == "fail"


def test_load_aggregate_path_type():
    with pytest.raises(TypeError, match="path must be a str"):
        substrate.load_aggregate(1)


def test_load_aggregate_path_empty():
    with pytest.raises(ValueError, match="path must not be empty"):
        substrate.load_aggregate("")


def test_load_aggregate_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        substrate.load_aggregate(str(tmp_path / "missing.json"))


def test_load_aggregate_directory(tmp_path):
    with pytest.raises(IsADirectoryError):
        substrate.load_aggregate(str(tmp_path))


def test_load_aggregate_file_not_modified(tmp_path):
    path = write_aggregate(tmp_path, two_batches(tmp_path))
    before = (tmp_path / "aggregate.json").read_bytes()
    substrate.load_aggregate(path)
    assert (tmp_path / "aggregate.json").read_bytes() == before


def test_load_aggregate_bom_rejected(tmp_path):
    paths = two_batches(tmp_path)
    raw = b"\xef\xbb\xbf" + substrate.dump_aggregate(paths)
    path = tmp_path / "aggregate.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="must not start with a UTF-8 BOM"):
        substrate.load_aggregate(str(path))


def test_load_aggregate_trailing_newline_rejected(tmp_path):
    paths = two_batches(tmp_path)
    path = tmp_path / "aggregate.json"
    path.write_bytes(substrate.dump_aggregate(paths) + b"\n")
    with pytest.raises(ValueError, match="must not end with a trailing newline"):
        substrate.load_aggregate(str(path))


def test_load_aggregate_invalid_json(tmp_path):
    path = tmp_path / "aggregate.json"
    path.write_bytes(b"{not json}")
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load_aggregate(str(path))


def test_load_aggregate_rejects_nan(tmp_path):
    path = tmp_path / "aggregate.json"
    path.write_bytes(b'{"batches": NaN, "summary": {}}')
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load_aggregate(str(path))


def test_load_aggregate_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "aggregate.json"
    path.write_bytes(b'{"batches": [], "batches": [], "summary": {}}')
    with pytest.raises(ValueError, match="file is not valid JSON"):
        substrate.load_aggregate(str(path))


def tampered_aggregate(tmp_path, mutate):
    paths = two_batches(tmp_path)
    document = json.loads(substrate.dump_aggregate(paths).decode("utf-8"))
    mutate(document)
    path = tmp_path / "aggregate.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return str(path)


def test_load_aggregate_top_level_key_order(tmp_path):
    def mutate(document):
        document["extra"] = 1

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="keys must be in the order"):
        substrate.load_aggregate(path)


def test_load_aggregate_single_batch_rejected(tmp_path):
    def mutate(document):
        document["batches"] = document["batches"][:1]

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="at least 2 items"):
        substrate.load_aggregate(path)


def test_load_aggregate_invalid_batch_item(tmp_path):
    def mutate(document):
        document["batches"][1]["summary"]["unknown"] = 5

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="batches\\[1\\]"):
        substrate.load_aggregate(path)


def test_load_aggregate_wrong_counts(tmp_path):
    def mutate(document):
        document["summary"]["counts"]["mud"] = 0

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="counts"):
        substrate.load_aggregate(path)


def test_load_aggregate_wrong_unknown_ratio(tmp_path):
    def mutate(document):
        document["summary"]["unknown_ratio"] = 0.5

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="unknown_ratio"):
        substrate.load_aggregate(path)


def test_load_aggregate_wrong_worst_batch_index(tmp_path):
    def mutate(document):
        document["summary"]["worst_batch_index"] = 1

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="worst_batch_index"):
        substrate.load_aggregate(path)


def test_load_aggregate_wrong_quality(tmp_path):
    def mutate(document):
        document["summary"]["quality"] = "pass"

    path = tampered_aggregate(tmp_path, mutate)
    with pytest.raises(ValueError, match="quality"):
        substrate.load_aggregate(path)


def test_load_aggregate_non_canonical_bytes(tmp_path):
    paths = two_batches(tmp_path)
    text = substrate.dump_aggregate(paths).decode("utf-8")
    path = tmp_path / "aggregate.json"
    path.write_text(json.dumps(json.loads(text), indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        substrate.load_aggregate(str(path))
