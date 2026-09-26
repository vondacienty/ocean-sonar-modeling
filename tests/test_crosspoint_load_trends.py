"""Tests for crosspoint.load_trends."""

import json
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    aggregate_trends,
    dump_trends,
    load_trend,
    load_trends,
    serialize_trend,
)


def _q6(value):
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def make_quality_batch(records):
    rows = [
        {
            "index": i,
            "coverage": _q6(coverage),
            "score": _q6(score),
            "quality": quality,
        }
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
    "file_count",
    "changes",
    "degraded",
    "coverage_delta",
    "score_delta",
    "worst",
    "quality",
]


@pytest.fixture
def trend_file_sets(tmp_path):
    # Two trend files, each built from two snapshots of one batch.
    sets = []
    for k, records_pair in enumerate(
        (
            ([(0.8, 80.0, "pass")], [(0.9, 82.0, "pass")]),
            ([(0.5, 50.0, "pass")], [(0.4, 49.0, "fail")]),
        )
    ):
        paths = []
        for s, records in enumerate(records_pair):
            path = write_aggregate(
                tmp_path / f"ag_{k}_{s}.json", [("p0", records)]
            )
            paths.append(str(path))
        trend_path = tmp_path / f"trend_{k}.json"
        trend_path.write_bytes(serialize_trend(paths))
        sets.append(str(trend_path))
    return sets


def _write_bytes(tmp_path, data, name="trends.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


@pytest.fixture
def trends_bytes(trend_file_sets):
    return dump_trends(list(trend_file_sets))


@pytest.fixture
def pass_trends_bytes(tmp_path):
    batches = [("p0", [(0.5, 50.0, "pass")])]
    snapshot_paths = []
    for s in range(2):
        snapshot_paths.append(
            str(write_aggregate(tmp_path / f"pass_ag_{s}.json", batches))
        )
    trend_paths = []
    for k in range(2):
        trend_path = tmp_path / f"pass_trend_{k}.json"
        trend_path.write_bytes(serialize_trend(snapshot_paths))
        trend_paths.append(str(trend_path))
    return dump_trends(trend_paths)


def test_load_trends_exported():
    assert hasattr(crosspoint_mod, "load_trends")
    assert "load_trends" in crosspoint_mod.__all__
    assert crosspoint_mod.load_trends is load_trends
    # Sibling APIs remain exported and untouched.
    assert "dump_trends" in crosspoint_mod.__all__
    assert "load_trend" in crosspoint_mod.__all__


def test_load_trends_roundtrip(tmp_path, trend_file_sets, trends_bytes):
    document = json.loads(trends_bytes)
    result = load_trends(_write_bytes(tmp_path, trends_bytes))

    assert isinstance(result, dict)
    assert list(result.keys()) == EXPECTED_KEYS
    assert result["file_count"] == document["file_count"] == 2
    assert result["changes"] == document["changes"] == 2
    assert result["degraded"] == document["degraded"] == 1
    # dc: +0.1 (file 0), -0.1 (file 1) -> mean 0.0
    assert result["coverage_delta"] == document["coverage_delta"] == 0.0
    # ds: +2, -1 -> mean 0.5
    assert result["score_delta"] == document["score_delta"] == 0.5
    # Worst minimizes (ds, dc, j, i, b, r): file 1 with ds -1.
    assert result["worst"] == tuple(document["worst"]) == (
        1,
        1,
        0,
        0,
        -0.1,
        -1.0,
    )
    assert isinstance(result["worst"], tuple)
    assert result["quality"] == "fail"

    assert type(result["file_count"]) is int
    assert type(result["changes"]) is int
    assert type(result["degraded"]) is int
    for key in ("coverage_delta", "score_delta"):
        assert type(result[key]) is float
    assert all(type(v) is int for v in result["worst"][:4])
    assert all(type(v) is float for v in result["worst"][4:])


def test_load_trends_matches_aggregate(tmp_path, trend_file_sets, trends_bytes):
    path = _write_bytes(tmp_path, trends_bytes)
    assert load_trends(path) == aggregate_trends(list(trend_file_sets))


def test_load_trends_pass_roundtrip(tmp_path, pass_trends_bytes):
    result = load_trends(_write_bytes(tmp_path, pass_trends_bytes))
    assert result == {
        "file_count": 2,
        "changes": 2,
        "degraded": 0,
        "coverage_delta": 0.0,
        "score_delta": 0.0,
        "worst": (0, 1, 0, 0, 0.0, 0.0),
        "quality": "pass",
    }
    for value in (
        result["coverage_delta"],
        result["score_delta"],
        *result["worst"][4:],
    ):
        assert math.copysign(1.0, value) == 1.0


def test_load_trends_does_not_modify_file(tmp_path, trends_bytes):
    path = _write_bytes(tmp_path, trends_bytes)
    load_trends(path)
    with open(path, "rb") as handle:
        assert handle.read() == trends_bytes


def test_load_trends_path_type_error():
    with pytest.raises(TypeError):
        load_trends(42)
    with pytest.raises(TypeError):
        load_trends(None)
    with pytest.raises(TypeError):
        load_trends(b"trends.json")


def test_load_trends_path_empty_value_error():
    with pytest.raises(ValueError):
        load_trends("")


def test_load_trends_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trends(str(tmp_path / "missing.json"))


def test_load_trends_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_trends(str(tmp_path))


def test_load_trends_bom_rejected(tmp_path, trends_bytes):
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, b"\xef\xbb\xbf" + trends_bytes))


