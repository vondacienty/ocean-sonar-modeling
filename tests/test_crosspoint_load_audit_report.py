"""Tests for crosspoint.load_audit_report."""

import json
import math

import pytest

from ocean_sonar import crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    load_audit_report,
    serialize_audit,
    serialize_audit_report,
)

TOP_KEYS = ["schema_version", "source", "summary", "worst", "quality"]
SOURCE_KEYS = ["path", "kind"]
SUMMARY_KEYS = ["files", "changes", "failed", "passed", "pass_ratio"]
WORST_KEYS = [
    "file_index",
    "index",
    "degraded_delta",
    "coverage_delta",
    "score_delta",
    "quality",
]


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


def make_audit_file(tmp_path, changes_per_file):
    """Create comparison files and an audit file; return (audit_path, paths)."""
    paths = []
    for i, changes in enumerate(changes_per_file):
        p = tmp_path / f"c{i}.json"
        paths.append(write_comparison(p, changes))
    audit_path = tmp_path / "audit.json"
    audit_path.write_bytes(serialize_audit(paths))
    return str(audit_path), paths


def valid_report(source_path="in-audit.json"):
    """A canonical passing audit report value."""
    changes = 3
    passed = 3
    return {
        "schema_version": 1,
        "source": {"path": source_path, "kind": "audit"},
        "summary": {
            "files": 2,
            "changes": changes,
            "failed": 0,
            "passed": passed,
            "pass_ratio": round(passed / changes, 6),
        },
        "worst": {
            "file_index": 0,
            "index": 1,
            "degraded_delta": 0,
            "coverage_delta": 0.1,
            "score_delta": 1.0,
            "quality": "pass",
        },
        "quality": "pass",
    }


def dump_document(document, *, allow_nan=False, indent=None):
    text = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":") if indent is None else (", ", ": "),
        allow_nan=allow_nan,
        indent=indent,
    )
    return text.encode("utf-8")


def write_report(path, document, *, raw=None, allow_nan=False, indent=None):
    data = raw if raw is not None else dump_document(
        document, allow_nan=allow_nan, indent=indent
    )
    with open(path, "wb") as handle:
        handle.write(data)
    return str(path)


def failing_report():
    changes = 4
    failed = 1
    passed = changes - failed
    return {
        "schema_version": 1,
        "source": {"path": "in-audit.json", "kind": "audit"},
        "summary": {
            "files": 2,
            "changes": changes,
            "failed": failed,
            "passed": passed,
            "pass_ratio": round(passed / changes, 6),
        },
        "worst": {
            "file_index": 1,
            "index": 2,
            "degraded_delta": 1,
            "coverage_delta": -0.25,
            "score_delta": -3.5,
            "quality": "fail",
        },
        "quality": "fail",
    }


# ---------------------------------------------------------------------------
# round trip with the real producer
# ---------------------------------------------------------------------------


def test_round_trip_pass(tmp_path):
    changes = [
        change(1, 0, 0.1, 1.0, "pass"),
        change(2, 0, 0.2, 2.0, "pass"),
    ]
    audit_path, _ = make_audit_file(tmp_path, [changes, changes])
    report_bytes = serialize_audit_report(audit_path)
    report_path = tmp_path / "report.json"
    report_path.write_bytes(report_bytes)

    result = load_audit_report(str(report_path))

    assert list(result.keys()) == TOP_KEYS
    assert type(result["schema_version"]) is int
    assert result["schema_version"] == 1
    assert list(result["source"].keys()) == SOURCE_KEYS
    assert result["source"] == {"path": audit_path, "kind": "audit"}
    assert list(result["summary"].keys()) == SUMMARY_KEYS
    assert result["summary"] == {
        "files": 2,
        "changes": 4,
        "failed": 0,
        "passed": 4,
        "pass_ratio": 1.0,
    }
    assert list(result["worst"].keys()) == WORST_KEYS
    assert result["worst"]["quality"] == "pass"
    assert result["quality"] == "pass"
    # types
    for name in ("files", "changes", "failed", "passed"):
        assert type(result["summary"][name]) is int
    assert type(result["summary"]["pass_ratio"]) is float
    for name in ("file_index", "index", "degraded_delta"):
        assert type(result["worst"][name]) is int
    for name in ("coverage_delta", "score_delta"):
        assert type(result["worst"][name]) is float


