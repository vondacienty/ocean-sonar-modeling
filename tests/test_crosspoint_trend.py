"""Tests for crosspoint.trend."""

import json
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import dump_aggregate, trend
from ocean_sonar.crosspoint import render_trend, serialize_trend
from ocean_sonar.crosspoint import load_trend


def _q6(value):
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def make_quality_batch(records):
    """Build a valid quality-batch dict from (coverage, score, quality) rows."""
    rows = [
        {"index": i, "coverage": _q6(coverage), "score": _q6(score), "quality": quality}
        for i, (coverage, score, quality) in enumerate(records)
    ]
    n = len(rows)
    mean_score = _q6(math.fsum(row["score"] for row in rows) / n)
    worst_index = min(
        range(n), key=lambda i: (rows[i]["score"], rows[i]["coverage"], i)
    )
    quality = "pass" if all(row["quality"] == "pass" for row in rows) else "fail"
    return {
        "records": rows,
        "summary": {
            "count": n,
            "mean_score": mean_score,
            "worst_index": worst_index,
            "quality": quality,
        },
    }


def write_aggregate(path, batches):
    """Write a canonical aggregate file from [(batch_path, records), ...]."""
    items = [
        {"index": i, "path": batch_path, "batch": make_quality_batch(records)}
        for i, (batch_path, records) in enumerate(batches)
    ]
    coverages = []
    scores = []
    all_pass = True
    worst_position = None
    for i, item in enumerate(items):
        for row in item["batch"]["records"]:
            coverages.append(row["coverage"])
            scores.append(row["score"])
            if row["quality"] != "pass":
                all_pass = False
            position = (row["score"], row["coverage"], i, row["index"])
            if worst_position is None or position < worst_position:
                worst_position = position
    n_records = len(coverages)
    aggregate = {
        "batches": items,
        "summary": {
            "batch_count": len(items),
            "record_count": n_records,
            "mean_coverage": _q6(math.fsum(coverages) / n_records),
            "mean_score": _q6(math.fsum(scores) / n_records),
            "worst_batch_index": int(worst_position[2]),
            "worst_record_index": int(worst_position[3]),
            "quality": "pass" if all_pass else "fail",
        },
        "quality": "pass" if all_pass else "fail",
    }
    path.write_text(
        json.dumps(
            aggregate, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ),
        encoding="utf-8",
    )
    return path


EXPECTED_KEYS = [
    "count",
    "changes",
    "degraded",
    "coverage_delta",
    "score_delta",
    "worst",
    "quality",
]


@pytest.fixture
def snapshot_paths(tmp_path):
    # Two batches per snapshot: "p0" with two records, "p1" with one.
    snapshots = [
        [
            ("p0", [(0.8, 80.0, "pass"), (0.9, 90.0, "pass")]),
            ("p1", [(1.0, 100.0, "pass")]),
        ],
        [
            ("p0", [(0.85, 81.0, "pass"), (0.85, 90.0, "pass")]),
            ("p1", [(1.0, 100.0, "pass")]),
        ],
        [
            ("p0", [(0.85, 81.0, "fail"), (0.85, 90.0, "pass")]),
            ("p1", [(0.95, 99.0, "pass")]),
        ],
    ]
    paths = []
    for i, batches in enumerate(snapshots):
        path = tmp_path / f"snapshot_{i}.json"
        write_aggregate(path, batches)
        paths.append(str(path))
    return paths


def test_trend_basic(snapshot_paths):
    result = trend(list(snapshot_paths))

    assert list(result.keys()) == EXPECTED_KEYS
    assert result["count"] == 3
    assert isinstance(result["count"], int)
    # K = (n - 1) * total records = 2 * 3
    assert result["changes"] == 6
    assert isinstance(result["changes"], int)
    # Degraded: i=1 b=0 r=1 (coverage drop), i=2 b=0 r=0 (pass->fail),
    # i=2 b=1 r=0 (coverage and score drop)
    assert result["degraded"] == 3
    assert isinstance(result["degraded"], int)
    assert result["quality"] == "fail"

    # dc: +0.05, -0.05, 0, 0, 0, -0.05 -> fsum = -0.05
    assert result["coverage_delta"] == -0.008333
    # ds: +1, 0, 0, 0, 0, -1 -> fsum = 0
    assert result["score_delta"] == 0.0
    assert math.copysign(1.0, result["score_delta"]) == 1.0

    worst = result["worst"]
    assert isinstance(worst, tuple)
    assert worst == (2, 1, 0, -0.05, -1.0)
    assert all(isinstance(v, int) for v in worst[:3])
    assert all(isinstance(v, float) for v in worst[3:])


