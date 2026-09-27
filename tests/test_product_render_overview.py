"""Tests for product.render_overview."""

import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import render_overview, serialize_overview


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


def substrate_section(quality="pass"):
    regressed = 0 if quality == "pass" else 1
    return {
        "count": 2,
        "changes": 1,
        "regressed": regressed,
        "unknown_delta": 0,
        "unknown_ratio_delta": 0.0,
        "worst": (1, 0, 0.0, quality),
        "quality": quality,
    }


def crosspoint_section(quality="pass"):
    regressed = 0 if quality == "pass" else 1
    failed_delta = 1 if quality == "fail" else 0
    return {
        "sources": ["a.json", "b.json"],
        "trend": {
            "count": 2,
            "changes": 1,
            "regressed": regressed,
            "failed_delta": failed_delta,
            "pass_ratio_delta": 0.0,
            "worst": (1, failed_delta, 0.0, quality),
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
    monkeypatch.setattr(
        product_mod, "quality_dashboard", lambda path: product_result
    )
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


def write_valid(tmp_path, monkeypatch, sections=None):
    if sections is None:
        sections = valid_sections()
    data = serialize_sections(monkeypatch, sections)
    return write_bytes(tmp_path, data), data


def test_exported():
    assert "render_overview" in product_mod.__all__
    assert product_mod.render_overview is render_overview


def test_calls_load_overview_exactly_once(monkeypatch):
    calls = []

    class _Section(dict):
        def __getattr__(self, name):
            return self[name]

    loaded = {
        "quality": "pass",
        "summary": _Section(domain_count=3, pass_count=3, fail_count=0),
        "product": _Section(
            quality="pass",
            summary={
                "count": 1,
                "passed": 1,
                "failed": 0,
                "coverage_delta": 0.1,
            },
        ),
        "substrate": _Section(
            quality="pass",
            count=2,
            changes=1,
            regressed=0,
            unknown_delta=0,
            unknown_ratio_delta=0.0,
        ),
        "crosspoint": {
            "trend": _Section(
                quality="pass",
                count=2,
                changes=1,
                regressed=0,
                failed_delta=0,
                pass_ratio_delta=0.0,
            )
        },
    }

    def fake_load(path):
        calls.append(path)
        return loaded

    monkeypatch.setattr(product_mod, "load_overview", fake_load)
    result = render_overview("overview.json")

    assert calls == ["overview.json"]
    assert result == (
        "OVERVIEW=pass,3,3,0\n"
        "PRODUCT=pass,1,1,0,0.100000\n"
        "SUBSTRATE=pass,2,1,0,0,0.000000\n"
        "CROSSPOINT=pass,2,1,0,0,0.000000"
    )


def test_exact_four_lines_no_trailing_newline(tmp_path, monkeypatch):
    (path, _) = write_valid(tmp_path, monkeypatch)

    text = render_overview(path)

    assert len(text.split("\n")) == 4
    assert not text.endswith("\n")


def test_all_pass_rendering(tmp_path, monkeypatch):
    (path, _) = write_valid(tmp_path, monkeypatch)

    assert render_overview(path) == (
        "OVERVIEW=pass,3,3,0\n"
        "PRODUCT=pass,1,1,0,0.100000\n"
        "SUBSTRATE=pass,2,1,0,0,0.000000\n"
        "CROSSPOINT=pass,2,1,0,0,0.000000"
    )


def test_values_taken_in_column_order(tmp_path, monkeypatch):
    item = trend_item(index=1, failed_delta=2, coverage_delta=-0.25, quality="fail")
    product = product_section(item)
    substrate = substrate_section("fail")
    substrate.update(
        count=3,
        changes=2,
        regressed=1,
        unknown_delta=4,
        unknown_ratio_delta=0.125,
        worst=(2, 4, 0.125, "fail"),
    )
    crosspoint = crosspoint_section("fail")
    crosspoint["sources"] = ["a", "b", "c"]
    crosspoint["trend"].update(
        count=3,
        changes=2,
        regressed=1,
        failed_delta=2,
        pass_ratio_delta=-0.5,
        worst=(2, 2, -0.5, "fail"),
    )
    sections = (product, substrate, crosspoint)
    (path, _) = write_valid(tmp_path, monkeypatch, sections)

    assert render_overview(path) == (
        "OVERVIEW=fail,3,0,3\n"
        "PRODUCT=fail,1,0,1,-0.250000\n"
        "SUBSTRATE=fail,3,2,1,4,0.125000\n"
        "CROSSPOINT=fail,3,2,1,2,-0.500000"
    )


def test_mixed_quality_combination(tmp_path, monkeypatch):
    sections = valid_sections("fail", "pass", "fail")
    (path, _) = write_valid(tmp_path, monkeypatch, sections)

    lines = render_overview(path).split("\n")
    assert lines[0] == "OVERVIEW=fail,3,1,2"
    assert lines[1].startswith("PRODUCT=fail,")
    assert lines[2].startswith("SUBSTRATE=pass,")
    assert lines[3].startswith("CROSSPOINT=fail,")


def test_input_file_not_modified(tmp_path, monkeypatch):
    (path, data) = write_valid(tmp_path, monkeypatch)
    before = os.stat(path)

    render_overview(path)

    with open(path, "rb") as handle:
        assert handle.read() == data
    after = os.stat(path)
    assert after.st_size == before.st_size


@pytest.mark.parametrize("value", [1, 1.5, b"x", None, ["x"], object()])
def test_path_type_error_passthrough(value, monkeypatch):
    def fake_load(path):
        raise TypeError("path must be a str")

    monkeypatch.setattr(product_mod, "load_overview", fake_load)
    with pytest.raises(TypeError, match="^path must be a str$"):
        render_overview(value)


def test_empty_path_value_error_passthrough(monkeypatch):
    def fake_load(path):
        raise ValueError("path must not be empty")

    monkeypatch.setattr(product_mod, "load_overview", fake_load)
    with pytest.raises(ValueError, match="^path must not be empty$"):
        render_overview("")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_overview(str(tmp_path / "missing.json"))


def test_corrupted_file_error_passthrough(tmp_path, monkeypatch):
    data = serialize_sections(monkeypatch, valid_sections())
    mangled = data.replace(b'"domain_count":3', b'"domain_count":2')
    path = write_bytes(tmp_path, mangled)

    with pytest.raises(ValueError):
        render_overview(path)
