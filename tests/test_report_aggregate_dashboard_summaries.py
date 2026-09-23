"""Tests for report.aggregate_dashboard_summaries."""

import copy

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.report import aggregate_dashboard_summaries, dashboard_summary

CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]
LAYERS = [
    (1.0, 2, 2, [(1.0, 0.5), (2.0, 0.0), (4.0, 1.0), (0.0, 0.0)]),
]
TOLERANCES = [0.1, 0.5, 1.0]

S1 = dashboard_summary(CROSSINGS, TOLERANCES, LAYERS)["summary"]
S2 = dashboard_summary(
    [(0.0, 0.0, 10.0, 9.0)], [0.5], [(1.0, 1, 1, [(None, None)])]
)["summary"]

KEYS = [
    "batch_count",
    "tolerance_count",
    "pass_count",
    "fail_count",
    "first_pass_summary",
    "terrain_total",
    "terrain_valid",
    "terrain_coverage",
    "quality_score",
]


def test_aggregate_exported():
    assert "aggregate_dashboard_summaries" in report_mod.__all__
    assert report_mod.aggregate_dashboard_summaries is aggregate_dashboard_summaries


def test_aggregate_basic():
    result = aggregate_dashboard_summaries([S1, S2])
    assert isinstance(result, dict)
    assert list(result.keys()) == KEYS

    m = S1["tolerance_count"] + S2["tolerance_count"]
    p = S1["pass_count"] + S2["pass_count"]
    n = S1["terrain_total"] + S2["terrain_total"]
    v = S1["terrain_valid"] + S2["terrain_valid"]

    assert result["batch_count"] == 2
    assert result["tolerance_count"] == m
    assert result["pass_count"] == p
    assert result["fail_count"] == m - p
    assert result["first_pass_summary"] == 0
    assert result["terrain_total"] == n
    assert result["terrain_valid"] == v
    assert result["terrain_coverage"] == round(v / n, 6)
    assert result["quality_score"] == round(100 * (p / m) * (v / n), 6)


def test_aggregate_types():
    result = aggregate_dashboard_summaries([S1, S2])
    for key in (
        "batch_count",
        "tolerance_count",
        "pass_count",
        "fail_count",
        "terrain_total",
        "terrain_valid",
    ):
        assert type(result[key]) is int
    assert type(result["first_pass_summary"]) is int
    assert type(result["terrain_coverage"]) is float
    assert type(result["quality_score"]) is float


def test_aggregate_accepts_tuple():
    result = aggregate_dashboard_summaries((S1, S2))
    assert result["batch_count"] == 2
    assert result["tolerance_count"] == (
        S1["tolerance_count"] + S2["tolerance_count"]
    )


def test_aggregate_single_item_matches_item_metrics():
    result = aggregate_dashboard_summaries([S1])
    assert result["batch_count"] == 1
    assert result["tolerance_count"] == S1["tolerance_count"]
    assert result["pass_count"] == S1["pass_count"]
    assert result["fail_count"] == S1["fail_count"]
    assert result["first_pass_summary"] == 0
    assert result["terrain_total"] == S1["terrain_total"]
    assert result["terrain_valid"] == S1["terrain_valid"]
    assert result["terrain_coverage"] == S1["terrain_coverage"]
    assert result["quality_score"] == S1["quality_score"]


def test_aggregate_first_pass_summary_index():
    assert aggregate_dashboard_summaries([S1])["first_pass_summary"] == 0
    assert aggregate_dashboard_summaries([S2, S1])["first_pass_summary"] == 1
    assert aggregate_dashboard_summaries([S1, S2])["first_pass_summary"] == 0


def test_aggregate_no_pass():
    result = aggregate_dashboard_summaries([S2, S2])
    assert result["first_pass_summary"] is None
    assert result["pass_count"] == 0
    assert result["fail_count"] == result["tolerance_count"]
    assert result["terrain_valid"] == 0
    assert result["terrain_coverage"] == 0.0
    assert result["quality_score"] == 0.0
    assert type(result["terrain_coverage"]) is float
    assert type(result["quality_score"]) is float


def test_aggregate_does_not_modify_inputs():
    items = [copy.deepcopy(S1), copy.deepcopy(S2)]
    snapshot = copy.deepcopy(items)
    aggregate_dashboard_summaries(items)
    assert items == snapshot


def test_outer_container_type_error():
    with pytest.raises(TypeError):
        aggregate_dashboard_summaries(None)
    with pytest.raises(TypeError):
        aggregate_dashboard_summaries(42)
    with pytest.raises(TypeError):
        aggregate_dashboard_summaries({})
    with pytest.raises(TypeError):
        aggregate_dashboard_summaries(iter([S1]))
    with pytest.raises(TypeError):
        aggregate_dashboard_summaries(True)


def test_outer_container_empty_value_error():
    with pytest.raises(ValueError):
        aggregate_dashboard_summaries([])
    with pytest.raises(ValueError):
        aggregate_dashboard_summaries(())