def test_trend_tuple_paths(snapshot_paths):
    result = trend(tuple(snapshot_paths))
    assert result["count"] == 3
    assert result["changes"] == 6


def test_trend_identical_snapshots_pass(tmp_path):
    batches = [
        ("p0", [(0.5, 50.0, "pass"), (0.75, 75.0, "pass")]),
        ("p1", [(1.0, 100.0, "fail")]),
    ]
    first = write_aggregate(tmp_path / "a.json", batches)
    second = write_aggregate(tmp_path / "b.json", batches)

    result = trend([str(first), str(second)])
    assert result == {
        "count": 2,
        "changes": 3,
        "degraded": 0,
        "coverage_delta": 0.0,
        "score_delta": 0.0,
        "worst": (1, 0, 0, 0.0, 0.0),
        "quality": "pass",
    }
    # A fail that stays fail is not a pass->fail degradation.
    assert math.copysign(1.0, result["coverage_delta"]) == 1.0
    assert math.copysign(1.0, result["score_delta"]) == 1.0
    assert math.copysign(1.0, result["worst"][3]) == 1.0
    assert math.copysign(1.0, result["worst"][4]) == 1.0


def test_trend_fail_to_pass_is_not_degraded(tmp_path):
    first = write_aggregate(
        tmp_path / "a.json", [("p0", [(0.5, 50.0, "fail")])]
    )
    second = write_aggregate(
        tmp_path / "b.json", [("p0", [(0.6, 51.0, "pass")])]
    )
    result = trend([str(first), str(second)])
    assert result["degraded"] == 0
    assert result["quality"] == "pass"
    assert result["coverage_delta"] == 0.1
    assert result["score_delta"] == 1.0
    assert result["worst"] == (1, 0, 0, 0.1, 1.0)


def test_trend_worst_uses_unrounded_deltas(tmp_path):
    # 0.3 - 0.1 == 0.19999999999999998 (rounds to 0.2)
    # 0.2 - 0.0 == 0.2
    first = write_aggregate(
        tmp_path / "a.json",
        [("p0", [(0.5, 0.1, "pass"), (0.5, 0.0, "pass")])],
    )
    second = write_aggregate(
        tmp_path / "b.json",
        [("p0", [(0.5, 0.3, "pass"), (0.5, 0.2, "pass")])],
    )
    result = trend([str(first), str(second)])
    # Both ds round to 0.2, but the unrounded value at r=0 is smaller.
    assert result["worst"][:3] == (1, 0, 0)
    assert result["worst"][4] == 0.2


def test_trend_worst_tie_position_order(tmp_path):
    # Two identical zero-delta comparisons resolve to (i, b, r) = (1, 0, 0).
    first = write_aggregate(
        tmp_path / "a.json",
        [("p0", [(0.5, 10.0, "pass"), (0.5, 20.0, "pass")])],
    )
    second = write_aggregate(
        tmp_path / "b.json",
        [("p0", [(0.5, 10.0, "pass"), (0.5, 20.0, "pass")])],
    )
    result = trend([str(first), str(second)])
    assert result["worst"] == (1, 0, 0, 0.0, 0.0)


def test_trend_paths_container_validation():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        trend({})
    with pytest.raises(TypeError):
        trend("a/b")


def test_trend_paths_count_validation():
    with pytest.raises(ValueError, match="at least 2 items"):
        trend([])
    # Count is checked before item types.
    with pytest.raises(ValueError, match="at least 2 items"):
        trend([123])


def test_trend_paths_item_validation():
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        trend(["a", 5])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        trend(["", "b"])
    # Items are checked in index order.
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        trend([None, ""])


