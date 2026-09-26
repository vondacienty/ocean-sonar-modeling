"""Tests for crosspoint.audit_comparisons."""

import json

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import audit_comparisons

EXPECTED_KEYS = ["files", "changes", "failed", "worst", "quality"]


def write_comparison(path, changes):
    """Write a canonical serialize_comparison-shaped JSON file."""
    quality = "fail" if any(c["quality"] == "fail" for c in changes) else "pass"
    document = {
        "changes": changes,
        "worst": changes[0],
        "quality": quality,
    }
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
def comparison_loader(monkeypatch):
    """Patch load_comparison to serve queued comparisons; tracks loaded paths."""
    state = {"loaded": []}

    def install(comparisons):
        queue = list(comparisons)

        def fake_load_comparison(path):
            state["loaded"].append(path)
            return queue.pop(0)

        monkeypatch.setattr(
            crosspoint_mod, "load_comparison", fake_load_comparison
        )

    install.loaded = state["loaded"]
    return install


def make_loaded(changes):
    quality = "fail" if any(c["quality"] == "fail" for c in changes) else "pass"
    return {"changes": tuple(changes), "worst": changes[0], "quality": quality}


def test_basic_two_files(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json",
        [change(1, 0, 0.1, 1.0, "pass")],
    )
    p1 = write_comparison(
        tmp_path / "c1.json",
        [
            change(1, 1, -0.2, -0.5, "fail"),
            change(2, 0, 0.3, 2.0, "pass"),
        ],
    )

    result = audit_comparisons([p0, p1])

    assert list(result.keys()) == EXPECTED_KEYS
    assert result["files"] == 2
    assert result["changes"] == 3
    assert result["failed"] == 1
    assert result["quality"] == "fail"
    assert result["worst"] == (1, 1, 1, -0.2, -0.5, "fail")
    assert [type(value).__name__ for value in result["worst"]] == [
        "int",
        "int",
        "int",
        "float",
        "float",
        "str",
    ]


def test_all_pass_is_pass(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json",
        [change(1, 0, 0.2, 2.0, "pass"), change(2, 0, 0.3, 3.0, "pass")],
    )

    result = audit_comparisons([p0, p1])
    assert result == {
        "files": 2,
        "changes": 3,
        "failed": 0,
        "worst": (0, 1, 0, 0.1, 1.0, "pass"),
        "quality": "pass",
    }


def test_worst_orders_by_score_then_coverage_then_negated_degraded(
    comparison_loader,
):
    # file 0 has score -0.5; file 1 has the same score but larger coverage.
    comparisons = [
        make_loaded([change(1, 0, 0.0, -0.5, "fail")]),
        make_loaded([change(1, 0, 0.2, -0.5, "fail")]),
    ]
    comparison_loader(comparisons)

    result = audit_comparisons(["c0.json", "c1.json"])
    assert result["worst"] == (0, 1, 0, 0.0, -0.5, "fail")


def test_worst_negated_degraded_breaks_tie(comparison_loader):
    # Same score and coverage; larger degraded_delta makes -dd smaller.
    comparisons = [
        make_loaded([change(1, 0, 0.0, -0.5, "fail")]),
        make_loaded([change(1, 2, 0.0, -0.5, "fail")]),
    ]
    comparison_loader(comparisons)

    result = audit_comparisons(["c0.json", "c1.json"])
    assert result["worst"][0] == 1
    assert result["worst"][2] == 2


def test_worst_tie_prefers_lower_file_then_lower_index(comparison_loader):
    comparisons = [
        make_loaded(
            [
                change(1, 0, 0.0, 0.0, "pass"),
                change(2, 0, 0.0, 0.0, "pass"),
            ]
        ),
        make_loaded([change(1, 0, 0.0, 0.0, "pass")]),
    ]
    comparison_loader(comparisons)

    result = audit_comparisons(["c0.json", "c1.json"])
    assert result["worst"] == (0, 1, 0, 0.0, 0.0, "pass")


def test_expanded_in_file_order_and_change_order(comparison_loader):
    changes_a = [
        change(1, 0, 0.1, 5.0, "pass"),
        change(2, 0, 0.1, 4.0, "pass"),
    ]
    changes_b = [change(1, 0, 0.1, 3.0, "pass")]
    comparison_loader([make_loaded(changes_a), make_loaded(changes_b)])

    result = audit_comparisons(["a.json", "b.json"])
    # Lowest score is file 1, change index 1 (3.0): both orders traversed.
    assert result["worst"] == (1, 1, 0, 0.1, 3.0, "pass")
    assert result["changes"] == 3
    assert result["files"] == 2


def test_loads_each_path_once_in_order(comparison_loader):
    comparisons = [
        make_loaded([change(1, 0, 0.1, 1.0, "pass")]),
        make_loaded([change(1, 0, 0.2, 2.0, "pass")]),
        make_loaded([change(1, 0, 0.3, 3.0, "fail")]),
    ]
    comparison_loader(comparisons)
    paths = ["c0.json", "c1.json", "c2.json"]

    audit_comparisons(paths)
    assert comparison_loader.loaded == paths


def test_load_exception_propagates(comparison_loader):
    class Boom(Exception):
        pass

    def fake_load(path):
        if path == "c1.json":
            raise Boom("disk on fire")
        return make_loaded([change(1, 0, 0.1, 1.0, "pass")])

    import unittest.mock

    with unittest.mock.patch.object(
        crosspoint_mod, "load_comparison", side_effect=fake_load
    ) as mocked:
        with pytest.raises(Boom, match="disk on fire"):
            audit_comparisons(["c0.json", "c1.json", "c2.json"])
        assert mocked.call_count == 2


def test_missing_file_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        audit_comparisons(
            [str(tmp_path / "nope0.json"), str(tmp_path / "nope1.json")]
        )


def test_paths_container_validation():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        audit_comparisons({})
    with pytest.raises(TypeError):
        audit_comparisons("a/b")


def test_paths_count_validation():
    with pytest.raises(ValueError, match="at least 2 items"):
        audit_comparisons([])
    with pytest.raises(ValueError, match="at least 2 items"):
        audit_comparisons([123])


def test_paths_item_validation():
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        audit_comparisons(["a", 5])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        audit_comparisons(["", "b"])
    with pytest.raises(TypeError, match=r"^paths\[0\]: must be a str$"):
        audit_comparisons([None, ""])


def test_tuple_paths(tmp_path):
    p0 = write_comparison(
        tmp_path / "c0.json", [change(1, 0, 0.1, 1.0, "pass")]
    )
    p1 = write_comparison(
        tmp_path / "c1.json", [change(1, 0, 0.2, 2.0, "pass")]
    )
    result = audit_comparisons((p0, p1))
    assert result["quality"] == "pass"


def test_inputs_and_files_not_modified(tmp_path):
    changes = [change(1, 0, 0.1, 1.0, "pass")]
    p0 = write_comparison(tmp_path / "c0.json", changes)
    p1 = write_comparison(tmp_path / "c1.json", changes)
    before0 = open(p0, "rb").read()
    before1 = open(p1, "rb").read()
    paths = [p0, p1]

    audit_comparisons(list(paths))

    assert paths == [p0, p1]
    assert open(p0, "rb").read() == before0
    assert open(p1, "rb").read() == before1


def test_exported():
    assert hasattr(crosspoint_mod, "audit_comparisons")
    assert "audit_comparisons" in crosspoint_mod.__all__
    assert crosspoint_mod.audit_comparisons is audit_comparisons