def test_load_trends_trailing_newline_rejected(tmp_path, trends_bytes):
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, trends_bytes + b"\n"))


def test_load_trends_invalid_utf8(tmp_path, trends_bytes):
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, trends_bytes[:-2] + b"\xff\xfe"))


def test_load_trends_invalid_json(tmp_path):
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, b"{"))


def test_load_trends_non_object_json(tmp_path):
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, b"[1,2,3]"))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, b"42"))


def test_load_trends_nan_infinity_rejected(tmp_path, trends_bytes):
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path,
                trends_bytes.replace(b'"coverage_delta":0.0', b'"coverage_delta":NaN', 1),
            )
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path,
                trends_bytes.replace(
                    b'"coverage_delta":0.0', b'"coverage_delta":Infinity', 1
                ),
            )
        )


def test_load_trends_duplicate_key_rejected(tmp_path, trends_bytes):
    duplicated = trends_bytes.replace(
        b'"file_count":2', b'"file_count":1,"file_count":2', 1
    )
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, duplicated))


def test_load_trends_key_order_rejected(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    keys = list(document)
    reordered = {key: document[key] for key in keys[1:] + keys[:1]}
    data = json.dumps(reordered, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, data))


def test_load_trends_missing_and_extra_keys(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)

    def encode(value):
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    missing = {key: document[key] for key in document if key != "quality"}
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, encode(missing)))
    extra = dict(document)
    extra["extra"] = 1
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, encode(extra)))


def _mutated(document, **changes):
    value = dict(document)
    value.update(changes)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_load_trends_file_count_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, file_count=True)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, file_count=2.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, file_count="2")))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, file_count=1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, file_count=0)))


def test_load_trends_changes_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, changes=True)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, changes=2.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, changes=0)))


def test_load_trends_degraded_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, degraded=True)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, degraded=1.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, degraded=-1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, degraded=3)))


def test_load_trends_delta_type_range_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, coverage_delta=0))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, coverage_delta="0.0"))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, coverage_delta=1.5))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, coverage_delta=-1.5))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, score_delta=0))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, score_delta=100.5))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, score_delta=-100.5))
        )


def test_load_trends_delta_precision_and_negative_zero(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    # score_delta is 0.5 exactly; perturb its precision.
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, score_delta=0.5000001))
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(document, coverage_delta=-0.0))
        )


def test_load_trends_worst_container_and_length(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    broken = dict(document)
    broken["worst"] = [1, 1, 0, 0, -0.1]
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )
    broken["worst"] = {"j": 1}
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_trends_worst_int_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)

    def worst_with(index, value):
        broken = dict(document)
        worst = list(document["worst"])
        worst[index] = value
        broken["worst"] = worst
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    # j: in [0, file_count=2)
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(0, True)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(0, 2.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(0, -1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(0, 2)))
    # i: >= 1
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(1, 0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(1, 1.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(1, True)))
    # b, r: >= 0
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(2, -1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(2, 0.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(3, -1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(3, True)))


def test_load_trends_worst_float_errors(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)

    def worst_with(index, value):
        broken = dict(document)
        worst = list(document["worst"])
        worst[index] = value
        broken["worst"] = worst
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, 0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, "-0.1")))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, 1.5)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, -1.5)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, -0.1000001)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(4, -0.0)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(5, -1)))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, worst_with(5, 100.5)))


def test_load_trends_quality_relation(tmp_path, trends_bytes, pass_trends_bytes):
    document = json.loads(trends_bytes)
    # degraded == 1 must pair with "fail".
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, quality="pass")))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, quality="maybe")))
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, _mutated(document, quality=True)))

    pass_document = json.loads(pass_trends_bytes)
    # degraded == 0 must pair with "pass".
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(tmp_path, _mutated(pass_document, quality="fail"))
        )
    degraded = dict(pass_document)
    degraded["degraded"] = 1
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path,
                json.dumps(degraded, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_trends_noncanonical_bytes_rejected(tmp_path, trends_bytes):
    document = json.loads(trends_bytes)
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path, json.dumps(document, indent=2).encode("utf-8")
            )
        )
    with pytest.raises(ValueError):
        load_trends(
            _write_bytes(
                tmp_path, trends_bytes.replace(b"-0.1", b"-0.10", 1)
            )
        )


def test_load_trends_rejects_single_trend_document(tmp_path, trend_file_sets):
    # A serialize_trend document uses "count" and a five-item worst.
    data = serialize_trend(
        [
            str(write_aggregate(tmp_path / "x_a.json", [("p0", [(0.5, 50.0, "pass")])])),
            str(write_aggregate(tmp_path / "x_b.json", [("p0", [(0.6, 51.0, "pass")])])),
        ]
    )
    with pytest.raises(ValueError):
        load_trends(_write_bytes(tmp_path, data))


def test_load_trends_file_unused_helpers_still_load(tmp_path, trend_file_sets):
    # Each input trend file remains independently loadable via load_trend.
    for path in trend_file_sets:
        assert isinstance(load_trend(path), dict)