def test_trend_loads_each_path_once_in_order(monkeypatch, snapshot_paths):
    calls = []

    def fake_load_aggregate(path):
        calls.append(path)
        return {"batches": ({"index": 0, "path": "p0",
                             "batch": {"records": [
                                 {"index": 0, "coverage": 0.5,
                                  "score": 50.0, "quality": "pass"}]}},),
                "summary": {}, "quality": "pass"}

    monkeypatch.setattr(crosspoint_mod, "load_aggregate", fake_load_aggregate)
    paths = list(snapshot_paths)
    result = trend(paths)

    assert calls == paths
    assert result["count"] == 3
    assert result["changes"] == 2


def test_trend_load_exception_propagates(monkeypatch, snapshot_paths):
    calls = []

    class Boom(Exception):
        pass

    def fake_load_aggregate(path):
        calls.append(path)
        if len(calls) == 2:
            raise Boom("disk on fire")
        return {"batches": ({"index": 0, "path": "p0",
                             "batch": {"records": [
                                 {"index": 0, "coverage": 0.5,
                                  "score": 50.0, "quality": "pass"}]}},),
                "summary": {}, "quality": "pass"}

    monkeypatch.setattr(crosspoint_mod, "load_aggregate", fake_load_aggregate)
    with pytest.raises(Boom, match="disk on fire"):
        trend(list(snapshot_paths))
    assert len(calls) == 2


def test_trend_missing_file_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        trend([str(tmp_path / "nope1.json"), str(tmp_path / "nope2.json")])


def test_trend_inputs_and_files_not_modified(snapshot_paths):
    paths = list(snapshot_paths)
    before = [open(p, "rb").read() for p in paths]
    trend(paths)
    assert paths == snapshot_paths
    after = [open(p, "rb").read() for p in paths]
    assert after == before


def test_trend_batch_count_mismatch(tmp_path):
    first = write_aggregate(
        tmp_path / "a.json",
        [("p0", [(0.5, 50.0, "pass")]), ("p1", [(0.5, 50.0, "pass")])],
    )
    second = write_aggregate(
        tmp_path / "b.json", [("p0", [(0.5, 50.0, "pass")])]
    )
    with pytest.raises(ValueError, match="batches"):
        trend([str(first), str(second)])


def test_trend_batch_path_mismatch(tmp_path):
    first = write_aggregate(
        tmp_path / "a.json", [("p0", [(0.5, 50.0, "pass")])]
    )
    second = write_aggregate(
        tmp_path / "b.json", [("other", [(0.5, 50.0, "pass")])]
    )
    with pytest.raises(ValueError, match="path"):
        trend([str(first), str(second)])


def test_trend_record_count_mismatch(tmp_path):
    first = write_aggregate(
        tmp_path / "a.json",
        [("p0", [(0.5, 50.0, "pass"), (0.6, 60.0, "pass")])],
    )
    second = write_aggregate(
        tmp_path / "b.json", [("p0", [(0.5, 50.0, "pass")])]
    )
    with pytest.raises(ValueError, match="records"):
        trend([str(first), str(second)])


def test_trend_delta_fsum_average(tmp_path):
    # Two comparisons: dc = 0.1 + 0.2 in float terms; mean via math.fsum.
    first = write_aggregate(
        tmp_path / "a.json",
        [("p0", [(0.0, 0.0, "pass")]), ("p1", [(0.0, 0.0, "pass")])],
    )
    second = write_aggregate(
        tmp_path / "b.json",
        [("p0", [(0.1, 0.0, "pass")]), ("p1", [(0.2, 0.0, "pass")])],
    )
    result = trend([str(first), str(second)])
    assert result["coverage_delta"] == _q6(math.fsum([0.1, 0.2]) / 2)


def test_trend_exported():
    assert hasattr(crosspoint_mod, "trend")
    assert "trend" in crosspoint_mod.__all__
    assert dump_aggregate  # sibling API untouched


