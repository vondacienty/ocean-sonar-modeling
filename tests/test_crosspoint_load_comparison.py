"""Tests for crosspoint.load_comparison."""

import json
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    compare_reports,
    load_comparison,
    serialize_comparison,
)


def make_summary(degraded, coverage_delta, score_delta, quality):
    """Build a load_trend_report-shaped summary (worst is unused here)."""
    return {
        "file_count": 2,
        "changes": 1,
        "degraded": degraded,
        "coverage_delta": coverage_delta,
        "score_delta": score_delta,
        "worst": (0, 1, 0, 0, 0.0, 0.0),
        "quality": quality,
    }


def make_report(sources, summary):
    return {"sources": list(sources), "summary": summary}


SOURCES = ["a.json", "b.json"]


@pytest.fixture
def report_loader(monkeypatch):
    """Patch load_trend_report to serve queued reports; tracks loaded paths."""
    state = {"loaded": []}

    def install(reports):
        queue = list(reports)

        def fake_load_trend_report(path):
            state["loaded"].append(path)
            return queue.pop(0)

        monkeypatch.setattr(
            crosspoint_mod, "load_trend_report", fake_load_trend_report
        )

    install.loaded = state["loaded"]
    return install


EXPECTED_TOP_KEYS = ["changes", "worst", "quality"]
EXPECTED_CHANGE_KEYS = [
    "index",
    "degraded_delta",
    "coverage_delta",
    "score_delta",
    "quality",
]


@pytest.fixture
def failing_comparison_bytes(report_loader, tmp_path):
    """Canonical bytes of a two-change, failing comparison."""
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(1, 0.1, 1.0, "fail")),
        make_report(SOURCES, make_summary(1, 0.05, 0.5, "fail")),
    ]
    report_loader(reports)
    paths = ["r0.json", "r1.json", "r2.json"]
    return serialize_comparison(paths)


@pytest.fixture
def passing_comparison_bytes(report_loader):
    """Canonical bytes of a one-change, passing comparison."""
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.1, 1.0, "pass")),
    ]
    report_loader(reports)
    return serialize_comparison(["r0.json", "r1.json"])


def _write_bytes(tmp_path, data, name="comparison.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_load_comparison_exported():
    assert hasattr(crosspoint_mod, "load_comparison")
    assert "load_comparison" in crosspoint_mod.__all__
    assert crosspoint_mod.load_comparison is load_comparison
    # Sibling APIs remain exported and untouched.
    assert "serialize_comparison" in crosspoint_mod.__all__
    assert "render_comparison" in crosspoint_mod.__all__


def test_load_comparison_roundtrip(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    result = load_comparison(_write_bytes(tmp_path, failing_comparison_bytes))

    assert isinstance(result, dict)
    assert list(result.keys()) == EXPECTED_TOP_KEYS
    assert isinstance(result["changes"], tuple)
    assert len(result["changes"]) == 2

    first = result["changes"][0]
    assert list(first.keys()) == EXPECTED_CHANGE_KEYS
    assert first == {
        "index": 1,
        "degraded_delta": 1,
        "coverage_delta": 0.1,
        "score_delta": 1.0,
        "quality": "fail",
    }
    assert type(first["index"]) is int
    assert type(first["degraded_delta"]) is int
    assert type(first["coverage_delta"]) is float
    assert type(first["score_delta"]) is float

    second = result["changes"][1]
    assert second == {
        "index": 2,
        "degraded_delta": 0,
        "coverage_delta": -0.05,
        "score_delta": -0.5,
        "quality": "fail",
    }

    # Worst is field-for-field equal to the second change and the same object.
    assert result["worst"] == second
    assert result["worst"] is result["changes"][1]
    assert result["quality"] == "fail"
    assert document["quality"] == "fail"


def test_load_comparison_pass_roundtrip(tmp_path, passing_comparison_bytes):
    result = load_comparison(_write_bytes(tmp_path, passing_comparison_bytes))
    assert result == {
        "changes": (
            {
                "index": 1,
                "degraded_delta": 0,
                "coverage_delta": 0.1,
                "score_delta": 1.0,
                "quality": "pass",
            },
        ),
        "worst": {
            "index": 1,
            "degraded_delta": 0,
            "coverage_delta": 0.1,
            "score_delta": 1.0,
            "quality": "pass",
        },
        "quality": "pass",
    }
    assert result["worst"] is result["changes"][0]


def test_load_comparison_matches_compare_reports(
    tmp_path, report_loader, failing_comparison_bytes
):
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(1, 0.1, 1.0, "fail")),
        make_report(SOURCES, make_summary(1, 0.05, 0.5, "fail")),
    ]
    report_loader(reports)
    expected = compare_reports(["r0.json", "r1.json", "r2.json"])

    loaded = load_comparison(_write_bytes(tmp_path, failing_comparison_bytes))
    assert loaded == expected


