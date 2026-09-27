"""Tests for product.load_overview."""

import json
import math
import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import load_overview, serialize_overview

KEYS = ["product", "substrate", "crosspoint", "summary", "quality"]
SUMMARY_KEYS = ["domain_count", "pass_count", "fail_count", "quality"]


def trend_item(index=1, failed_delta=0, coverage_delta=0.1, quality="pass"):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "coverage_delta": coverage_delta,
        "quality": quality,
    }


def product_section(item=None):
    item = item or trend_item()
    quality = item["quality"]
    passed = 1 if quality == "pass" else 0
    return {
        "trend": {
            "changes": (item,),
            "worst": item,
            "quality": quality,
        },
        "summary": {
            "count": 1,
            "passed": passed,
            "failed": 1 - passed,
            "coverage_delta": item["coverage_delta"],
        },
        "quality": quality,
    }


def substrate_section(quality="pass", *, regressed=None, worst_q=None):
    if regressed is None:
        regressed = 0 if quality == "pass" else 1
    if worst_q is None:
        worst_q = quality
    return {
        "count": 2,
        "changes": 1,
        "regressed": regressed,
        "unknown_delta": 0,
        "unknown_ratio_delta": 0.0,
        "worst": (1, 0, 0.0, worst_q),
        "quality": quality,
    }


def crosspoint_section(quality="pass", *, regressed=None, worst_q=None):
    if regressed is None:
        regressed = 0 if quality == "pass" else 1
    if worst_q is None:
        worst_q = quality
    failed_delta = 1 if quality == "fail" else 0
    return {
        "sources": ["a.json", "b.json"],
        "trend": {
            "count": 2,
            "changes": 1,
            "regressed": regressed,
            "failed_delta": failed_delta,
            "pass_ratio_delta": 0.0,
            "worst": (1, failed_delta, 0.0, worst_q),
            "quality": quality,
        },
    }


def valid_sections(product_q="pass", substrate_q="pass", crosspoint_q="pass"):
    return (
        product_section(trend_item(quality=product_q)),
        substrate_section(substrate_q),
        crosspoint_section(crosspoint_q),
    )


def install_loaders(monkeypatch, sections):
    product_result, substrate_result, crosspoint_result = sections
    monkeypatch.setattr(product_mod, "quality_dashboard", lambda path: product_result)
    monkeypatch.setattr(
        product_mod.substrate,
        "load_aggregate_report_trend",
        lambda path: substrate_result,
    )
    monkeypatch.setattr(
        product_mod.crosspoint,
        "load_audit_report_trend",
        lambda path: crosspoint_result,
    )


def serialize_sections(monkeypatch, sections):
    install_loaders(monkeypatch, sections)
    return serialize_overview("product.json", "substrate.json", "crosspoint.json")


