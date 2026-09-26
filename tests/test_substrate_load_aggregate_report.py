"""Tests for substrate.load_aggregate_report."""

import json

import pytest

from ocean_sonar import substrate as substrate_mod
from ocean_sonar.substrate import (
    batch,
    dump_aggregate,
    load_aggregate_report,
    serialize_aggregate_report,
)

TOP_KEYS = ["schema_version", "source", "summary", "worst", "quality"]
SOURCE_KEYS = ["path", "kind"]
SUMMARY_KEYS = [
    "batch_count",
    "result_count",
    "unknown",
    "counts",
    "unknown_ratio",
    "worst_batch_index",
    "quality",
]
COUNT_KEYS = ["unknown", "mud", "sand", "gravel", "rock"]
WORST_KEYS = ["index", "count", "unknown", "quality"]

ANALYSIS_1 = [(3.0, 0.5), (6.0, 0.5), (None, None)]
INTENSITIES_1 = [0.4, 0.6, 0.7]
ANALYSIS_2 = [(1.0, 0.0), (2.0, 2.0)]
INTENSITIES_2 = [0.2, 0.9]


def write_batch(path, analysis, intensities):
    path.write_bytes(batch(analysis, intensities))
    return str(path)


def make_aggregate_file(tmp_path, name="aggregate.json"):
    first = write_batch(tmp_path / "b1.json", ANALYSIS_1, INTENSITIES_1)
    second = write_batch(tmp_path / "b2.json", ANALYSIS_2, INTENSITIES_2)
    aggregate_path = tmp_path / name
    aggregate_path.write_bytes(dump_aggregate([first, second]))
    return str(aggregate_path)


def valid_report(source_path="aggregate.json"):
    """A canonical passing aggregate report value (unknown == 0)."""
    return {
        "schema_version": 1,
        "source": {"path": source_path, "kind": "substrate_aggregate"},
        "summary": {
            "batch_count": 2,
            "result_count": 3,
            "unknown": 0,
            "counts": {"unknown": 0, "mud": 1, "sand": 0, "gravel": 0, "rock": 2},
            "unknown_ratio": 0.0,
            "worst_batch_index": 0,
            "quality": "pass",
        },
        "worst": {"index": 0, "count": 2, "unknown": 0, "quality": "pass"},
        "quality": "pass",
    }


