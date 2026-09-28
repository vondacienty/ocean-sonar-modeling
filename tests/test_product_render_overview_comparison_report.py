"""Tests for product.render_overview_comparison_report."""

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    export_overview_comparison_report,
    export_overview_trend_report,
    load_overview_comparison_report,
    render_overview_comparison_report,
    serialize_overview_comparison,
    serialize_overview_trend,
)


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


def sections_for(domains):
    product_quality, substrate_quality, crosspoint_quality = domains
    if product_quality == "pass":
        product = product_section()
    else:
        product = product_section(
            trend_item(
                failed_delta=1, coverage_delta=-0.2, quality="fail"
            )
        )
    return (
        product,
        substrate_section(substrate_quality),
        crosspoint_section(crosspoint_quality),
    )


def install_sections(monkeypatch, domains):
    product_result, substrate_result, crosspoint_result = sections_for(
        domains
    )
    monkeypatch.setattr(
        product_mod,
        "quality_dashboard",
        lambda path: product_result,
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


def write_report(tmp_path, monkeypatch, domain_sets):
    overview_paths = []
    for i, domains in enumerate(domain_sets):
        install_sections(monkeypatch, domains)
        data = product_mod.serialize_overview(
            "product.json", "substrate.json", "crosspoint.json"
        )
        overview_path = tmp_path / f"overview{i}.json"
        overview_path.write_bytes(data)
        overview_paths.append(str(overview_path))

    trend_report_paths = []
    for i in range(len(overview_paths) - 1):
        trend_data = serialize_overview_trend(
            [overview_paths[i], overview_paths[i + 1]]
        )
        trend_path = tmp_path / f"overview_trend{i}.json"
        trend_path.write_bytes(trend_data)
        trend_report_path = tmp_path / f"overview_trend_report{i}.json"
        export_overview_trend_report(
            str(trend_path), str(trend_report_path)
        )
        trend_report_paths.append(str(trend_report_path))

    comparison_data = serialize_overview_comparison(trend_report_paths)
    comparison_path = tmp_path / "overview_comparison.json"
    comparison_path.write_bytes(comparison_data)
    report_path = tmp_path / "overview_comparison_report.json"
    report_data = export_overview_comparison_report(
        str(comparison_path), str(report_path)
    )
    return str(report_path), str(comparison_path), report_data


ALL_PASS = ("pass", "pass", "pass")


def test_exported():
    assert "render_overview_comparison_report" in product_mod.__all__
    assert (
        product_mod.render_overview_comparison_report
        is render_overview_comparison_report
    )


def test_all_pass_exact_output(tmp_path, monkeypatch):
    path, comparison_path, _ = write_report(
        tmp_path, monkeypatch, [ALL_PASS, ALL_PASS, ALL_PASS]
    )

    assert render_overview_comparison_report(path) == (
        f'REPORT=1,"{comparison_path}",overview_comparison,pass\n'
        "SUMMARY=1,0,0,0\n"
        "WORST=1,0,0,pass"
    )


def test_regressed_exact_output(tmp_path, monkeypatch):
    path, comparison_path, _ = write_report(
        tmp_path,
        monkeypatch,
        [ALL_PASS, ALL_PASS, ("fail", "pass", "fail")],
    )

    assert render_overview_comparison_report(path) == (
        f'REPORT=1,"{comparison_path}",overview_comparison,fail\n'
        "SUMMARY=1,1,1,-1\n"
        "WORST=1,1,-1,fail"
    )


def test_no_trailing_newline(tmp_path, monkeypatch):
    path, _, _ = write_report(tmp_path, monkeypatch, [ALL_PASS, ALL_PASS, ALL_PASS])

    text = render_overview_comparison_report(path)
    assert not text.endswith("\n")
    assert text.count("\n") == 2
    assert len(text.split("\n")) == 3


def test_path_rendered_as_compact_json(tmp_path, monkeypatch):
    path, comparison_path, _ = write_report(
        tmp_path, monkeypatch, [ALL_PASS, ALL_PASS, ALL_PASS]
    )

    text = render_overview_comparison_report(path)
    first_line = text.split("\n", 1)[0]
    assert (
        first_line
        == f'REPORT=1,"{comparison_path}",overview_comparison,pass'
    )


def test_values_taken_directly_from_r_without_recompute(monkeypatch):
    import json

    report = {
        "schema_version": 1,
        "source": {
            "path": "comparison 路径.json",
            "kind": "overview_comparison",
        },
        "summary": {
            "count": 9,
            "failed": 7,
            "regressed_delta": 6,
            "passed_delta": -5,
        },
        "worst": {
            "index": 4,
            "regressed_delta": 3,
            "passed_delta": -2,
            "quality": "fail",
        },
        "quality": "fail",
    }
    monkeypatch.setattr(
        product_mod,
        "load_overview_comparison_report",
        lambda path: report,
    )

    rendered_path = json.dumps(
        "comparison 路径.json", ensure_ascii=False, separators=(",", ":")
    )
    assert render_overview_comparison_report("report.json") == (
        f"REPORT=1,{rendered_path},overview_comparison,fail\n"
        "SUMMARY=9,7,6,-5\n"
        "WORST=4,3,-2,fail"
    )


def test_calls_load_overview_comparison_report_exactly_once_with_path_unchanged(
    monkeypatch,
):
    calls = []
    sentinel = object()

    def fake_load(path):
        calls.append(path)
        return sentinel

    monkeypatch.setattr(
        product_mod, "load_overview_comparison_report", fake_load
    )
    with pytest.raises(TypeError):
        render_overview_comparison_report("report.json")
    assert calls == ["report.json"]


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
def test_load_exceptions_propagate_unchanged(monkeypatch, exc):
    def fake_load(path):
        raise exc

    monkeypatch.setattr(
        product_mod, "load_overview_comparison_report", fake_load
    )
    with pytest.raises(type(exc)) as excinfo:
        render_overview_comparison_report("report.json")
    assert excinfo.value is exc


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_overview_comparison_report(str(tmp_path / "missing.json"))


def test_corrupted_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError):
        render_overview_comparison_report(str(path))


def test_directory_path(tmp_path):
    with pytest.raises(IsADirectoryError):
        render_overview_comparison_report(str(tmp_path))


def test_input_file_not_modified(tmp_path, monkeypatch):
    path, _, data = write_report(
        tmp_path,
        monkeypatch,
        [ALL_PASS, ALL_PASS, ("fail", "pass", "fail")],
    )

    render_overview_comparison_report(path)

    assert load_overview_comparison_report(path) is not None
    assert (tmp_path / "overview_comparison_report.json").read_bytes() == data