def write_bytes(tmp_path, data, name="overview.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def write_valid(tmp_path, monkeypatch, sections=None, name="overview.json"):
    if sections is None:
        sections = valid_sections()
    data = serialize_sections(monkeypatch, sections)
    return write_bytes(tmp_path, data, name), data


def test_exported():
    assert "load_overview" in product_mod.__all__
    assert product_mod.load_overview is load_overview


def test_roundtrip_key_order(tmp_path, monkeypatch):
    path, data = write_valid(tmp_path, monkeypatch)

    result = load_overview(path)

    assert list(result.keys()) == KEYS
    assert list(result["summary"].keys()) == SUMMARY_KEYS
    assert json.dumps(result, ensure_ascii=False, separators=(",", ":")) is not None
    # canonical re-encoding reproduces the file exactly
    assert data == product_mod._dump_overview(result)


def test_all_pass_summary(tmp_path, monkeypatch):
    path, _ = write_valid(tmp_path, monkeypatch, valid_sections())

    result = load_overview(path)

    assert result["summary"] == {
        "domain_count": 3,
        "pass_count": 3,
        "fail_count": 0,
        "quality": "pass",
    }
    assert result["quality"] == "pass"


@pytest.mark.parametrize(
    "qualities",
    [
        ("fail", "pass", "pass"),
        ("pass", "fail", "pass"),
        ("pass", "pass", "fail"),
        ("fail", "fail", "pass"),
        ("fail", "fail", "fail"),
    ],
)
def test_pass_count_and_quality(tmp_path, monkeypatch, qualities):
    sections = valid_sections(*qualities)
    path, _ = write_valid(tmp_path, monkeypatch, sections)

    result = load_overview(path)

    passes = qualities.count("pass")
    assert result["summary"]["pass_count"] == passes
    assert result["summary"]["fail_count"] == 3 - passes
    expected = "pass" if passes == 3 else "fail"
    assert result["summary"]["quality"] == expected
    assert result["quality"] == expected


def test_arrays_restored_following_loader_contracts(tmp_path, monkeypatch):
    path, _ = write_valid(tmp_path, monkeypatch)

    result = load_overview(path)

    changes = result["product"]["trend"]["changes"]
    assert isinstance(changes, tuple)
    # worst is the matching tuple item, identity preserved
    assert result["product"]["trend"]["worst"] is changes[0]
    assert isinstance(result["substrate"]["worst"], tuple)
    assert isinstance(result["crosspoint"]["sources"], list)
    assert isinstance(result["crosspoint"]["trend"]["worst"], tuple)


def test_sections_equal_direct_loaders(tmp_path, monkeypatch):
    sections = valid_sections()
    product_result, substrate_result, crosspoint_result = sections
    path, _ = write_valid(tmp_path, monkeypatch, sections)

    result = load_overview(path)

    assert result["product"] == product_result
    assert result["substrate"] == substrate_result
    assert result["crosspoint"] == crosspoint_result


def test_serialize_overview_reads_flat_substrate_quality(tmp_path, monkeypatch):
    # The substrate loader returns a flat dict; its quality is S["quality"].
    sections = valid_sections("pass", "fail", "pass")
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    assert document["summary"]["pass_count"] == 2
    assert document["summary"]["quality"] == "fail"
    assert document["quality"] == "fail"


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_must_be_str(value):
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_overview(value)


def test_empty_path_value_error():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_overview("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_overview(str(tmp_path / "missing.json"))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_overview(str(tmp_path))


def test_file_not_modified_on_success(tmp_path, monkeypatch):
    path, data = write_valid(tmp_path, monkeypatch)
    before = os.stat(path)

    load_overview(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


def test_file_not_modified_on_failure(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    mangled = data.replace(b'"domain_count":3', b'"domain_count":2')
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        load_overview(path)

    with open(path, "rb") as handle:
        assert handle.read() == mangled


def test_bom_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, b"\xef\xbb\xbf" + data)
    with pytest.raises(ValueError, match="BOM"):
        load_overview(path)


def test_trailing_newline_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data + b"\n")
    with pytest.raises(ValueError, match="trailing newline"):
        load_overview(path)


def test_invalid_utf8_rejected(tmp_path):
    path = write_bytes(tmp_path, b"{\xff}")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_overview(path)


@pytest.mark.parametrize("data", [b"", b"{", b"[1,2]", b"null", b"42", b'"x"'])
def test_invalid_json_or_non_object_rejected(tmp_path, data):
    path = write_bytes(tmp_path, data)
    with pytest.raises(ValueError):
        load_overview(path)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_rejected(tmp_path, monkeypatch, token):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data.replace(b"0.1", token.encode("ascii"), 1))
    with pytest.raises(ValueError):
        load_overview(path)


def test_duplicate_keys_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(
        tmp_path, data.replace(b'{"product"', b'{"product":null,"product"', 1)
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_overview(path)


def test_missing_top_key_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    document = json.loads(data)
    del document["quality"]
    path = write_bytes(
        tmp_path, json.dumps(document, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview(path)


def test_extra_top_key_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data[:-1] + b',"extra":1}')
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview(path)


def test_wrong_top_key_order_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    document = json.loads(data)
    reordered = {key: document[key] for key in reversed(KEYS)}
    path = write_bytes(
        tmp_path, json.dumps(reordered, separators=(",", ":")).encode()
    )
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview(path)


def test_wrong_summary_key_order_rejected(tmp_path, monkeypatch):
    sections = valid_sections()
    data = serialize_sections(monkeypatch, sections)
    # swap the order of pass_count and fail_count by rebuilding the bytes
    document = json.loads(data)
    summary = document["summary"]
    document["summary"] = {
        "domain_count": 3,
        "fail_count": 0,
        "pass_count": 3,
        "quality": "pass",
    }
    assert list(document["summary"].keys()) != SUMMARY_KEYS
    raw = json.dumps(document, separators=(",", ":")).encode()
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="keys must be in the order"):
        load_overview(path)


@pytest.mark.parametrize(
    "name,value",
    [("domain_count", 3), ("pass_count", 3), ("fail_count", 0)],
)
def test_summary_ints_reject_bool(tmp_path, monkeypatch, name, value):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(
        tmp_path,
        data.replace(f'"{name}":{value}'.encode(), f'"{name}":true'.encode(), 1),
    )
    with pytest.raises(ValueError, match=f"{name} must be a non-bool int"):
        load_overview(path)


def test_domain_count_must_be_3(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(
        tmp_path, data.replace(b'"domain_count":3', b'"domain_count":2', 1)
    )
    with pytest.raises(ValueError, match="domain_count must be 3"):
        load_overview(path)


def test_fail_count_must_complement_pass_count(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data.replace(b'"fail_count":0', b'"fail_count":1', 1))
    with pytest.raises(ValueError, match="fail_count must equal 3 - pass_count"):
        load_overview(path)


def test_pass_count_must_match_domains(tmp_path, monkeypatch):
    sections = valid_sections("fail", "pass", "pass")
    data = serialize_sections(monkeypatch, sections)
    # claim 3 passes although only two domains pass
    path = write_bytes(
        tmp_path,
        data.replace(
            b'"pass_count":2,"fail_count":1',
            b'"pass_count":3,"fail_count":0',
            1,
        ),
    )
    with pytest.raises(ValueError, match="pass_count must equal the number"):
        load_overview(path)


def test_summary_quality_must_follow_domains(tmp_path, monkeypatch):
    sections = valid_sections("fail", "pass", "pass")
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    document["summary"]["quality"] = "pass"  # inconsistent with fail_count 1
    raw = json.dumps(document, separators=(",", ":")).encode()
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="all three domains pass"):
        load_overview(path)


def test_top_level_quality_must_equal_summary_quality(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    assert data.endswith(b'"quality":"pass"}')
    raw = data[: -len(b'"quality":"pass"}')] + b'"quality":"fail"}'
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="quality must equal summary.quality"):
        load_overview(path)


@pytest.mark.parametrize(
    "bad_quality",
    ['"quality":"maybe"', '"quality":null', '"quality":1'],
)
def test_summary_quality_enum(tmp_path, monkeypatch, bad_quality):
    data = serialize_sections(monkeypatch, valid_sections())
    # the summary quality is the first  "quality":"pass"}  occurrence (end of summary)
    needle = b'"pass_count":3,"fail_count":0,"quality":"pass"'
    replacement = b'"pass_count":3,"fail_count":0,' + bad_quality.encode()
    path = write_bytes(tmp_path, data.replace(needle, replacement, 1))
    with pytest.raises(ValueError, match="quality must be"):
        load_overview(path)


def test_product_section_must_follow_dashboard_contract(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    # break the product trend: change item index so it no longer runs from 1
    path = write_bytes(
        tmp_path, data.replace(b'"index":1', b'"index":2', 1)
    )
    with pytest.raises(ValueError, match="overview"):
        load_overview(path)


def test_product_summary_passed_must_match_changes(tmp_path, monkeypatch):
    sections = valid_sections("pass", "pass", "pass")
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    document["product"]["summary"]["passed"] = 0
    document["product"]["summary"]["failed"] = 1
    raw = json.dumps(document, separators=(",", ":")).encode()
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="passed must equal the number"):
        load_overview(path)


def test_product_quality_must_equal_trend_quality(tmp_path, monkeypatch):
    sections = valid_sections("pass", "pass", "pass")
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    document["product"]["quality"] = "fail"
    raw = json.dumps(document, separators=(",", ":")).encode()
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="quality must equal trend.quality"):
        load_overview(path)


def test_substrate_section_must_follow_loader_contract(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    # substrate worst index 0 violates 1 <= i < count
    path = write_bytes(
        tmp_path,
        data.replace(b'"worst":[1,0,0.0,', b'"worst":[0,0,0.0,', 1),
    )
    with pytest.raises(ValueError, match="overview"):
        load_overview(path)


def test_crosspoint_section_must_follow_loader_contract(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    # trend count 3 != number of sources (2)
    path = write_bytes(
        tmp_path,
        data.replace(
            b'"count":2,"changes":1,"regressed"',
            b'"count":3,"changes":1,"regressed"',
            1,
        ),
    )
    with pytest.raises(ValueError, match="overview"):
        load_overview(path)


def test_non_canonical_spacing_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data.replace(b":", b": ", 1))
    with pytest.raises(ValueError, match="canonical"):
        load_overview(path)


def test_non_canonical_float_spelling_rejected(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    path = write_bytes(tmp_path, data.replace(b"0.1", b"0.100", 1))
    with pytest.raises(ValueError, match="canonical"):
        load_overview(path)


def test_unrounded_float_rejected(tmp_path, monkeypatch):
    sections = valid_sections()
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    document["product"]["trend"]["changes"][0]["coverage_delta"] = 1.0 / 3.0
    raw = json.dumps(document, separators=(",", ":")).encode()
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="overview"):
        load_overview(path)


def test_negative_zero_float_rejected(tmp_path, monkeypatch):
    sections = valid_sections()
    data = serialize_sections(monkeypatch, sections)
    document = json.loads(data)
    document["product"]["trend"]["changes"][0]["coverage_delta"] = -0.0
    raw = json.dumps(document, separators=(",", ":")).encode()
    assert b"-0.0" in raw
    path = write_bytes(tmp_path, raw)
    with pytest.raises(ValueError, match="overview"):
        load_overview(path)
