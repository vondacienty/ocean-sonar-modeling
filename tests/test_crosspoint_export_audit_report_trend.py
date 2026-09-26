"""Tests for crosspoint.export_audit_report_trend and
crosspoint.load_audit_report_trend."""

from __future__ import annotations

import json
import os

import pytest

from ocean_sonar import crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    audit_report_trend,
    export_audit_report_trend,
    load_audit_report_trend,
    serialize_audit,
    serialize_audit_report,
)


def write_comparison(path, changes):
    """Write a canonical serialize_comparison-shaped JSON file."""
    quality = "pass" if all(c["quality"] == "pass" for c in changes) else "fail"
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
def report_paths(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json", [change(1, 0, 0.2, 0.5, "pass")]
    )
    p2 = write_comparison(
        tmp_path / "c2.json", [change(1, 1, -0.2, -0.5, "fail")]
    )
    audit0 = tmp_path / "audit0.json"
    audit0.write_bytes(serialize_audit([p0, p1]))
    audit1 = tmp_path / "audit1.json"
    audit1.write_bytes(serialize_audit([p1, p2]))
    r0 = tmp_path / "report0.json"
    r0.write_bytes(serialize_audit_report(str(audit0)))
    r1 = tmp_path / "report1.json"
    r1.write_bytes(serialize_audit_report(str(audit1)))
    return [str(r0), str(r1)]


def test_in___all__():
    assert "export_audit_report_trend" in crosspoint_mod.__all__
    assert "load_audit_report_trend" in crosspoint_mod.__all__


def test_success_writes_bytes_and_returns_them(tmp_path, report_paths):
    output = str(tmp_path / "trend.json")
    result = export_audit_report_trend(report_paths, output)
    expected_trend = audit_report_trend(report_paths)
    document = json.loads(result)
    assert list(document.keys()) == ["sources", "trend"]
    assert document["sources"] == report_paths
    trend = document["trend"]
    assert list(trend.keys()) == [
        "count",
        "changes",
        "regressed",
        "failed_delta",
        "pass_ratio_delta",
        "worst",
        "quality",
    ]
    assert trend["count"] == expected_trend["count"]
    assert trend["changes"] == expected_trend["changes"]
    assert trend["regressed"] == expected_trend["regressed"]
    assert trend["failed_delta"] == expected_trend["failed_delta"]
    assert trend["pass_ratio_delta"] == expected_trend["pass_ratio_delta"]
    assert trend["worst"] == list(expected_trend["worst"])
    assert trend["quality"] == expected_trend["quality"]
    assert isinstance(result, bytes)
    with open(output, "rb") as handle:
        assert handle.read() == result


def test_inputs_not_modified(tmp_path, report_paths):
    before = [open(path, "rb").read() for path in report_paths]
    export_audit_report_trend(report_paths, str(tmp_path / "trend.json"))
    after = [open(path, "rb").read() for path in report_paths]
    assert after == before


def test_calls_audit_report_trend_exactly_once(monkeypatch, tmp_path, report_paths):
    calls = []
    original = crosspoint_mod.audit_report_trend

    def counting(paths):
        calls.append(list(paths))
        return original(paths)

    monkeypatch.setattr(crosspoint_mod, "audit_report_trend", counting)
    output = str(tmp_path / "trend.json")
    export_audit_report_trend(report_paths, output)
    assert calls == [list(report_paths)]


def test_paths_validation_runs_before_output_validation(tmp_path):
    with pytest.raises(TypeError, match="paths must be a list or tuple"):
        export_audit_report_trend(123, 456)
    with pytest.raises(ValueError, match="paths must contain at least 2 items"):
        export_audit_report_trend(["only.json"], 456)


def test_audit_report_trend_exception_propagates_unchanged(monkeypatch, tmp_path):
    def raising(paths):
        raise ValueError("boom")

    monkeypatch.setattr(crosspoint_mod, "audit_report_trend", raising)
    with pytest.raises(ValueError, match="^boom$"):
        export_audit_report_trend(["a.json", "b.json"], str(tmp_path / "o.json"))


