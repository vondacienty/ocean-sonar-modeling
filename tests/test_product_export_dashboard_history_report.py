"""Tests for product.export_dashboard_history_report."""

from __future__ import annotations

import os

import pytest

from ocean_sonar import product as product_mod
from ocean_sonar.product import (
    export_dashboard_history_report,
    serialize_dashboard_history,
    serialize_dashboard_history_report,
)


def trend_item(index, failed_delta, regressed_delta, passed_delta, quality):
    return {
        "index": index,
        "failed_delta": failed_delta,
        "regressed_delta": regressed_delta,
        "passed_delta": passed_delta,
        "quality": quality,
    }


def dashboard_doc(changes):
    n = len(changes)
    r = sum(1 for c in changes if c["quality"] == "fail")
    p = n - r
    ratio = round(float(p / n), 6)
    if ratio == 0:
        ratio = 0.0
    worst = min(
        changes,
        key=lambda c: (
            c["passed_delta"],
            -c["failed_delta"],
            -c["regressed_delta"],
            c["index"],
        ),
    )
    return {
        "trend": {
            "count": n + 1,
            "changes": changes,
            "regressed": r,
            "worst": worst,
            "quality": "pass" if r == 0 else "fail",
        },
        "summary": {
            "reports": n + 1,
            "passed": p,
            "regressed": r,
            "ratio": ratio,
            "worst": worst["index"],
        },
        "quality": "pass" if r == 0 else "fail",
    }


def write_dashboard(tmp_path, doc, name):
    path = tmp_path / name
    path.write_bytes(
        product_mod._dump_overview_comparison_report_trend(doc)
    )
    return str(path)


@pytest.fixture
def paths(tmp_path):
    passing = dashboard_doc(
        [trend_item(i + 1, 0, 0, 1, "pass") for i in range(3)]
    )
    one_fail = dashboard_doc(
        [
            trend_item(1, 0, 0, 1, "pass"),
            trend_item(2, 1, 1, -1, "fail"),
            trend_item(3, 0, 0, 1, "pass"),
        ]
    )
    return (
        write_dashboard(tmp_path, passing, "a.json"),
        write_dashboard(tmp_path, one_fail, "b.json"),
    )


@pytest.fixture
def history_path(tmp_path, paths):
    path = tmp_path / "history.json"
    path.write_bytes(serialize_dashboard_history(paths))
    return str(path)


def test_exported():
    assert "export_dashboard_history_report" in product_mod.__all__
    assert (
        product_mod.export_dashboard_history_report
        is export_dashboard_history_report
    )


def test_success_writes_canonical_bytes_and_returns_them(
    tmp_path, history_path, paths
):
    output = str(tmp_path / "report.json")
    result = export_dashboard_history_report(history_path, paths, output)
    expected = serialize_dashboard_history_report(history_path, paths)
    assert isinstance(result, bytes)
    assert result == expected
    with open(output, "rb") as handle:
        assert handle.read() == expected


def test_inputs_not_modified(tmp_path, history_path, paths):
    before = [open(p, "rb").read() for p in paths]
    history_before = open(history_path, "rb").read()
    paths_snapshot = list(paths)
    export_dashboard_history_report(
        history_path, paths, str(tmp_path / "report.json")
    )
    assert [open(p, "rb").read() for p in paths] == before
    assert open(history_path, "rb").read() == history_before
    assert list(paths) == paths_snapshot


def test_overwrites_existing_output(tmp_path, history_path, paths):
    output = tmp_path / "report.json"
    output.write_bytes(b"old contents")
    result = export_dashboard_history_report(
        history_path, paths, str(output)
    )
    assert output.read_bytes() == result


def test_calls_serialize_exactly_once(monkeypatch, tmp_path, history_path, paths):
    calls = []
    original = product_mod.serialize_dashboard_history_report

    def counting(path, value):
        calls.append((path, value))
        return original(path, value)

    monkeypatch.setattr(
        product_mod,
        "serialize_dashboard_history_report",
        counting,
    )
    output = str(tmp_path / "report.json")
    export_dashboard_history_report(history_path, paths, output)
    assert calls == [(history_path, paths)]


def test_path_validation_before_output_validation(
    monkeypatch, tmp_path, history_path, paths
):
    calls = []
    original = product_mod.serialize_dashboard_history_report

    def counting(path, value):
        calls.append((path, value))
        return original(path, value)

    monkeypatch.setattr(
        product_mod,
        "serialize_dashboard_history_report",
        counting,
    )
    # Bad path surfaces from the serialize call before output is seen.
    with pytest.raises(TypeError, match="path must be a str"):
        export_dashboard_history_report(123, paths, 456)
    assert calls == [(123, paths)]

    with pytest.raises(ValueError, match="path must not be empty"):
        export_dashboard_history_report("", paths, "")
    assert calls[-1] == ("", paths)


def test_paths_prefix_error_passthrough_before_output(
    tmp_path, history_path
):
    with pytest.raises(ValueError, match=r"paths\[1\]: "):
        export_dashboard_history_report(
            history_path, ["a", ""], 123
        )