def failing_report(source_path="aggregate.json"):
    """A canonical failing aggregate report value (unknown == 1)."""
    return {
        "schema_version": 1,
        "source": {"path": source_path, "kind": "substrate_aggregate"},
        "summary": {
            "batch_count": 2,
            "result_count": 5,
            "unknown": 1,
            "counts": {"unknown": 1, "mud": 2, "sand": 0, "gravel": 0, "rock": 2},
            "unknown_ratio": 0.2,
            "worst_batch_index": 0,
            "quality": "fail",
        },
        "worst": {"index": 0, "count": 3, "unknown": 1, "quality": "fail"},
        "quality": "fail",
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


# ---------------------------------------------------------------------------
# round trip with the real producer
# ---------------------------------------------------------------------------


def test_round_trip_fail(tmp_path):
    aggregate_path = make_aggregate_file(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_bytes(serialize_aggregate_report(aggregate_path))

    result = load_aggregate_report(str(report_path))

    assert list(result.keys()) == TOP_KEYS
    assert type(result["schema_version"]) is int
    assert result["schema_version"] == 1
    assert list(result["source"].keys()) == SOURCE_KEYS
    assert result["source"] == {
        "path": aggregate_path,
        "kind": "substrate_aggregate",
    }
    assert list(result["summary"].keys()) == SUMMARY_KEYS
    assert result["summary"] == {
        "batch_count": 2,
        "result_count": 5,
        "unknown": 1,
        "counts": {"unknown": 1, "mud": 2, "sand": 0, "gravel": 0, "rock": 2},
        "unknown_ratio": 0.2,
        "worst_batch_index": 0,
        "quality": "fail",
    }
    assert list(result["summary"]["counts"].keys()) == COUNT_KEYS
    assert list(result["worst"].keys()) == WORST_KEYS
    assert result["worst"] == {"index": 0, "count": 3, "unknown": 1, "quality": "fail"}
    assert result["quality"] == "fail"
    # types
    for name in ("batch_count", "result_count", "unknown", "worst_batch_index"):
        assert type(result["summary"][name]) is int
    assert type(result["summary"]["unknown_ratio"]) is float
    for name in ("index", "count", "unknown"):
        assert type(result["worst"][name]) is int
    assert type(result["worst"]["quality"]) is str


def test_round_trip_pass(tmp_path):
    first = write_batch(tmp_path / "b1.json", [(1.0, 0.0)], [0.2])
    second = write_batch(tmp_path / "b2.json", [(2.0, 2.0)], [0.9])
    aggregate_path = tmp_path / "aggregate.json"
    aggregate_path.write_bytes(dump_aggregate([first, second]))
    report_path = tmp_path / "report.json"
    report_path.write_bytes(serialize_aggregate_report(str(aggregate_path)))

    result = load_aggregate_report(str(report_path))

    assert result["summary"]["unknown"] == 0
    assert result["summary"]["unknown_ratio"] == 0.0
    assert result["summary"]["quality"] == "pass"
    assert result["worst"]["unknown"] == 0
    assert result["worst"]["quality"] == "pass"
    assert result["quality"] == "pass"
    assert result["worst"]["index"] == result["summary"]["worst_batch_index"]


def test_round_trip_bytes_exact(tmp_path):
    aggregate_path = make_aggregate_file(tmp_path)
    data = serialize_aggregate_report(aggregate_path)
    report_path = tmp_path / "report.json"
    report_path.write_bytes(data)
    # Loading must not require the aggregate file to still exist; the
    # report is self-describing.
    assert load_aggregate_report(str(report_path))["source"]["path"] == aggregate_path


def test_in___all__():
    assert "load_aggregate_report" in substrate_mod.__all__


# ---------------------------------------------------------------------------
# path validation and system errors
# ---------------------------------------------------------------------------


def test_path_non_str_typeerror():
    with pytest.raises(TypeError, match="path must be a str"):
        load_aggregate_report(123)


def test_path_empty_valueerror():
    with pytest.raises(ValueError, match="path must not be empty"):
        load_aggregate_report("")


def test_missing_file_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_aggregate_report(str(tmp_path / "missing.json"))


def test_directory_isadirectoryerror(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_aggregate_report(str(tmp_path))


def test_file_not_modified(tmp_path):
    report_path = tmp_path / "report.json"
    p = write_report(report_path, failing_report())
    before = bytes(report_path.read_bytes())
    load_aggregate_report(p)
    assert report_path.read_bytes() == before


# ---------------------------------------------------------------------------
# byte / encoding rejection
# ---------------------------------------------------------------------------


def test_bom_rejected(tmp_path):
    p = write_report(tmp_path / "r.json", None, raw=b"\xef\xbb\xbf" + dump_document(valid_report()))
    with pytest.raises(ValueError, match="BOM"):
        load_aggregate_report(p)


def test_trailing_newline_rejected(tmp_path):
    p = write_report(
        tmp_path / "r.json", None, raw=dump_document(valid_report()) + b"\n"
    )
    with pytest.raises(ValueError, match="trailing newline"):
        load_aggregate_report(p)


def test_invalid_utf8_rejected(tmp_path):
    p = write_report(tmp_path / "r.json", None, raw=b"\xff\xfe\x00not json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_aggregate_report(p)


def test_invalid_json_rejected(tmp_path):
    p = write_report(tmp_path / "r.json", None, raw=b"{not json")
    with pytest.raises(ValueError, match="valid JSON"):
        load_aggregate_report(p)


def test_nan_constant_rejected(tmp_path):
    document = failing_report()
    document["summary"]["unknown_ratio"] = float("nan")
    p = write_report(tmp_path / "r.json", document, allow_nan=True)
    with pytest.raises(ValueError):
        load_aggregate_report(p)


def test_infinity_constant_rejected(tmp_path):
    document = failing_report()
    document["summary"]["unknown_ratio"] = float("inf")
    p = write_report(tmp_path / "r.json", document, allow_nan=True)
    with pytest.raises(ValueError):
        load_aggregate_report(p)


def test_duplicate_keys_rejected(tmp_path):
    raw = (
        b'{"schema_version":1,"schema_version":1,'
        b'"source":{"path":"a.json","kind":"substrate_aggregate"},'
        b'"summary":{"batch_count":2,"result_count":3,"unknown":0,'
        b'"counts":{"unknown":0,"mud":1,"sand":0,"gravel":0,"rock":2},'
        b'"unknown_ratio":0.0,"worst_batch_index":0,"quality":"pass"},'
        b'"worst":{"index":0,"count":2,"unknown":0,"quality":"pass"},'
        b'"quality":"pass"}'
    )
    p = write_report(tmp_path / "r.json", None, raw=raw)
    with pytest.raises(ValueError):
        load_aggregate_report(p)


def test_pretty_printed_bytes_rejected(tmp_path):
    p = write_report(tmp_path / "r.json", valid_report(), indent=2)
    with pytest.raises(ValueError, match="canonical"):
        load_aggregate_report(p)


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------


def test_top_level_not_object(tmp_path):
    p = write_report(tmp_path / "r.json", None, raw=b"[1,2,3]")
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_top_level_wrong_key_order(tmp_path):
    document = valid_report()
    reordered = {key: document[key] for key in reversed(TOP_KEYS)}
    p = write_report(tmp_path / "r.json", reordered)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_top_level_missing_key(tmp_path):
    document = valid_report()
    del document["quality"]
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_top_level_extra_key(tmp_path):
    document = valid_report()
    document["extra"] = 1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_schema_version_bool_rejected(tmp_path):
    document = valid_report()
    document["schema_version"] = True
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_schema_version_float_rejected(tmp_path):
    document = valid_report()
    document["schema_version"] = 1.0
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_schema_version_wrong_int(tmp_path):
    document = valid_report()
    document["schema_version"] = 2
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------


def test_source_wrong_key_order(tmp_path):
    document = valid_report()
    document["source"] = {"kind": "substrate_aggregate", "path": "a.json"}
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_source_empty_path(tmp_path):
    document = valid_report()
    document["source"]["path"] = ""
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_source_path_non_str(tmp_path):
    document = valid_report()
    document["source"]["path"] = 7
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_source_wrong_kind(tmp_path):
    document = valid_report()
    document["source"]["kind"] = "aggregate"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary_wrong_key_order(tmp_path):
    document = valid_report()
    summary = document["summary"]
    document["summary"] = {key: summary[key] for key in reversed(SUMMARY_KEYS)}
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_batch_count_below_two(tmp_path):
    document = valid_report()
    document["summary"]["batch_count"] = 1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_result_count_below_batch_count(tmp_path):
    document = valid_report()
    document["summary"]["result_count"] = 1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_unknown_out_of_range(tmp_path):
    document = failing_report()
    document["summary"]["unknown"] = 6
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_unknown_negative(tmp_path):
    document = failing_report()
    document["summary"]["unknown"] = -1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_bool_int_rejected(tmp_path):
    document = valid_report()
    document["summary"]["batch_count"] = True
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_counts_wrong_key_order(tmp_path):
    document = valid_report()
    counts = document["summary"]["counts"]
    document["summary"]["counts"] = {key: counts[key] for key in reversed(COUNT_KEYS)}
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_counts_unknown_mismatch(tmp_path):
    document = failing_report()
    document["summary"]["counts"]["unknown"] = 0
    document["summary"]["counts"]["mud"] = 3
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_counts_sum_mismatch(tmp_path):
    document = failing_report()
    document["summary"]["counts"]["mud"] = 3
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_counts_negative_value(tmp_path):
    document = valid_report()
    document["summary"]["counts"]["sand"] = -1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_counts_bool_value_rejected(tmp_path):
    document = valid_report()
    document["summary"]["counts"]["mud"] = True
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_unknown_ratio_wrong_value(tmp_path):
    document = failing_report()
    document["summary"]["unknown_ratio"] = 0.5
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_unknown_ratio_consistent_value_loads(tmp_path):
    # unknown=1, result_count=7 -> round(1/7, 6)
    document = failing_report()
    document["summary"]["result_count"] = 7
    document["summary"]["counts"] = {
        "unknown": 1, "mud": 6, "sand": 0, "gravel": 0, "rock": 0
    }
    document["summary"]["unknown_ratio"] = round(1 / 7, 6)
    p = write_report(tmp_path / "r.json", document)
    assert load_aggregate_report(p)["summary"]["unknown_ratio"] == round(1 / 7, 6)


def test_unknown_ratio_not_six_rounded(tmp_path):
    document = valid_report()
    # Build an unknown=1/7 shape and store the unrounded fraction.
    document["summary"]["quality"] = "fail"
    document["summary"]["unknown"] = 1
    document["summary"]["result_count"] = 7
    document["summary"]["counts"] = {
        "unknown": 1, "mud": 6, "sand": 0, "gravel": 0, "rock": 0
    }
    document["summary"]["unknown_ratio"] = 1 / 7
    document["worst"] = {"index": 0, "count": 4, "unknown": 1, "quality": "fail"}
    document["quality"] = "fail"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_unknown_ratio_int_rejected(tmp_path):
    document = valid_report()
    document["summary"]["unknown_ratio"] = 0
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_unknown_ratio_negative_zero_rejected(tmp_path):
    text = dump_document(valid_report()).decode("utf-8")
    text = text.replace('"unknown_ratio":0.0', '"unknown_ratio":-0.0')
    p = write_report(tmp_path / "r.json", None, raw=text.encode("utf-8"))
    with pytest.raises(ValueError):
        load_aggregate_report(p)


def test_worst_batch_index_out_of_range(tmp_path):
    document = valid_report()
    document["summary"]["worst_batch_index"] = 2
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_batch_index_negative(tmp_path):
    document = valid_report()
    document["summary"]["worst_batch_index"] = -1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_quality_pass_with_unknown(tmp_path):
    document = failing_report()
    document["summary"]["quality"] = "pass"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_quality_fail_without_unknown(tmp_path):
    document = valid_report()
    document["summary"]["quality"] = "fail"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_summary_quality_bad_string(tmp_path):
    document = valid_report()
    document["summary"]["quality"] = "ok"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


# ---------------------------------------------------------------------------
# worst
# ---------------------------------------------------------------------------


def test_worst_wrong_key_order(tmp_path):
    document = valid_report()
    worst = document["worst"]
    document["worst"] = {key: worst[key] for key in reversed(WORST_KEYS)}
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_index_mismatch(tmp_path):
    document = failing_report()
    document["worst"]["index"] = 1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_index_bool_rejected(tmp_path):
    document = valid_report()
    document["worst"]["index"] = False
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_count_zero(tmp_path):
    document = valid_report()
    document["worst"]["count"] = 0
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_count_negative(tmp_path):
    document = valid_report()
    document["worst"]["count"] = -2
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_unknown_above_count(tmp_path):
    document = failing_report()
    document["worst"]["unknown"] = 4
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_unknown_negative(tmp_path):
    document = valid_report()
    document["worst"]["unknown"] = -1
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_quality_bad_string(tmp_path):
    document = valid_report()
    document["worst"]["quality"] = "ok"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_quality_pass_with_unknown(tmp_path):
    document = failing_report()
    document["worst"]["quality"] = "pass"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_quality_fail_without_unknown(tmp_path):
    document = valid_report()
    document["worst"]["quality"] = "fail"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_worst_partial_unknown_loads(tmp_path):
    # A worst batch with unknown > 0 but unknown < count is valid.
    document = failing_report()
    document["worst"] = {"index": 0, "count": 3, "unknown": 1, "quality": "fail"}
    p = write_report(tmp_path / "r.json", document)
    result = load_aggregate_report(p)
    assert result["worst"]["unknown"] == 1


# ---------------------------------------------------------------------------
# top-level quality
# ---------------------------------------------------------------------------


def test_top_quality_mismatches_summary(tmp_path):
    document = failing_report()
    document["quality"] = "pass"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_top_quality_bad_string(tmp_path):
    document = valid_report()
    document["quality"] = "ok"
    p = write_report(tmp_path / "r.json", document)
    with pytest.raises(ValueError, match="valid aggregate report"):
        load_aggregate_report(p)


def test_failing_report_loads(tmp_path):
    p = write_report(tmp_path / "r.json", failing_report())
    result = load_aggregate_report(p)
    assert result["quality"] == "fail"
    assert result["summary"]["quality"] == "fail"
    assert result["worst"]["quality"] == "fail"
    assert result["summary"]["unknown_ratio"] == 0.2
