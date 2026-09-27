"""Tests for product.render_overview."""

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import load_overview, render_overview, serialize_overview


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


def substrate_section(
    quality="pass",
    *,
    count=2,
    changes=1,
    regressed=None,
    unknown_delta=0,
    unknown_ratio_delta=0.0,
    worst_q=None,
):
    if regressed is None:
        regressed = 0 if quality == "pass" else 1
    if worst_q is None:
        worst_q = quality
    return {
        "count": count,
        "changes": changes,
        "regressed": regressed,
        "unknown_delta": unknown_delta,
        "unknown_ratio_delta": unknown_ratio_delta,
        "worst": (1, unknown_delta, unknown_ratio_delta, worst_q),
        "quality": quality,
    }


def crosspoint_section(
    quality="pass",
    *,
    count=2,
    changes=1,
    regressed=None,
    failed_delta=None,
    pass_ratio_delta=0.0,
    worst_q=None,
):
    if regressed is None:
        regressed = 0 if quality == "pass" else 1
    if failed_delta is None:
        failed_delta = 1 if quality == "fail" else 0
    if worst_q is None:
        worst_q = quality
    return {
        "sources": ["a.json", "b.json"],
        "trend": {
            "count": count,
            "changes": changes,
            "regressed": regressed,
            "failed_delta": failed_delta,
            "pass_ratio_delta": pass_ratio_delta,
            "worst": (1, failed_delta, pass_ratio_delta, worst_q),
            "quality": quality,
        },
    }


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


def write_overview(tmp_path, monkeypatch, sections, name="overview.json"):
    install_loaders(monkeypatch, sections)
    data = serialize_overview("product.json", "substrate.json", "crosspoint.json")
    path = tmp_path / name
    path.write_bytes(data)
    return str(path), data


def all_pass_sections():
    return (
        product_section(trend_item(coverage_delta=0.1)),
        substrate_section("pass"),
        crosspoint_section("pass"),
    )


def mixed_sections():
    return (
        product_section(
            trend_item(failed_delta=1, coverage_delta=-0.2, quality="fail")
        ),
        substrate_section(
            "fail",
            unknown_delta=3,
            unknown_ratio_delta=0.25,
        ),
        crosspoint_section(
            "fail",
            failed_delta=2,
            pass_ratio_delta=-0.5,
        ),
    )


def test_exported():
    assert "render_overview" in product_mod.__all__
    assert product_mod.render_overview is render_overview


def test_all_pass_exact_output(tmp_path, monkeypatch):
    path, _ = write_overview(tmp_path, monkeypatch, all_pass_sections())

    assert render_overview(path) == (
        "OVERVIEW=pass,3,3,0\n"
        "PRODUCT=pass,1,1,0,0.100000\n"
        "SUBSTRATE=pass,2,1,0,0,0.000000\n"
        "CROSSPOINT=pass,2,1,0,0,0.000000"
    )


def test_mixed_qualities_exact_output(tmp_path, monkeypatch):
    path, _ = write_overview(tmp_path, monkeypatch, mixed_sections())

    assert render_overview(path) == (
        "OVERVIEW=fail,3,0,3\n"
        "PRODUCT=fail,1,0,1,-0.200000\n"
        "SUBSTRATE=fail,2,1,1,3,0.250000\n"
        "CROSSPOINT=fail,2,1,1,2,-0.500000"
    )


def test_no_trailing_newline_and_three_separators(tmp_path, monkeypatch):
    path, _ = write_overview(tmp_path, monkeypatch, all_pass_sections())

    text = render_overview(path)
    assert not text.endswith("\n")
    assert text.count("\n") == 3
    assert len(text.split("\n")) == 4