def test_serialize_exception_propagates_unchanged(
    monkeypatch, tmp_path, history_path, paths
):
    def raising(path, value):
        raise ValueError("boom")

    monkeypatch.setattr(
        product_mod,
        "serialize_dashboard_history_report",
        raising,
    )
    with pytest.raises(ValueError, match="^boom$"):
        export_dashboard_history_report(
            history_path, paths, str(tmp_path / "report.json")
        )


def test_cross_check_mismatch_propagates(tmp_path, paths):
    # History serialized from a different dashboard set fails the cross-check.
    passing = dashboard_doc(
        [trend_item(i + 1, 0, 0, 1, "pass") for i in range(3)]
    )
    two_fail = dashboard_doc(
        [
            trend_item(1, 1, 1, -1, "fail"),
            trend_item(2, 1, 1, -1, "fail"),
            trend_item(3, 0, 0, 1, "pass"),
        ]
    )
    other_paths = (
        write_dashboard(tmp_path, passing, "c.json"),
        write_dashboard(tmp_path, two_fail, "d.json"),
    )
    bad_history = tmp_path / "history.json"
    bad_history.write_bytes(serialize_dashboard_history(other_paths))
    with pytest.raises(ValueError, match="dashboard history report"):
        export_dashboard_history_report(
            str(bad_history), paths, str(tmp_path / "report.json")
        )
    assert not (tmp_path / "report.json").exists()


def test_missing_history_file(tmp_path, paths):
    missing = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        export_dashboard_history_report(
            missing, paths, str(tmp_path / "report.json")
        )
    assert not (tmp_path / "report.json").exists()


def test_output_non_str_typeerror(monkeypatch, tmp_path, history_path, paths):
    monkeypatch.setattr(
        product_mod,
        "serialize_dashboard_history_report",
        lambda path, value: b"{}",
    )
    with pytest.raises(TypeError, match="output must be a str"):
        export_dashboard_history_report(history_path, paths, 123)


def test_output_empty_valueerror(monkeypatch, tmp_path, history_path, paths):
    monkeypatch.setattr(
        product_mod,
        "serialize_dashboard_history_report",
        lambda path, value: b"{}",
    )
    with pytest.raises(ValueError, match="output must not be empty"):
        export_dashboard_history_report(history_path, paths, "")


def test_output_same_as_history_valueerror(tmp_path, history_path, paths):
    with pytest.raises(ValueError, match="same file"):
        export_dashboard_history_report(
            history_path, paths, history_path
        )


@pytest.mark.parametrize("index", [0, 1])
def test_output_same_as_a_paths_item_valueerror(
    tmp_path, history_path, paths, index
):
    with pytest.raises(ValueError, match="same file"):
        export_dashboard_history_report(
            history_path, paths, paths[index]
        )


def test_output_samefile_via_symlink(tmp_path, history_path, paths):
    link = str(tmp_path / "history-link.json")
    os.symlink(history_path, link)
    with pytest.raises(ValueError, match="same file"):
        export_dashboard_history_report(history_path, paths, link)


def test_output_hard_link_to_input_valueerror(
    tmp_path, history_path, paths
):
    hard = str(tmp_path / "dashboard-hard.json")
    os.link(paths[0], hard)
    with pytest.raises(ValueError, match="same file"):
        export_dashboard_history_report(history_path, paths, hard)


def test_output_resolves_to_history_through_nonexistent_component(
    tmp_path, history_path, paths
):
    os.symlink(tmp_path, tmp_path / "selflink")
    equivalent = str(
        tmp_path / "selflink" / "missing" / ".." / "history.json"
    )
    assert not os.path.exists(equivalent)
    with pytest.raises(ValueError, match="same file"):
        export_dashboard_history_report(
            history_path, paths, equivalent
        )


def test_no_temp_file_left_after_success(tmp_path, history_path, paths):
    export_dashboard_history_report(
        history_path, paths, str(tmp_path / "report.json")
    )
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_existing_output_unchanged_when_replace_fails(
    monkeypatch, tmp_path, history_path, paths
):
    output = tmp_path / "report.json"
    original_bytes = b"do not touch"
    output.write_bytes(original_bytes)

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot replace"):
        export_dashboard_history_report(
            history_path, paths, str(output)
        )
    assert output.read_bytes() == original_bytes
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == []


def test_inputs_unchanged_when_write_fails(
    monkeypatch, tmp_path, history_path, paths
):
    before = [open(p, "rb").read() for p in paths]
    history_before = open(history_path, "rb").read()

    def fail_replace(src, dst):
        raise OSError("cannot replace")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        export_dashboard_history_report(
            history_path, paths, str(tmp_path / "report.json")
        )
    assert [open(p, "rb").read() for p in paths] == before
    assert open(history_path, "rb").read() == history_before


def test_oserror_from_write_propagates(
    monkeypatch, tmp_path, history_path, paths
):
    def fail_replace(src, dst):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="nope"):
        export_dashboard_history_report(
            history_path, paths, str(tmp_path / "report.json")
        )
