"""Tests for crosspoint.load_pair_gate_score_summary."""

import json

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    load_pair_gate_score_summary,
    serialize_pair_gate_score_summary,
)

FIRST = [
    (0.0, 0.0, 10.0),
    (1.0, 0.0, 5.0),
    (2.0, 0.0, 8.0),
]
SECOND = [
    (0.0, 0.0, 10.0),
    (1.0, 0.0, 5.0),
    (2.0, 0.0, 8.0),
]
TOLERANCES = [0.5, 1.0]

DATA = serialize_pair_gate_score_summary(FIRST, SECOND, TOLERANCES)
GOOD = json.loads(DATA)

FAIL = dict(GOOD)
FAIL.update(score_margin=100.0, pair_quality="fail", quality="fail")
FAIL_DATA = json.dumps(FAIL, separators=(",", ":")).encode("utf-8")


def _write(tmp_path, data, name="summary.json"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _dump(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _mutated(**changes):
    value = dict(GOOD)
    value.update(changes)
    return _dump(value)


def test_load_pair_gate_score_summary_exported():
    assert "load_pair_gate_score_summary" in crosspoint_mod.__all__
    assert (
        crosspoint_mod.load_pair_gate_score_summary is load_pair_gate_score_summary
    )


def test_roundtrip(tmp_path):
    path = _write(tmp_path, DATA)
    summary = load_pair_gate_score_summary(path)
    assert isinstance(summary, dict)
    assert list(summary.keys()) == [
        "coverage_product",
        "score_margin",
        "matched",
        "pair_quality",
        "quality",
    ]
    assert summary == GOOD
    assert summary["coverage_product"] == 1.0
    assert summary["score_margin"] == 0.0
    assert summary["matched"] == 3
    assert summary["pair_quality"] == "pass"
    assert summary["quality"] == "pass"


def test_roundtrip_failing_case(tmp_path):
    path = _write(tmp_path, FAIL_DATA)
    summary = load_pair_gate_score_summary(path)
    assert summary == FAIL
    assert summary["quality"] == "fail"


def test_load_returns_plain_dict_and_does_not_modify_file(tmp_path):
    target = tmp_path / "summary.json"
    target.write_bytes(DATA)
    path = str(target)
    first = load_pair_gate_score_summary(path)
    mtime = target.stat().st_mtime_ns
    second = load_pair_gate_score_summary(path)
    assert first == second
    assert first is not second
    assert target.stat().st_mtime_ns == mtime
    assert target.read_bytes() == DATA


def test_path_must_be_str(tmp_path):
    with pytest.raises(TypeError, match="path must be a str"):
        load_pair_gate_score_summary(None)
    for bad in (1, b"summary.json", 1.0, [], object()):
        with pytest.raises(TypeError):
            load_pair_gate_score_summary(bad)


def test_path_must_not_be_empty(tmp_path):
    with pytest.raises(ValueError, match="path must not be empty"):
        load_pair_gate_score_summary("")


def test_missing_file_raises_filenotfounderror(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pair_gate_score_summary(str(tmp_path / "missing.json"))


def test_directory_raises_isadirectoryerror(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_pair_gate_score_summary(str(tmp_path))


def test_bom_rejected(tmp_path):
    with pytest.raises(ValueError, match="BOM"):
        load_pair_gate_score_summary(_write(tmp_path, b"\xef\xbb\xbf" + DATA))


def test_trailing_newline_rejected(tmp_path):
    with pytest.raises(ValueError, match="trailing newline"):
        load_pair_gate_score_summary(_write(tmp_path, DATA + b"\n"))


def test_trailing_carriage_return_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, DATA + b"\r"))


def test_bad_utf8_rejected(tmp_path):
    with pytest.raises(ValueError, match="UTF-8"):
        load_pair_gate_score_summary(
            _write(tmp_path, b'{"coverage_product":\xff}')
        )


def test_invalid_json_rejected(tmp_path):
    with pytest.raises(ValueError, match="valid JSON"):
        load_pair_gate_score_summary(_write(tmp_path, b"not json"))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_constants_rejected(tmp_path, token):
    payload = _dump(dict(GOOD, quality="fail", pair_quality="fail",
                         score_margin=1.0)).replace(b"1.0", token.encode(), 1)
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, payload))


def test_top_level_must_be_object(tmp_path):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, b"[1,2,3]"))
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, b"1"))


def test_key_order_must_be_exact(tmp_path):
    reordered = {
        "score_margin": GOOD["score_margin"],
        "coverage_product": GOOD["coverage_product"],
        "matched": GOOD["matched"],
        "pair_quality": GOOD["pair_quality"],
        "quality": GOOD["quality"],
    }
    with pytest.raises(ValueError, match="order"):
        load_pair_gate_score_summary(_write(tmp_path, _dump(reordered)))