def test_item_not_dict_type_error():
    with pytest.raises(TypeError) as excinfo:
        aggregate_dashboard_summaries([42])
    assert str(excinfo.value) == "summaries[0]: must be a dict"
    with pytest.raises(TypeError) as excinfo:
        aggregate_dashboard_summaries([S1, (1, 2)])
    assert str(excinfo.value) == "summaries[1]: must be a dict"


def test_item_key_order_type_error():
    with pytest.raises(TypeError) as excinfo:
        aggregate_dashboard_summaries([{}])
    assert str(excinfo.value).startswith("summaries[0]: keys must be in the order")
    keys = list(S1)
    reordered = {key: S1[key] for key in keys[1:] + keys[:1]}
    with pytest.raises(TypeError) as excinfo:
        aggregate_dashboard_summaries([S2, reordered])
    assert str(excinfo.value).startswith("summaries[1]: keys must be in the order")


def _mutated(item, **changes):
    value = dict(item)
    value.update(changes)
    return value


def test_item_field_type_errors():
    with pytest.raises(TypeError, match=r"^summaries\[0\]: tolerance_count"):
        aggregate_dashboard_summaries([_mutated(S1, tolerance_count=True)])
    with pytest.raises(TypeError, match=r"^summaries\[1\]: pass_count"):
        aggregate_dashboard_summaries(
            [S2, _mutated(S1, pass_count=1.0)]
        )
    with pytest.raises(TypeError, match=r"^summaries\[0\]: terrain_coverage"):
        aggregate_dashboard_summaries([_mutated(S1, terrain_coverage=1)])
    with pytest.raises(TypeError, match=r"^summaries\[0\]: quality_score"):
        aggregate_dashboard_summaries([_mutated(S1, quality_score="66.6")])
    with pytest.raises(TypeError, match=r"^summaries\[0\]: first_pass_index"):
        aggregate_dashboard_summaries([_mutated(S1, first_pass_index=True)])


def test_item_range_and_relation_value_errors():
    with pytest.raises(ValueError, match=r"^summaries\[0\]: tolerance_count"):
        aggregate_dashboard_summaries([_mutated(S1, tolerance_count=0)])
    with pytest.raises(ValueError, match=r"^summaries\[1\]: pass_count"):
        aggregate_dashboard_summaries(
            [
                S2,
                _mutated(
                    S1, pass_count=S1["tolerance_count"] + 1, fail_count=0
                ),
            ]
        )
    with pytest.raises(ValueError, match=r"^summaries\[0\]: fail_count"):
        aggregate_dashboard_summaries(
            [_mutated(S1, fail_count=S1["fail_count"] + 1)]
        )
    with pytest.raises(ValueError, match=r"^summaries\[0\]: terrain_total"):
        aggregate_dashboard_summaries([_mutated(S1, terrain_total=0)])
    with pytest.raises(ValueError, match=r"^summaries\[1\]: terrain_valid"):
        aggregate_dashboard_summaries(
            [
                S2,
                _mutated(
                    S1, terrain_valid=S1["terrain_total"] + 1
                ),
            ]
        )
    with pytest.raises(ValueError, match=r"^summaries\[0\]: terrain_coverage"):
        aggregate_dashboard_summaries([_mutated(S1, terrain_coverage=0.5)])
    with pytest.raises(ValueError, match=r"^summaries\[0\]: quality_score"):
        aggregate_dashboard_summaries([_mutated(S1, quality_score=0.0)])


def test_first_error_stops():
    # the invalid second item is reached only because the first is valid
    with pytest.raises(TypeError, match=r"^summaries\[1\]: must be a dict"):
        aggregate_dashboard_summaries([S1, 42])
    # an invalid first item short-circuits before the second is examined
    with pytest.raises(TypeError, match=r"^summaries\[0\]: tolerance_count"):
        aggregate_dashboard_summaries(
            [_mutated(S1, tolerance_count=1.0), 42]
        )


def test_aggregation_math_over_three_items():
    s3 = dashboard_summary(
        CROSSINGS, [0.2, 0.8], LAYERS
    )["summary"]
    result = aggregate_dashboard_summaries([S2, S1, s3])
    m = S2["tolerance_count"] + S1["tolerance_count"] + s3["tolerance_count"]
    p = S2["pass_count"] + S1["pass_count"] + s3["pass_count"]
    n = S2["terrain_total"] + S1["terrain_total"] + s3["terrain_total"]
    v = S2["terrain_valid"] + S1["terrain_valid"] + s3["terrain_valid"]
    assert result["batch_count"] == 3
    assert result["tolerance_count"] == m
    assert result["pass_count"] == p
    assert result["fail_count"] == m - p
    assert result["first_pass_summary"] == 1
    assert result["terrain_total"] == n
    assert result["terrain_valid"] == v
    assert result["terrain_coverage"] == round(v / n, 6)
    assert result["quality_score"] == round(100 * (p / m) * (v / n), 6)