def test_round_trip_fail_and_pass_ratio_rounding(tmp_path):
    c0 = [
        change(1, 1, -0.25, -3.5, "fail"),
        change(2, 0, 0.2, 2.0, "pass"),
    ]
    c1 = [change(1, 0, 0.1, 1.0, "pass")]
    audit_path, _ = make_audit_file(tmp_path, [c0, c1])
    report_path = tmp_path / "report.json"
    report_path.write_bytes(serialize_audit_report(audit_path))

    result = load_audit_report(str(report_path))

    summary = result["summary"]
    assert summary["files"] == 2
    assert summary["changes"] == 3
    assert summary["failed"] == 1
    assert summary["passed"] == 2
    assert summary["pass_ratio"] == round(2 / 3, 6)
    assert summary["pass_ratio"] == 0.666667
    assert result["quality"] == "fail"
    assert result["worst"]["quality"] == "fail"


def test_in___all__():
    assert "load_audit_report" in crosspoint_mod.__all__


# ---------------------------------------------------------------------------
# path validation and system errors
# ---------------------------------------------------------------------------


def test_path_non_str_typeerror():
    with pytest.raises(TypeError, match="path must be a str"):
        load_audit_report(123)


def test_path_empty_valueerror():
    with pytest.raises(ValueError, match="path must not be empty"):
        load_audit_report("")


def test_missing_file_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_audit_report(str(tmp_path / "missing.json"))


def test_directory_isadirectoryerror(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_audit_report(str(tmp_path))


def test_file_not_modified(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, valid_report())
    before = bytes(report_path.read_bytes())
    load_audit_report(p)
    after = report_path.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# byte / encoding rejection
# ---------------------------------------------------------------------------


def test_bom_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    data = b"\xef\xbb\xbf" + dump_document(valid_report())
    p = write_report(report_path, None, raw=data)
    with pytest.raises(ValueError, match="BOM"):
        load_audit_report(p)


def test_trailing_newline_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    data = dump_document(valid_report()) + b"\n"
    p = write_report(report_path, None, raw=data)
    with pytest.raises(ValueError, match="trailing newline"):
        load_audit_report(p)


def test_invalid_utf8_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, None, raw=b"\xff\xfe\x00not json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_audit_report(p)


def test_invalid_json_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, None, raw=b"{not json")
    with pytest.raises(ValueError, match="valid JSON"):
        load_audit_report(p)


def test_nan_constant_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["pass_ratio"] = float("nan")
    p = write_report(report_path, document, allow_nan=True)
    with pytest.raises(ValueError):
        load_audit_report(p)


def test_infinity_constant_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["score_delta"] = float("inf")
    p = write_report(report_path, document, allow_nan=True)
    with pytest.raises(ValueError):
        load_audit_report(p)


def test_duplicate_keys_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    raw = (
        b'{"schema_version":1,"schema_version":1,'
        b'"source":{"path":"a.json","kind":"audit"},'
        b'"summary":{"files":2,"changes":3,"failed":0,"passed":3,'
        b'"pass_ratio":1.0},'
        b'"worst":{"file_index":0,"index":1,"degraded_delta":0,'
        b'"coverage_delta":0.1,"score_delta":1.0,"quality":"pass"},'
        b'"quality":"pass"}'
    )
    p = write_report(report_path, None, raw=raw)
    with pytest.raises(ValueError):
        load_audit_report(p)


def test_pretty_printed_bytes_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, valid_report(), indent=2)
    with pytest.raises(ValueError, match="canonical"):
        load_audit_report(p)


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------