def test_load_comparison_does_not_modify_file(tmp_path, failing_comparison_bytes):
    path = _write_bytes(tmp_path, failing_comparison_bytes)
    load_comparison(path)
    with open(path, "rb") as handle:
        assert handle.read() == failing_comparison_bytes


def test_load_comparison_path_type_error():
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_comparison(42)
    with pytest.raises(TypeError):
        load_comparison(None)
    with pytest.raises(TypeError):
        load_comparison(b"comparison.json")


def test_load_comparison_path_empty_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_comparison("")


def test_load_comparison_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_comparison(str(tmp_path / "missing.json"))


def test_load_comparison_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_comparison(str(tmp_path))


def test_load_comparison_bom_rejected(tmp_path, failing_comparison_bytes):
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(tmp_path, b"\xef\xbb\xbf" + failing_comparison_bytes)
        )


def test_load_comparison_trailing_newline_rejected(tmp_path, failing_comparison_bytes):
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, failing_comparison_bytes + b"\n"))


def test_load_comparison_invalid_utf8(tmp_path, failing_comparison_bytes):
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(tmp_path, failing_comparison_bytes[:-2] + b"\xff\xfe")
        )


def test_load_comparison_invalid_json(tmp_path):
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, b"{"))


def test_load_comparison_non_object_json(tmp_path):
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, b"[1,2,3]"))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, b"42"))


def test_load_comparison_nan_infinity_rejected(tmp_path, failing_comparison_bytes):
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                failing_comparison_bytes.replace(
                    b'"coverage_delta":0.1', b'"coverage_delta":NaN', 1
                ),
            )
        )
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                failing_comparison_bytes.replace(
                    b'"score_delta":1', b'"score_delta":Infinity', 1
                ),
            )
        )


def test_load_comparison_duplicate_key_rejected(tmp_path, failing_comparison_bytes):
    duplicated = failing_comparison_bytes.replace(
        b'"quality":"fail"', b'"quality":"fail","quality":"fail"', 1
    )
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, duplicated))


def test_load_comparison_top_key_order_rejected(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    keys = list(document)
    reordered = {key: document[key] for key in keys[1:] + keys[:1]}
    data = json.dumps(reordered, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, data))


def test_load_comparison_missing_and_extra_keys(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def encode(value):
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    missing = {key: document[key] for key in document if key != "quality"}
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, encode(missing)))
    extra = dict(document)
    extra["extra"] = 1
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, encode(extra)))


def _change_document(failing_comparison_bytes, tmp_path, **changes):
    document = json.loads(failing_comparison_bytes)

    def encode(value=None):
        value = document if value is None else value
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    mutated = dict(document)
    mutated.update(changes)
    return _write_bytes(tmp_path, encode(mutated))


def test_load_comparison_changes_container_errors(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    with pytest.raises(ValueError):
        load_comparison(
            _change_document(failing_comparison_bytes, tmp_path, changes={})
        )
    broken = dict(document)
    broken["changes"] = 1
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )
    broken["changes"] = []
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_comparison_change_key_order_rejected(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    item = document["changes"][0]
    keys = list(item)
    reordered = {key: item[key] for key in keys[1:] + keys[:1]}
    broken = dict(document)
    broken["changes"] = [reordered] + document["changes"][1:]
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )


def test_load_comparison_index_errors(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def with_indexes(first, second):
        broken = dict(document)
        items = json.loads(json.dumps(document["changes"]))
        items[0]["index"] = first
        items[1]["index"] = second
        broken["changes"] = items
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes(True, 2)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes(0, 2)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes(2, 3)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes(1, 1)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes("1", 2)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_indexes(1.0, 2)))


def test_load_comparison_degraded_delta_errors(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def with_degraded(value, position=0):
        broken = json.loads(json.dumps(document))
        broken["changes"][position]["degraded_delta"] = value
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_degraded(True)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_degraded(1.0)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_degraded("1")))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_degraded(3)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_degraded(-3)))
    # Boundary values -2 and 2 are accepted.
    assert load_comparison(_write_bytes(tmp_path, with_degraded(-2)))[
        "changes"
    ][0]["degraded_delta"] == -2
    assert load_comparison(_write_bytes(tmp_path, with_degraded(2)))[
        "changes"
    ][0]["degraded_delta"] == 2