def test_serialize_trend_document(snapshot_paths):
    data = serialize_trend(list(snapshot_paths))

    assert isinstance(data, bytes)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")

    document = json.loads(data)
    assert list(document.keys()) == EXPECTED_KEYS
    assert document["count"] == 3
    assert document["changes"] == 6
    assert document["degraded"] == 3
    assert document["coverage_delta"] == -0.008333
    assert document["score_delta"] == 0.0
    assert math.copysign(1.0, document["score_delta"]) == 1.0
    assert document["worst"] == [2, 1, 0, -0.05, -1.0]
    assert document["quality"] == "fail"

    # Compact canonical JSON, non-ASCII preserved.
    assert data == json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_serialize_trend_matches_trend(snapshot_paths):
    result = trend(tuple(snapshot_paths))
    document = json.loads(serialize_trend(snapshot_paths))

    assert document["count"] == result["count"]
    assert document["changes"] == result["changes"]
    assert document["degraded"] == result["degraded"]
    assert document["coverage_delta"] == result["coverage_delta"]
    assert document["score_delta"] == result["score_delta"]
    assert document["worst"] == list(result["worst"])
    assert document["quality"] == result["quality"]


def test_serialize_trend_pass_identical(tmp_path):
    batches = [("p0", [(0.5, 50.0, "pass")])]
    first = write_aggregate(tmp_path / "a.json", batches)
    second = write_aggregate(tmp_path / "b.json", batches)

    data = serialize_trend([str(first), str(second)])
    document = json.loads(data)
    assert document == {
        "count": 2,
        "changes": 1,
        "degraded": 0,
        "coverage_delta": 0.0,
        "score_delta": 0.0,
        "worst": [1, 0, 0, 0.0, 0.0],
        "quality": "pass",
    }
    # Negative zero is normalized; zero renders without a sign.
    assert b'"coverage_delta":0.0' in data
    assert b'"worst":[1,0,0,0.0,0.0]' in data


def test_serialize_trend_calls_trend_once(monkeypatch, snapshot_paths):
    calls = []
    original = crosspoint_mod.trend

    def counting(paths):
        calls.append(list(paths))
        return original(paths)

    monkeypatch.setattr(crosspoint_mod, "trend", counting)
    paths = list(snapshot_paths)
    serialize_trend(paths)
    assert calls == [paths]


def test_serialize_trend_validation_passthrough():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        serialize_trend({})
    with pytest.raises(ValueError, match="at least 2 items"):
        serialize_trend(["only"])
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        serialize_trend([None, "b"])


def test_serialize_trend_load_exception_passthrough(tmp_path):
    with pytest.raises(FileNotFoundError):
        serialize_trend(
            [str(tmp_path / "nope1.json"), str(tmp_path / "nope2.json")]
        )


def test_serialize_trend_does_not_modify_inputs_or_files(snapshot_paths):
    paths = list(snapshot_paths)
    before = [open(p, "rb").read() for p in paths]
    serialize_trend(paths)
    assert paths == snapshot_paths
    assert [open(p, "rb").read() for p in paths] == before


def test_render_trend_lines(snapshot_paths):
    text = render_trend(list(snapshot_paths))

    assert isinstance(text, str)
    assert not text.endswith("\n")
    lines = text.split("\n")
    assert lines == [
        "TREND=3,6,3,-0.008333,0.000000,fail",
        "WORST=2,1,0,-0.050000,-1.000000",
    ]


def test_render_trend_pass_identical(tmp_path):
    batches = [("p0", [(0.5, 50.0, "pass")])]
    first = write_aggregate(tmp_path / "a.json", batches)
    second = write_aggregate(tmp_path / "b.json", batches)

    text = render_trend([str(first), str(second)])
    assert text == (
        "TREND=2,1,0,0.000000,0.000000,pass\n"
        "WORST=1,0,0,0.000000,0.000000"
    )


def test_render_trend_positive_deltas(tmp_path):
    first = write_aggregate(
        tmp_path / "a.json", [("p0", [(0.5, 50.0, "fail")])]
    )
    second = write_aggregate(
        tmp_path / "b.json", [("p0", [(0.6, 51.0, "pass")])]
    )
    text = render_trend([str(first), str(second)])
    assert text == (
        "TREND=2,1,0,0.100000,1.000000,pass\n"
        "WORST=1,0,0,0.100000,1.000000"
    )


def test_render_trend_calls_trend_once(monkeypatch, snapshot_paths):
    calls = []
    original = crosspoint_mod.trend

    def counting(paths):
        calls.append(list(paths))
        return original(paths)

    monkeypatch.setattr(crosspoint_mod, "trend", counting)
    paths = list(snapshot_paths)
    render_trend(paths)
    assert calls == [paths]