def test_top_level_not_object(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, None, raw=b"[1,2,3]")
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_top_level_wrong_key_order(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    reordered = {key: document[key] for key in reversed(TOP_KEYS)}
    p = write_report(report_path, reordered)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_top_level_missing_key(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    del document["quality"]
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_top_level_extra_key(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["extra"] = 1
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_schema_version_bool_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["schema_version"] = True
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_schema_version_float_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["schema_version"] = 1.0
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_schema_version_wrong_int(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["schema_version"] = 2
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------


def test_source_wrong_key_order(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["source"] = {"kind": "audit", "path": "a.json"}
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_source_empty_path(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["source"]["path"] = ""
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_source_path_non_str(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["source"]["path"] = 7
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_source_wrong_kind(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["source"]["kind"] = "trend"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary_wrong_key_order(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    summary = document["summary"]
    document["summary"] = {
        key: summary[key]
        for key in reversed(SUMMARY_KEYS)
    }
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_files_below_two(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["files"] = 1
    document["worst"]["file_index"] = 0
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_changes_below_files(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["changes"] = 1
    document["summary"]["passed"] = 1
    document["summary"]["pass_ratio"] = 1.0
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_failed_out_of_range(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["failed"] = 4
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_passed_mismatch(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    document["summary"]["passed"] = 1  # changes-failed = 3
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_bool_int_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["files"] = True
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_pass_ratio_wrong_value(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    # Make 0.5 the genuinely consistent ratio: passed/changes = 2/4.
    document["summary"]["failed"] = 2
    document["summary"]["passed"] = 2
    document["summary"]["pass_ratio"] = 0.5
    p = write_report(report_path, document)
    assert load_audit_report(p)["summary"]["pass_ratio"] == 0.5

    document["summary"]["pass_ratio"] = 0.9
    report_path2 = tmp_path / "report2.json"
    p2 = write_report(report_path2, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p2)


def test_summary_pass_ratio_not_six_rounded(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    # 1/7 is a repeating fraction not equal to its six-decimal rounding.
    document["summary"]["changes"] = 7
    document["summary"]["failed"] = 6
    document["summary"]["passed"] = 1
    document["summary"]["pass_ratio"] = 1 / 7
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_pass_ratio_int_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["summary"]["pass_ratio"] = 1
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_summary_pass_ratio_negative_zero_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    # Every change failed -> ratio is genuinely 0.0, so a -0.0 token
    # passes the equality check and must be rejected for its sign.
    document["summary"]["failed"] = document["summary"]["changes"]
    document["summary"]["passed"] = 0
    document["summary"]["pass_ratio"] = 0.0
    text = dump_document(document).decode("utf-8")
    text = text.replace('"pass_ratio":0.0', '"pass_ratio":-0.0')
    p = write_report(report_path, None, raw=text.encode("utf-8"))
    with pytest.raises(ValueError):
        load_audit_report(p)


# ---------------------------------------------------------------------------
# worst
# ---------------------------------------------------------------------------


def test_worst_wrong_key_order(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    worst = document["worst"]
    document["worst"] = {key: worst[key] for key in reversed(WORST_KEYS)}
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_file_index_out_of_range(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["file_index"] = 2  # files == 2
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_index_below_one(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["index"] = 0
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_degraded_out_of_range(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    document["worst"]["degraded_delta"] = 3
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_coverage_delta_out_of_range(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["coverage_delta"] = 2.5
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_score_delta_out_of_range(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["score_delta"] = -200.5
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_delta_int_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["coverage_delta"] = 0
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_delta_bool_int_field_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["degraded_delta"] = True
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_delta_not_six_rounded(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["coverage_delta"] = 1 / 7
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_coverage_negative_zero_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    text = dump_document(document).decode("utf-8")
    text = text.replace('"coverage_delta":0.1', '"coverage_delta":-0.0')
    p = write_report(report_path, None, raw=text.encode("utf-8"))
    with pytest.raises(ValueError):
        load_audit_report(p)


def test_worst_score_negative_zero_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    text = dump_document(document).decode("utf-8")
    text = text.replace('"score_delta":1.0', '"score_delta":-0.0')
    p = write_report(report_path, None, raw=text.encode("utf-8"))
    with pytest.raises(ValueError):
        load_audit_report(p)


def test_worst_quality_bad_string(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["quality"] = "ok"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


# ---------------------------------------------------------------------------
# quality consistency
# ---------------------------------------------------------------------------


def test_quality_pass_with_failed_nonzero_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = failing_report()
    document["quality"] = "pass"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_quality_fail_with_zero_failed_rejected(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["quality"] = "fail"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_worst_quality_pass_required_when_zero_failed(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["worst"]["quality"] = "fail"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_quality_bad_string(tmp_path):
    report_path = tmp_path / "report.json"
    document = valid_report()
    document["quality"] = "ok"
    p = write_report(report_path, document)
    with pytest.raises(ValueError, match="valid audit report"):
        load_audit_report(p)


def test_failing_report_loads(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, failing_report())
    result = load_audit_report(p)
    assert result["quality"] == "fail"
    assert result["worst"]["quality"] == "fail"
    assert math.isfinite(result["summary"]["pass_ratio"])