def test_output_non_str_typeerror(tmp_path, report_paths):
    with pytest.raises(TypeError, match="output must be a str"):
        export_audit_report_trend(report_paths, 123)


def test_output_empty_valueerror(tmp_path, report_paths):
    with pytest.raises(ValueError, match="output must not be empty"):
        export_audit_report_trend(report_paths, "")


def test_output_same_as_input_valueerror(tmp_path, report_paths):
    with pytest.raises(ValueError, match="same file"):
        export_audit_report_trend(report_paths, report_paths[1])


def test_output_samefile_via_symlink(tmp_path, report_paths):
    link = str(tmp_path / "report-link.json")
    os.symlink(report_paths[0], link)
    paths = [link, report_paths[1]]
    with pytest.raises(ValueError, match="same file"):
        export_audit_report_trend(paths, report_paths[0])


def test_output_samefile_via_hard_link(tmp_path, report_paths):
    hard = str(tmp_path / "report-hard.json")
    os.link(report_paths[0], hard)
    with pytest.raises(ValueError, match="same file"):
        export_audit_report_trend(report_paths, hard)


def test_no_temp_file_left_after_success(tmp_path, report_paths):
    export_audit_report_trend(report_paths, str(tmp_path / "trend.json"))
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_existing_output_unchanged_when_replace_fails(
    monkeypatch, tmp_path, report_paths
):
    output = tmp_path / "trend.json"
    original_bytes = b"do not touch"
    output.write_bytes(original_bytes)

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        export_audit_report_trend(report_paths, str(output))
    assert output.read_bytes() == original_bytes
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_oserror_from_write_propagates(monkeypatch, tmp_path, report_paths):
    def fail_replace(src, dst):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="nope"):
        export_audit_report_trend(
            report_paths, str(tmp_path / "trend.json")
        )


# --- load_audit_report_trend ------------------------------------------------


def test_load_roundtrip(tmp_path, report_paths):
    output = str(tmp_path / "trend.json")
    written = export_audit_report_trend(report_paths, output)
    result = load_audit_report_trend(output)
    assert list(result.keys()) == ["sources", "trend"]
    assert result["sources"] == report_paths
    assert isinstance(result["sources"], list)
    trend = result["trend"]
    assert list(trend.keys()) == [
        "count",
        "changes",
        "regressed",
        "failed_delta",
        "pass_ratio_delta",
        "worst",
        "quality",
    ]
    assert trend == audit_report_trend(report_paths)
    assert isinstance(trend["worst"], tuple)
    assert len(trend["worst"]) == 4
    assert open(output, "rb").read() == written


def test_load_does_not_modify_file(tmp_path, report_paths):
    output = tmp_path / "trend.json"
    output.write_bytes(export_audit_report_trend(report_paths, str(output)))
    before = output.read_bytes()
    load_audit_report_trend(str(output))
    assert output.read_bytes() == before


def test_load_path_non_str_typeerror():
    with pytest.raises(TypeError, match="path must be a str"):
        load_audit_report_trend(123)


def test_load_path_empty_valueerror():
    with pytest.raises(ValueError, match="path must not be empty"):
        load_audit_report_trend("")


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_audit_report_trend(str(tmp_path / "missing.json"))


def test_load_directory_raises_isadirectoryerror(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_audit_report_trend(str(tmp_path))


def test_load_bom_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    bad = tmp_path / "bom.json"
    bad.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    with pytest.raises(ValueError, match="BOM"):
        load_audit_report_trend(str(bad))


def test_load_trailing_newline_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    bad = tmp_path / "nl.json"
    bad.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="trailing newline"):
        load_audit_report_trend(str(bad))


def test_load_invalid_json_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError, match="valid JSON"):
        load_audit_report_trend(str(path))


def test_load_not_an_object_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"[1,2]")
    with pytest.raises(ValueError, match="valid audit report trend"):
        load_audit_report_trend(str(path))