def test_render_trend_validation_passthrough():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        render_trend({})
    with pytest.raises(ValueError, match="at least 2 items"):
        render_trend(["only"])
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        render_trend(["a", 5])


def test_render_trend_does_not_modify_inputs_or_files(snapshot_paths):
    paths = list(snapshot_paths)
    before = [open(p, "rb").read() for p in paths]
    render_trend(paths)
    assert paths == snapshot_paths
    assert [open(p, "rb").read() for p in paths] == before


def test_trend_render_serialize_exported():
    assert hasattr(crosspoint_mod, "serialize_trend")
    assert hasattr(crosspoint_mod, "render_trend")
    assert "serialize_trend" in crosspoint_mod.__all__
    assert "render_trend" in crosspoint_mod.__all__


def _write_bytes(tmp_path, data, name="trend.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


@pytest.fixture
def trend_bytes(snapshot_paths):
    return serialize_trend(list(snapshot_paths))


@pytest.fixture
def pass_trend_bytes(tmp_path):
    batches = [("p0", [(0.5, 50.0, "pass")])]
    first = write_aggregate(tmp_path / "a.json", batches)
    second = write_aggregate(tmp_path / "b.json", batches)
    return serialize_trend([str(first), str(second)])


def test_load_trend_exported():
    assert hasattr(crosspoint_mod, "load_trend")
    assert "load_trend" in crosspoint_mod.__all__
    assert crosspoint_mod.load_trend is load_trend


def test_load_trend_roundtrip(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    result = load_trend(_write_bytes(tmp_path, trend_bytes))

    assert isinstance(result, dict)
    assert list(result.keys()) == EXPECTED_KEYS
    assert result["count"] == document["count"] == 3
    assert result["changes"] == document["changes"] == 6
    assert result["degraded"] == document["degraded"] == 3
    assert result["coverage_delta"] == document["coverage_delta"] == -0.008333
    assert result["score_delta"] == document["score_delta"] == 0.0
    assert math.copysign(1.0, result["score_delta"]) == 1.0
    assert result["worst"] == tuple(document["worst"]) == (2, 1, 0, -0.05, -1.0)
    assert isinstance(result["worst"], tuple)
    assert result["quality"] == "fail"

    assert type(result["count"]) is int
    assert type(result["changes"]) is int
    assert type(result["degraded"]) is int
    for key in ("coverage_delta", "score_delta"):
        assert type(result[key]) is float
    assert all(type(v) is int for v in result["worst"][:3])
    assert all(type(v) is float for v in result["worst"][3:])


def test_load_trend_matches_trend(tmp_path, snapshot_paths, trend_bytes):
    path = _write_bytes(tmp_path, trend_bytes)
    assert load_trend(path) == trend(list(snapshot_paths))


def test_load_trend_pass_roundtrip(tmp_path, pass_trend_bytes):
    result = load_trend(_write_bytes(tmp_path, pass_trend_bytes))
    assert result == {
        "count": 2,
        "changes": 1,
        "degraded": 0,
        "coverage_delta": 0.0,
        "score_delta": 0.0,
        "worst": (1, 0, 0, 0.0, 0.0),
        "quality": "pass",
    }
    for value in (result["coverage_delta"], result["score_delta"], *result["worst"][3:]):
        assert math.copysign(1.0, value) == 1.0


def test_load_trend_does_not_modify_file(tmp_path, trend_bytes):
    path = _write_bytes(tmp_path, trend_bytes)
    load_trend(path)
    with open(path, "rb") as handle:
        assert handle.read() == trend_bytes


def test_load_trend_path_type_error():
    with pytest.raises(TypeError):
        load_trend(42)
    with pytest.raises(TypeError):
        load_trend(None)
    with pytest.raises(TypeError):
        load_trend(b"trend.json")


def test_load_trend_path_empty_value_error():
    with pytest.raises(ValueError):
        load_trend("")


def test_load_trend_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trend(str(tmp_path / "missing.json"))


def test_load_trend_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_trend(str(tmp_path))


def test_load_trend_bom_rejected(tmp_path, trend_bytes):
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, b"\xef\xbb\xbf" + trend_bytes))


def test_load_trend_trailing_newline_rejected(tmp_path, trend_bytes):
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, trend_bytes + b"\n"))