def test_load_comparison_delta_type_and_range_errors(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def with_field(field, value, position=0):
        broken = json.loads(json.dumps(document))
        broken["changes"][position][field] = value
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    for field, low, high in (
        ("coverage_delta", -2, 2),
        ("score_delta", -200, 200),
    ):
        with pytest.raises(ValueError):
            load_comparison(_write_bytes(tmp_path, with_field(field, 0)))
        with pytest.raises(ValueError):
            load_comparison(_write_bytes(tmp_path, with_field(field, "0.1")))
        with pytest.raises(ValueError):
            load_comparison(_write_bytes(tmp_path, with_field(field, True)))
        with pytest.raises(ValueError):
            load_comparison(
                _write_bytes(
                    tmp_path,
                    with_field(field, float(high) * 2),
                )
            )
        with pytest.raises(ValueError):
            load_comparison(
                _write_bytes(tmp_path, with_field(field, high + 0.000001))
            )
        with pytest.raises(ValueError):
            load_comparison(
                _write_bytes(tmp_path, with_field(field, low - 0.000001))
            )


def test_load_comparison_delta_precision_and_negative_zero(
    tmp_path, failing_comparison_bytes
):
    document = json.loads(failing_comparison_bytes)

    def with_field(field, value, position=0):
        broken = json.loads(json.dumps(document))
        broken["changes"][position][field] = value
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path, with_field("coverage_delta", 0.1000001)
            )
        )
    # -0.0 parses as negative zero, which is forbidden.
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(tmp_path, with_field("coverage_delta", -0.0))
        )
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(tmp_path, with_field("score_delta", -0.0, 1))
        )


def test_load_comparison_change_quality_errors(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def with_quality(value, position=0):
        broken = json.loads(json.dumps(document))
        broken["changes"][position]["quality"] = value
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_quality("maybe")))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_quality(True)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_quality(1)))


def test_load_comparison_worst_must_match_a_change(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)

    def with_worst(worst):
        broken = json.loads(json.dumps(document))
        broken["worst"] = worst
        return json.dumps(broken, separators=(",", ":")).encode("utf-8")

    # An index not present in changes.
    bogus = json.loads(json.dumps(document["changes"][0]))
    bogus["index"] = 9
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_worst(bogus)))
    # Same index as a change but a differing field.
    almost = json.loads(json.dumps(document["changes"][0]))
    almost["score_delta"] = 1.5
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_worst(almost)))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_worst([1, 2])))
    with pytest.raises(ValueError):
        load_comparison(_write_bytes(tmp_path, with_worst(None)))


def test_load_comparison_top_quality_relation(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    # A failing change set must not be labelled pass.
    broken = json.loads(json.dumps(document))
    broken["quality"] = "pass"
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                json.dumps(broken, separators=(",", ":")).encode("utf-8"),
            )
        )

    passing = json.loads(
        b'{"changes":[{"index":1,"degraded_delta":0,"coverage_delta":0.0,'
        b'"score_delta":0.0,"quality":"pass"}],"worst":{"index":1,'
        b'"degraded_delta":0,"coverage_delta":0.0,"score_delta":0.0,'
        b'"quality":"pass"},"quality":"fail"}'
    )
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path,
                json.dumps(passing, separators=(",", ":")).encode("utf-8"),
                name="passing.json",
            )
        )


def test_load_comparison_noncanonical_bytes_rejected(tmp_path, failing_comparison_bytes):
    document = json.loads(failing_comparison_bytes)
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path, json.dumps(document, indent=2).encode("utf-8")
            )
        )
    # A float rendered with an extra trailing zero is semantically equal
    # but not the canonical compact six-decimal writing.
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(
                tmp_path, failing_comparison_bytes.replace(b"0.1", b"0.10", 1)
            )
        )
    # Trailing whitespace after the closing brace.
    with pytest.raises(ValueError):
        load_comparison(
            _write_bytes(tmp_path, failing_comparison_bytes + b" ")
        )


def test_load_comparison_no_negative_zero_in_result(tmp_path, report_loader):
    # 0.0 - 0.0 would be +0.0; craft a delta that rounds to zero from a
    # tiny positive value instead — canonical writer normalizes it, so the
    # stored form is 0.0 and the loaded float carries a positive sign.
    reports = [
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
        make_report(SOURCES, make_summary(0, 0.0, 0.0, "pass")),
    ]
    report_loader(reports)
    data = serialize_comparison(["r0.json", "r1.json"])
    result = load_comparison(_write_bytes(tmp_path, data))
    for change in result["changes"]:
        assert math.copysign(1.0, change["coverage_delta"]) == 1.0
        assert math.copysign(1.0, change["score_delta"]) == 1.0
