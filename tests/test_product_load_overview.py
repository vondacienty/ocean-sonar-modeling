"""Tests for product.serialize_overview and product.load_overview."""

from __future__ import annotations

import json

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar import substrate as substrate_mod
from ocean_sonar import crosspoint as crosspoint_mod
from ocean_sonar.product import load_overview, serialize_overview
from ocean_sonar.substrate import (
    batch,
    dump_aggregate,
    serialize_aggregate_report,
)
from ocean_sonar.crosspoint import serialize_audit, serialize_audit_report

ANALYSIS_1 = [(3.0, 0.5), (6.0, 0.5), (None, None)]
INTENSITIES_1 = [0.4, 0.6, 0.7]
ANALYSIS_2 = [(1.0, 0.0), (2.0, 2.0)]
INTENSITIES_2 = [0.2, 0.9]


def dump_json(document):
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def write_batch(path, analysis, intensities):
    path.write_bytes(batch(analysis, intensities))
    return str(path)


def make_aggregate_report(tmp_path, name):
    first = write_batch(
        tmp_path / f"{name}_b1.json", ANALYSIS_1, INTENSITIES_1
    )
    second = write_batch(
        tmp_path / f"{name}_b2.json", ANALYSIS_2, INTENSITIES_2
    )
    aggregate_path = tmp_path / f"{name}_agg.json"
    aggregate_path.write_bytes(dump_aggregate([first, second]))
    report_path = tmp_path / f"{name}_report.json"
    report_path.write_bytes(serialize_aggregate_report(str(aggregate_path)))
    return str(report_path)


