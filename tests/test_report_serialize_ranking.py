"""Tests for report.serialize_ranking."""

import copy
import json

import pytest

from ocean_sonar import report as report_mod
from ocean_sonar.report import rank_batches, serialize_ranking
from ocean_sonar.report import aggregate_dashboard_summaries


def _batch(pass_count=1, terrain_valid=4, terrain_total=4):
    return aggregate_dashboard_summaries(
        [
            {
                "tolerance_count": 1,
                "pass_count": pass_count,
                "fail_count": 1 - pass_count,
                "first_pass_index": 0 if pass_count else None,
                "terrain_total": terrain_total,
                "terrain_valid": terrain_valid,
                "terrain_coverage": round(terrain_valid / terrain_total, 6),
                "quality_score": round(
                    100 * (pass_count / 1) * (terrain_valid / terrain_total), 6
                ),
            }
        ]
    )


RANKING = rank_batches([_batch(0, 0), _batch(1, 2), _batch(1)])
TRIPLE = (0, 50.0, 0.5)


def _value(**changes):
    value = copy.deepcopy(RANKING)
    value.update(changes)
    return value


def _triples(*triples):
    return tuple(triples)


def test_serialize_ranking_exported():
    assert "serialize_ranking" in report_mod.__all__
    assert report_mod.serialize_ranking is serialize_ranking


def test_rank_batches_output_roundtrips():
    data = serialize_ranking(RANKING)
    assert isinstance(data, bytes)
    parsed = json.loads(data)
    assert parsed["ranking"] == [
        [2, 100.0, 1.0],
        [1, 50.0, 0.5],
        [0, 0.0, 0.0],
    ]
    assert parsed["score_spread"] == 100.0


def test_output_is_utf8_json_without_bom_or_trailing_newline():
    data = serialize_ranking(RANKING)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.endswith(b"\n")
    data.decode("utf-8")


def test_json_is_compact_and_key_order_preserved():
    data = serialize_ranking(RANKING)
    assert b", " not in data
    assert b": " not in data
    parsed = json.loads(data)
    assert list(parsed.keys()) == ["ranking", "score_spread"]
    assert isinstance(parsed["ranking"], list)
    assert all(isinstance(row, list) for row in parsed["ranking"])


def test_ties_ordered_by_coverage_then_index():
    value = {
        "ranking": _triples(
            (0, 50.0, 0.9),
            (1, 50.0, 0.9),
            (2, 50.0, 0.1),
        ),
        "score_spread": 0.0,
    }
    parsed = json.loads(serialize_ranking(value))
    assert parsed["ranking"] == [
        [0, 50.0, 0.9],
        [1, 50.0, 0.9],
        [2, 50.0, 0.1],
    ]


def test_floats_rounded_to_six_and_negative_zero_normalized():
    value = {
        "ranking": _triples((0, -0.0, 0.123456789)),
        "score_spread": 0.0,
    }
    token = serialize_ranking(value)
    assert token == b'{"ranking":[[0,0.0,0.123457]],"score_spread":0.0}'


def test_input_not_modified():
    snapshot = copy.deepcopy(RANKING)
    serialize_ranking(RANKING)
    assert RANKING == snapshot


def test_container_type_error():
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(42)
    assert str(excinfo.value) == "ranking must be a dict"
    with pytest.raises(TypeError):
        serialize_ranking([])


def test_key_order_error():
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(
            {"score_spread": 0.0, "ranking": RANKING["ranking"]}
        )
    assert "keys must be in the order" in str(excinfo.value)


def test_missing_and_extra_keys():
    with pytest.raises(TypeError):
        serialize_ranking({"ranking": RANKING["ranking"]})
    with pytest.raises(TypeError):
        serialize_ranking(dict(RANKING, extra=1))


def test_ranking_tuple_container_and_emptiness():
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(_value(ranking=[]))
    assert str(excinfo.value) == "ranking must be a tuple"
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(_value(ranking=()))
    assert str(excinfo.value) == "ranking must be non-empty"


def test_item_must_be_a_tuple():
    value = _value(ranking=_triples((1, 50.0, 0.5), (0, 0.0, 0.0)))
    value["ranking"] = ([1, 50.0, 0.5], (0, 0.0, 0.0))
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[0]: must be a tuple"


def test_item_arity_is_value_error():
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": ((0, 50.0),), "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: must have 3 elements"
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": ((0, 50.0, 0.5, 1),), "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: must have 3 elements"