def test_load_wrong_top_level_key_order_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    reordered = {"trend": document["trend"], "sources": document["sources"]}
    bad = tmp_path / "reordered.json"
    bad.write_text(json.dumps(reordered, separators=(",", ":")))
    with pytest.raises(ValueError, match="order sources, trend"):
        load_audit_report_trend(str(bad))


def test_load_extra_top_level_key_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    bad = tmp_path / "extra.json"
    bad.write_bytes(path.read_bytes()[:-1] + b',"x":1}')
    with pytest.raises(ValueError):
        load_audit_report_trend(str(bad))


def test_load_sources_not_a_list_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"sources": "a.json", "trend": {}}, separators=(",", ":"))
    )
    with pytest.raises(ValueError, match="valid audit report trend"):
        load_audit_report_trend(str(path))


def test_load_sources_too_few_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"sources": ["a.json"], "trend": {}}, separators=(",", ":"))
    )
    with pytest.raises(ValueError, match="at least 2 items"):
        load_audit_report_trend(str(path))


def test_load_sources_non_str_item_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {"sources": ["a.json", 2], "trend": {}}, separators=(",", ":")
        )
    )
    with pytest.raises(ValueError, match="must be a str"):
        load_audit_report_trend(str(path))


def test_load_sources_empty_str_item_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {"sources": ["a.json", ""], "trend": {}}, separators=(",", ":")
        )
    )
    with pytest.raises(ValueError, match="must not be empty"):
        load_audit_report_trend(str(path))


def _valid_trend_document(sources):
    return {
        "sources": list(sources),
        "trend": {
            "count": len(sources),
            "changes": len(sources) - 1,
            "regressed": 0,
            "failed_delta": 0,
            "pass_ratio_delta": 0.0,
            "worst": [1, 0, 0.0, "pass"],
            "quality": "pass",
        },
    }


def test_load_count_mismatch_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    document["trend"]["count"] = 3
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(document, separators=(",", ":")))
    with pytest.raises(ValueError, match="count must equal the number of sources"):
        load_audit_report_trend(str(bad))


def test_load_changes_mismatch_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    document["trend"]["changes"] = 5
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(document, separators=(",", ":")))
    with pytest.raises(ValueError, match="changes must equal count - 1"):
        load_audit_report_trend(str(bad))


def test_load_worst_wrong_length_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    document["trend"]["worst"] = [1, 0, 0.0]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(document, separators=(",", ":")))
    with pytest.raises(ValueError, match="must have 4 elements"):
        load_audit_report_trend(str(bad))


def test_load_trend_mismatch_with_recomputed_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    document["trend"]["failed_delta"] = 99
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(document, separators=(",", ":")))
    with pytest.raises(ValueError, match="field for field"):
        load_audit_report_trend(str(bad))


def test_load_audit_report_trend_called_once_with_sources(
    monkeypatch, tmp_path, report_paths
):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    calls = []
    original = crosspoint_mod.audit_report_trend

    def counting(sources):
        calls.append(list(sources))
        return original(sources)

    monkeypatch.setattr(crosspoint_mod, "audit_report_trend", counting)
    result = load_audit_report_trend(str(path))
    assert calls == [report_paths]
    assert result["sources"] == report_paths


def test_load_source_file_error_propagates_unchanged(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    document["sources"][1] = str(tmp_path / "gone.json")
    bad = tmp_path / "stale.json"
    bad.write_text(json.dumps(document, separators=(",", ":")))
    with pytest.raises(FileNotFoundError):
        load_audit_report_trend(str(bad))


def test_load_duplicate_keys_rejected(tmp_path):
    bad = tmp_path / "dup.json"
    bad.write_bytes(
        b'{"sources":["a","b"],"sources":["a","b"],"trend":{}}'
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_audit_report_trend(str(bad))


def test_load_noncanonical_bytes_rejected(tmp_path, report_paths):
    path = tmp_path / "trend.json"
    path.write_bytes(export_audit_report_trend(report_paths, str(path)))
    document = json.loads(path.read_bytes())
    bad = tmp_path / "pretty.json"
    bad.write_text(json.dumps(document, indent=2))
    with pytest.raises(ValueError, match="canonical"):
        load_audit_report_trend(str(bad))