def test_missing_key_rejected(tmp_path):
    value = dict(GOOD)
    del value["matched"]
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _dump(value)))


def test_extra_key_rejected(tmp_path):
    value = dict(GOOD)
    value["extra"] = 1
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _dump(value)))


def test_duplicate_key_rejected(tmp_path):
    payload = DATA.replace(
        b'"quality":"pass"', b'"quality":"fail","quality":"pass"'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_pair_gate_score_summary(_write(tmp_path, payload))


@pytest.mark.parametrize(
    "change",
    [
        {"coverage_product": 1},
        {"coverage_product": True},
        {"coverage_product": "1.0"},
        {"coverage_product": -0.01},
        {"coverage_product": 1.0001},
        {"coverage_product": 1.0000001},
    ],
)
def test_bad_coverage_product_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _mutated(**change)))


@pytest.mark.parametrize(
    "change",
    [
        {"score_margin": 0},
        {"score_margin": False},
        {"score_margin": "0.0"},
        {"score_margin": -0.01},
        {"score_margin": 100.01},
        {"score_margin": 0.0000001},
    ],
)
def test_bad_score_margin_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _mutated(**change)))


@pytest.mark.parametrize("matched", [1.0, True, False, 0, -1, "3", None])
def test_bad_matched_rejected(tmp_path, matched):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(
            _write(tmp_path, _mutated(matched=matched))
        )


@pytest.mark.parametrize("field", ["pair_quality", "quality"])
def test_quality_strings_must_be_pass_or_fail(tmp_path, field):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _mutated(**{field: "ok"})))
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(
            _write(tmp_path, _mutated(**{field: "PASS"}))
        )


def test_pass_requires_pair_quality_pass(tmp_path):
    with pytest.raises(ValueError, match="pair_quality"):
        load_pair_gate_score_summary(
            _write(tmp_path, _mutated(pair_quality="fail"))
        )


def test_pass_requires_zero_margin(tmp_path):
    # quality="pass" but margin nonzero (even with pair_quality="pass")
    value = dict(
        GOOD, score_margin=1.0, pair_quality="pass", quality="pass"
    )
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _dump(value)))


def test_pass_with_pair_fail_and_zero_margin_rejected(tmp_path):
    value = dict(
        GOOD, score_margin=0.0, pair_quality="fail", quality="pass"
    )
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _dump(value)))


def test_pair_pass_nonzero_margin_quality_must_be_fail(tmp_path):
    # pair_quality pass, margin > 0 -> quality must be fail (valid fail)
    value = dict(
        GOOD, score_margin=1.0, pair_quality="pass", quality="fail"
    )
    summary = load_pair_gate_score_summary(_write(tmp_path, _dump(value)))
    assert summary["quality"] == "fail"


def test_fail_when_pair_pass_and_zero_margin_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, _mutated(quality="fail")))


def test_negative_zero_bytes_rejected(tmp_path):
    payload = b'{"coverage_product":-0.0,"score_margin":0.0,"matched":3,' \
        b'"pair_quality":"pass","quality":"pass"}'
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, payload))


def test_leading_whitespace_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, b" " + DATA))


def test_non_canonical_float_format_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(
            _write(tmp_path, DATA.replace(b"1.0", b"1.00", 1))
        )


def test_unicode_escaped_key_rejected(tmp_path):
    payload = DATA.replace(b'"coverage_product"', b'"coverage\\u005fproduct"')
    with pytest.raises(ValueError):
        load_pair_gate_score_summary(_write(tmp_path, payload))


def test_margin_boundaries_accepted(tmp_path):
    value = dict(
        GOOD, score_margin=0.5, pair_quality="fail", quality="fail"
    )
    summary = load_pair_gate_score_summary(
        _write(tmp_path, _dump(value), "half.json")
    )
    assert summary["score_margin"] == 0.5

    value = dict(
        GOOD, score_margin=100.0, pair_quality="fail", quality="fail"
    )
    summary = load_pair_gate_score_summary(
        _write(tmp_path, _dump(value), "hundred.json")
    )
    assert summary["score_margin"] == 100.0


def test_coverage_product_zero_accepted(tmp_path):
    value = dict(
        GOOD,
        coverage_product=0.0,
        score_margin=100.0,
        pair_quality="fail",
        quality="fail",
    )
    summary = load_pair_gate_score_summary(_write(tmp_path, _dump(value)))
    assert summary["coverage_product"] == 0.0