def test_index_must_be_non_bool_int():
    value = {
        "ranking": _triples((True, 50.0, 0.5)),
        "score_spread": 0.0,
    }
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[0]: index must be a non-bool int"

    value = {
        "ranking": _triples((0.0, 50.0, 0.5)),
        "score_spread": 0.0,
    }
    with pytest.raises(TypeError):
        serialize_ranking(value)


def test_index_must_be_non_negative():
    value = {
        "ranking": _triples((-1, 50.0, 0.5), (0, 0.0, 0.5)),
        "score_spread": 50.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[0]: index must be >= 0"


def test_index_set_must_be_zero_to_n_minus_one():
    value = {
        "ranking": _triples((0, 50.0, 0.5), (2, 0.0, 0.5)),
        "score_spread": 50.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == (
        "ranking[1]: index must be in [0, len(ranking))"
    )

    value = {
        "ranking": _triples((0, 50.0, 0.5), (0, 0.0, 0.5)),
        "score_spread": 50.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[1]: index must be unique"


def test_score_type_and_range():
    value = {
        "ranking": _triples((0, 50, 0.5)),
        "score_spread": 0.0,
    }
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[0]: score must be a float"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, float("nan"), 0.5)),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: score must be finite"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, 100.000001, 0.5)),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: score must be in [0, 100]"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, -0.000001, 0.5)),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: score must be in [0, 100]"


def test_coverage_type_and_range():
    value = {
        "ranking": _triples((0, 50.0, 1)),
        "score_spread": 0.0,
    }
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "ranking[0]: coverage must be a float"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, 50.0, float("inf"))),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: coverage must be finite"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, 50.0, 1.000001)),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: coverage must be in [0, 1]"

    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, 50.0, -0.000001)),
             "score_spread": 0.0}
        )
    assert str(excinfo.value) == "ranking[0]: coverage must be in [0, 1]"


def test_ordering_errors():
    value = {
        "ranking": _triples((0, 0.0, 1.0), (1, 50.0, 0.5)),
        "score_spread": 50.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert "ranking[1]: " in str(excinfo.value)
    assert "score descending" in str(excinfo.value)

    value = {
        "ranking": _triples(
            (0, 50.0, 0.5),
            (1, 50.0, 0.6),
        ),
        "score_spread": 0.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert "coverage descending" in str(excinfo.value)

    value = {
        "ranking": _triples(
            (1, 50.0, 0.5),
            (0, 50.0, 0.5),
        ),
        "score_spread": 0.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert "ranking[1]: " in str(excinfo.value)
    assert "index ascending" in str(excinfo.value)


def test_score_spread_type():
    value = {
        "ranking": _triples((0, 50.0, 0.5)),
        "score_spread": 0,
    }
    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "score_spread must be a float"

    value = {
        "ranking": _triples((0, 50.0, 0.5)),
        "score_spread": True,
    }
    with pytest.raises(TypeError):
        serialize_ranking(value)


def test_score_spread_must_be_finite():
    value = {
        "ranking": _triples((0, 50.0, 0.5)),
        "score_spread": float("inf"),
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == "score_spread must be finite"


def test_score_spread_relation():
    value = {
        "ranking": _triples((0, 50.0, 0.5)),
        "score_spread": 1.0,
    }
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking(value)
    assert str(excinfo.value) == (
        "score_spread must equal round(max(score) - min(score), 6)"
    )

    good = {
        "ranking": _triples((1, 2.0, 0.9), (0, 0.5, 0.1)),
        "score_spread": 1.5,
    }
    serialize_ranking(good)


def test_negative_zero_score_spread_accepted():
    value = {
        "ranking": _triples(TRIPLE),
        "score_spread": -0.0,
    }
    assert serialize_ranking(value) == (
        b'{"ranking":[[0,50.0,0.5]],"score_spread":0.0}'
    )


def test_ranking_validated_before_score_spread():
    with pytest.raises(ValueError) as excinfo:
        serialize_ranking({"ranking": (), "score_spread": "x"})
    assert str(excinfo.value) == "ranking must be non-empty"

    with pytest.raises(TypeError) as excinfo:
        serialize_ranking(
            {"ranking": _triples((0, 50, 0.5)), "score_spread": "x"}
        )
    assert str(excinfo.value) == "ranking[0]: score must be a float"


def test_single_entry_requires_zero_spread():
    serialize_ranking(
        {"ranking": _triples(TRIPLE), "score_spread": 0.0}
    )
    with pytest.raises(ValueError):
        serialize_ranking(
            {"ranking": _triples(TRIPLE), "score_spread": -1.0}
        )