def test_partial_pass_counts(tmp_path, monkeypatch):
    sections = (
        product_section(trend_item(coverage_delta=0.1)),
        substrate_section(
            "fail",
            unknown_delta=1,
            unknown_ratio_delta=0.1,
        ),
        crosspoint_section("pass"),
    )
    path, _ = write_overview(tmp_path, monkeypatch, sections)

    lines = render_overview(path).split("\n")
    assert lines[0] == "OVERVIEW=fail,3,2,1"


def test_negative_zero_rendered_as_zero(tmp_path, monkeypatch):
    sections = (
        product_section(trend_item(coverage_delta=-0.0)),
        substrate_section("pass", unknown_ratio_delta=-0.0),
        crosspoint_section("pass", pass_ratio_delta=-0.0),
    )
    path, _ = write_overview(tmp_path, monkeypatch, sections)

    lines = render_overview(path).split("\n")
    assert lines[1].endswith(",0.000000")
    assert lines[2].endswith(",0.000000")
    assert lines[3].endswith(",0.000000")
    assert "-0.000000" not in render_overview(path)


def test_values_taken_in_column_order_without_recompute(monkeypatch):
    overview = {
        "product": {
            "trend": {"changes": (), "worst": None, "quality": "pass"},
            "summary": {
                "count": 11,
                "passed": 4,
                "failed": 7,
                "coverage_delta": 0.125,
            },
            "quality": "fail",
        },
        "substrate": {
            "count": 22,
            "changes": 21,
            "regressed": 5,
            "unknown_delta": 9,
            "unknown_ratio_delta": -0.75,
            "worst": (1, 0, 0.0, "pass"),
            "quality": "pass",
        },
        "crosspoint": {
            "sources": ["a", "b"],
            "trend": {
                "count": 33,
                "changes": 32,
                "regressed": 8,
                "failed_delta": 13,
                "pass_ratio_delta": 0.5,
                "worst": (1, 0, 0.0, "pass"),
                "quality": "fail",
            },
        },
        "summary": {
            "domain_count": 3,
            "pass_count": 42,
            "fail_count": 99,
            "quality": "pass",
        },
        "quality": "pass",
    }
    monkeypatch.setattr(product_mod, "load_overview", lambda path: overview)

    assert render_overview("overview.json") == (
        "OVERVIEW=pass,3,42,99\n"
        "PRODUCT=fail,11,4,7,0.125000\n"
        "SUBSTRATE=pass,22,21,5,9,-0.750000\n"
        "CROSSPOINT=fail,33,32,8,13,0.500000"
    )


def test_calls_load_overview_exactly_once_with_path_unchanged(monkeypatch):
    calls = []
    sentinel = object()

    def fake_load(path):
        calls.append(path)
        return sentinel

    monkeypatch.setattr(product_mod, "load_overview", fake_load)
    with pytest.raises(TypeError):
        render_overview("overview.json")
    assert calls == ["overview.json"]


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(TypeError("path must be a str"), id="type-error"),
        pytest.param(ValueError("path must not be empty"), id="value-error"),
        pytest.param(
            FileNotFoundError(2, "No such file or directory", "x.json"),
            id="file-not-found",
        ),
        pytest.param(IsADirectoryError(21, "Is a directory", "x"), id="is-a-directory"),
        pytest.param(PermissionError(13, "Permission denied", "x.json"), id="oserror"),
    ],
)
def test_load_overview_exceptions_propagate_unchanged(monkeypatch, exc):
    def fake_load(path):
        raise exc

    monkeypatch.setattr(product_mod, "load_overview", fake_load)
    with pytest.raises(type(exc)) as excinfo:
        render_overview("overview.json")
    assert excinfo.value is exc


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_overview(str(tmp_path / "missing.json"))


def test_corrupted_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError):
        render_overview(str(path))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        render_overview(str(tmp_path))


def test_input_file_not_modified(tmp_path, monkeypatch):
    path, data = write_overview(tmp_path, monkeypatch, mixed_sections())

    render_overview(path)

    assert load_overview(path) is not None
    assert (tmp_path / "overview.json").read_bytes() == data