def write_comparison(path, changes):
    quality = (
        "pass" if all(c["quality"] == "pass" for c in changes) else "fail"
    )
    path.write_bytes(
        dump_json({"changes": changes, "worst": changes[0], "quality": quality})
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


def quality_report_trend_document():
    item = {
        "index": 1,
        "failed_delta": 0,
        "coverage_delta": 0.0,
        "quality": "pass",
    }
    return {"changes": [item], "worst": dict(item), "quality": "pass"}


@pytest.fixture
def paths(tmp_path):
    # product domain: a canonical quality report trend document
    product_path = tmp_path / "product_trend.json"
    product_path.write_bytes(dump_json(quality_report_trend_document()))

    # substrate domain: real aggregate report trend
    report0 = make_aggregate_report(tmp_path, "s0")
    report1 = make_aggregate_report(tmp_path, "s1")
    substrate_path = tmp_path / "substrate_trend.json"
    substrate_path.write_bytes(
        substrate_mod.serialize_aggregate_report_trend([report0, report1])
    )

    # crosspoint domain: real audit report trend
    c0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    c1 = write_comparison(
        tmp_path / "c1.json", [change(1, 0, 0.2, 0.5, "pass")]
    )
    c2 = write_comparison(
        tmp_path / "c2.json", [change(1, 0, 0.3, 0.4, "pass")]
    )
    audit0 = tmp_path / "audit0.json"
    audit0.write_bytes(serialize_audit([c0, c1]))
    audit1 = tmp_path / "audit1.json"
    audit1.write_bytes(serialize_audit([c1, c2]))
    areport0 = tmp_path / "areport0.json"
    areport0.write_bytes(serialize_audit_report(str(audit0)))
    areport1 = tmp_path / "areport1.json"
    areport1.write_bytes(serialize_audit_report(str(audit1)))
    crosspoint_path = tmp_path / "audit_trend.json"
    crosspoint_mod.export_audit_report_trend(
        [str(areport0), str(areport1)], str(crosspoint_path)
    )

    return str(product_path), str(substrate_path), str(crosspoint_path)


def write_overview(tmp_path, data=None, **kwargs):
    path = tmp_path / "overview.json"
    if data is None:
        data = serialize_overview(*kwargs["paths"])
    path.write_bytes(data)
    return str(path)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_exported():
    assert "load_overview" in product_mod.__all__
    assert product_mod.load_overview is load_overview


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------


def test_roundtrip(tmp_path, paths):
    data = serialize_overview(*paths)
    path = write_overview(tmp_path, data=data)

    result = load_overview(path)

    assert list(result.keys()) == [
        "product",
        "substrate",
        "crosspoint",
        "summary",
        "quality",
    ]
    assert data == dump_json(result)
    assert open(path, "rb").read() == data


def test_roundtrip_equals_the_three_loaders(tmp_path, paths):
    product_path, substrate_path, crosspoint_path = paths
    path = write_overview(tmp_path, paths=paths)

    result = load_overview(path)

    assert result["product"] == product_mod.quality_dashboard(product_path)
    assert result["substrate"] == (
        substrate_mod.load_aggregate_report_trend(substrate_path)
    )
    assert result["crosspoint"] == (
        crosspoint_mod.load_audit_report_trend(crosspoint_path)
    )


def test_nested_arrays_restored_to_tuples(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)

    result = load_overview(path)

    assert isinstance(result["product"]["trend"]["changes"], tuple)
    assert isinstance(result["substrate"]["worst"], tuple)
    assert isinstance(result["crosspoint"]["trend"]["worst"], tuple)
    assert isinstance(result["crosspoint"]["sources"], list)


def test_summary_all_pass(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)

    result = load_overview(path)

    assert list(result["summary"].keys()) == [
        "domain_count",
        "pass_count",
        "fail_count",
        "quality",
    ]
    assert result["summary"] == {
        "domain_count": 3,
        "pass_count": 3,
        "fail_count": 0,
        "quality": "pass",
    }
    assert result["quality"] == "pass"
    assert type(result["summary"]["domain_count"]) is int
    assert type(result["summary"]["pass_count"]) is int
    assert type(result["summary"]["fail_count"]) is int


def test_file_not_modified(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    before = open(path, "rb").read()
    load_overview(path)
    assert open(path, "rb").read() == before


def test_failing_domain_summary(tmp_path, paths):
    product_path, substrate_path, crosspoint_path = paths

    # rebuild the product domain so its trend quality is "fail"
    failing_item = {
        "index": 1,
        "failed_delta": 1,
        "coverage_delta": 0.0,
        "quality": "fail",
    }
    failing_path = tmp_path / "failing_product_trend.json"
    failing_path.write_bytes(
        dump_json(
            {
                "changes": [failing_item],
                "worst": dict(failing_item),
                "quality": "fail",
            }
        )
    )

    data = serialize_overview(
        str(failing_path), substrate_path, crosspoint_path
    )
    path = tmp_path / "failing_overview.json"
    path.write_bytes(data)

    result = load_overview(str(path))
    assert result["summary"] == {
        "domain_count": 3,
        "pass_count": 2,
        "fail_count": 1,
        "quality": "fail",
    }
    assert result["quality"] == "fail"
    assert result["product"]["quality"] == "fail"


# ---------------------------------------------------------------------------
# path / OS errors
# ---------------------------------------------------------------------------


def test_path_non_str_typeerror():
    with pytest.raises(TypeError, match="^path must be a str$"):
        load_overview(123)


def test_path_empty_valueerror():
    with pytest.raises(ValueError, match="^path must not be empty$"):
        load_overview("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_overview(str(tmp_path / "missing.json"))


def test_directory_raises_isadirectoryerror(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_overview(str(tmp_path))


# ---------------------------------------------------------------------------
# byte / parse rejection
# ---------------------------------------------------------------------------


def test_bom_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    bad = tmp_path / "bom.json"
    bad.write_bytes(b"\xef\xbb\xbf" + open(path, "rb").read())
    with pytest.raises(ValueError, match="BOM"):
        load_overview(str(bad))


def test_trailing_newline_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    bad = tmp_path / "nl.json"
    bad.write_bytes(open(path, "rb").read() + b"\n")
    with pytest.raises(ValueError, match="trailing newline"):
        load_overview(str(bad))


def test_invalid_utf8_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_overview(str(path))


def test_invalid_json_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError, match="valid JSON"):
        load_overview(str(path))


def test_nan_constant_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(
        b'{"product":{"trend":{"changes":[],"worst":{},"quality":"pass"},'
        b'"summary":{},"quality":"pass"},"substrate":NaN,'
        b'"crosspoint":{},"summary":{},"quality":"pass"}'
    )
    with pytest.raises(ValueError, match="valid JSON"):
        load_overview(str(path))


def test_duplicate_top_level_key_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    bad = tmp_path / "dup.json"
    bad.write_bytes(open(path, "rb").read()[:-1] + b',"quality":"pass"}')
    with pytest.raises(ValueError, match="valid JSON|duplicate"):
        load_overview(str(bad))


def test_noncanonical_bytes_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    bad = tmp_path / "pretty.json"
    bad.write_text(json.dumps(document, indent=2))
    with pytest.raises(ValueError, match="canonical"):
        load_overview(str(bad))


# ---------------------------------------------------------------------------
# structural rejection
# ---------------------------------------------------------------------------


def test_not_an_object_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"[1,2,3]")
    with pytest.raises(ValueError, match="valid overview"):
        load_overview(str(path))


def test_wrong_top_level_key_order_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    reordered = {key: document[key] for key in reversed(document.keys())}
    bad = tmp_path / "reordered.json"
    bad.write_bytes(dump_json(reordered))
    with pytest.raises(ValueError, match="overview keys must be in the order"):
        load_overview(str(bad))


def test_extra_top_level_key_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    bad = tmp_path / "extra.json"
    bad.write_bytes(open(path, "rb").read()[:-1] + b',"extra":1}')
    with pytest.raises(ValueError, match="valid overview"):
        load_overview(str(bad))


def test_missing_top_level_key_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    del document["summary"]
    bad = tmp_path / "missing.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="valid overview"):
        load_overview(str(bad))


def test_product_domain_must_match_quality_dashboard_contract(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["product"]["summary"]["passed"] = 99
    bad = tmp_path / "bad_product.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="passed does not match the trend"):
        load_overview(str(bad))


def test_product_domain_wrong_key_order_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    trend = document["product"]["trend"]
    document["product"]["trend"] = {
        "quality": trend["quality"],
        "changes": trend["changes"],
        "worst": trend["worst"],
    }
    bad = tmp_path / "bad_product.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="changes, worst, quality"):
        load_overview(str(bad))


def test_product_trend_quality_relation_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["product"]["quality"] = "fail"
    bad = tmp_path / "bad_product.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="quality must equal the trend quality"):
        load_overview(str(bad))


def test_substrate_domain_must_match_loader_contract(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["substrate"]["regressed"] = 5
    bad = tmp_path / "bad_substrate.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError):
        load_overview(str(bad))


def test_crosspoint_domain_must_match_loader_contract(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["crosspoint"]["trend"]["count"] = 99
    bad = tmp_path / "bad_crosspoint.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="count must equal the number of sources"):
        load_overview(str(bad))


def test_summary_domain_count_must_be_3(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["summary"]["domain_count"] = 2
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="domain_count is inconsistent"):
        load_overview(str(bad))


def test_summary_pass_count_must_match_domains(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["summary"]["pass_count"] = 1
    document["summary"]["fail_count"] = 2
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="pass_count is inconsistent"):
        load_overview(str(bad))


def test_summary_quality_must_match_domains(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["summary"]["quality"] = "fail"
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="all three domains pass"):
        load_overview(str(bad))


def test_top_quality_must_equal_summary_quality(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["quality"] = "fail"
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="quality must equal the summary quality"):
        load_overview(str(bad))


def test_bool_counts_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    document["summary"]["domain_count"] = True
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="domain_count must be a non-bool int"):
        load_overview(str(bad))


def test_summary_wrong_key_order_rejected(tmp_path, paths):
    path = write_overview(tmp_path, paths=paths)
    document = json.loads(open(path, "rb").read())
    old = document["summary"]
    document["summary"] = {
        "quality": old["quality"],
        "domain_count": old["domain_count"],
        "pass_count": old["pass_count"],
        "fail_count": old["fail_count"],
    }
    bad = tmp_path / "bad.json"
    bad.write_bytes(dump_json(document))
    with pytest.raises(ValueError, match="domain_count, pass_count"):
        load_overview(str(bad))


# ---------------------------------------------------------------------------
# serialize_overview behavior
# ---------------------------------------------------------------------------


def test_serialize_overview_returns_compact_bytes(tmp_path, paths):
    data = serialize_overview(*paths)
    assert isinstance(data, bytes)
    assert b"\n" not in data
    assert b": " not in data
    assert b", " not in data
    document = json.loads(data)
    assert list(document.keys()) == [
        "product",
        "substrate",
        "crosspoint",
        "summary",
        "quality",
    ]


def test_serialize_overview_missing_product_file(tmp_path, paths):
    _, substrate_path, crosspoint_path = paths
    with pytest.raises(FileNotFoundError):
        serialize_overview(
            str(tmp_path / "gone.json"), substrate_path, crosspoint_path
        )


def test_serialize_overview_loads_in_order(monkeypatch, tmp_path, paths):
    calls = []

    def wrap(name, fn):
        def wrapped(path):
            calls.append(name)
            return fn(path)

        return wrapped

    monkeypatch.setattr(
        product_mod,
        "quality_dashboard",
        wrap("product", product_mod.quality_dashboard),
    )
    monkeypatch.setattr(
        substrate_mod,
        "load_aggregate_report_trend",
        wrap("substrate", substrate_mod.load_aggregate_report_trend),
    )
    monkeypatch.setattr(
        crosspoint_mod,
        "load_audit_report_trend",
        wrap("crosspoint", crosspoint_mod.load_audit_report_trend),
    )

    serialize_overview(*paths)
    assert calls == ["product", "substrate", "crosspoint"]