def test_load_trend_invalid_utf8(tmp_path, trend_bytes):
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, trend_bytes[:-2] + b"\xff\xfe"))


def test_load_trend_invalid_json(tmp_path):
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, b"{"))


def test_load_trend_non_object_json(tmp_path):
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, b"[1,2,3]"))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, b"42"))


def test_load_trend_nan_infinity_rejected(tmp_path, trend_bytes):
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                trend_bytes.replace(b'"coverage_delta":-0.008333', b'"coverage_delta":NaN', 1),
            )
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                trend_bytes.replace(b'"coverage_delta":-0.008333', b'"coverage_delta":Infinity', 1),
            )
        )


def test_load_trend_duplicate_key_rejected(tmp_path, trend_bytes):
    duplicated = trend_bytes.replace(b'"count":3', b'"count":2,"count":3', 1)
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, duplicated))


def test_load_trend_key_order_rejected(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    keys = list(document)
    reordered = {key: document[key] for key in keys[1:] + keys[:1]}
    data = json.dumps(reordered, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, data))


def test_load_trend_missing_and_extra_keys(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)

    def encode(value):
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    missing = {key: document[key] for key in document if key != "quality"}
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, encode(missing)))
    extra = dict(document)
    extra["extra"] = 1
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, encode(extra)))


def _mutated_trend(document, **changes):
    value = dict(document)
    value.update(changes)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_load_trend_count_type_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, count=True)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, count=3.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, count="3")))


def test_load_trend_count_range_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, count=1)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, count=0)))


def test_load_trend_changes_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, changes=True)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, changes=6.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, changes=0)))


def test_load_trend_degraded_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, degraded=True)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, degraded=3.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, degraded=-1)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, degraded=7)))


def test_load_trend_delta_type_range_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, coverage_delta=0))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, coverage_delta="0.0"))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, coverage_delta=1.5))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, coverage_delta=-1.5))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, score_delta=0))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, score_delta=100.5))
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, score_delta=-100.5))
        )


def test_load_trend_delta_precision_and_negative_zero(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                _mutated_trend(document, coverage_delta=-0.0083334),
            )
        )
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, score_delta=-0.0))
        )


def test_load_trend_worst_container_and_length(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)
    broken = dict(document)
    broken["worst"] = [2, 1, 0, -0.05]
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )
    broken["worst"] = {"i": 2}
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_trend_worst_int_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)

    def worst_with(index, value):
        broken = dict(document)
        worst = list(document["worst"])
        worst[index] = value
        broken["worst"] = worst
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(0, True)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(0, 2.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(0, 0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(0, 3)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(1, -1)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(1, 1.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(2, -1)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(2, True)))


def test_load_trend_worst_float_errors(tmp_path, trend_bytes):
    document = json.loads(trend_bytes)

    def worst_with(index, value):
        broken = dict(document)
        worst = list(document["worst"])
        worst[index] = value
        broken["worst"] = worst
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, 0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, "-0.05")))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, 1.5)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, -1.5)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, -0.0500001)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(3, -0.0)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(4, -1)))
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, worst_with(4, 100.5)))


def test_load_trend_quality_relation(tmp_path, trend_bytes, pass_trend_bytes):
    document = json.loads(trend_bytes)
    # degraded == 3 must pair with "fail".
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, quality="pass")))
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(tmp_path, _mutated_trend(document, quality="maybe"))
        )
    with pytest.raises(ValueError):
        load_trend(_write_bytes(tmp_path, _mutated_trend(document, quality=True)))

    pass_document = json.loads(pass_trend_bytes)
    # degraded == 0 must pair with "pass".
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path, _mutated_trend(pass_document, quality="fail")
            )
        )
    degraded = dict(pass_document)
    degraded["degraded"] = 1
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path,
                json.dumps(degraded, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_trend_noncanonical_bytes_rejected(tmp_path, trend_bytes):
    # pretty-printed / spaced encoder
    document = json.loads(trend_bytes)
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path, json.dumps(document, indent=2).encode("utf-8")
            )
        )
    # non-canonical float representation
    with pytest.raises(ValueError):
        load_trend(
            _write_bytes(
                tmp_path, trend_bytes.replace(b"-0.05", b"-0.050", 1)
            )
        )
