"""Tests for :func:`ocean_sonar.svp.batch` and ``load_batch_request``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ocean_sonar.svp as svp_mod
from ocean_sonar.svp import batch, load_batch_request, trace

Z = [0, 10, 20]
C = [1500, 1480, 1510]
RAYS = [(30.0, 0.02), (45.0, 0.01)]


def test_batch_success_exact_bytes():
    data = batch(Z, C, RAYS, 0.0, 1000.0)
    assert isinstance(data, bytes)
    x0, d0 = trace(Z, C, 30.0, 0.02, 0.0)
    x1, d1 = trace(Z, C, 45.0, 0.01, 0.0)
    expected = (
        b'{"results":[['
        + f"{x0:.6f}".encode()
        + b","
        + f"{d0:.6f}".encode()
        + b',true],['
        + f"{x1:.6f}".encode()
        + b","
        + f"{d1:.6f}".encode()
        + b',true]],"summary":{"count":2,"pass_count":2,'
        + b'"max_x":'
        + f"{max(x0, x1):.6f}".encode()
        + b',"quality":"pass"}}'
    )
    assert data == expected
    assert not data.endswith(b"\n")
    decoded = json.loads(data)
    assert list(decoded.keys()) == ["results", "summary"]
    assert list(decoded["summary"].keys()) == [
        "count",
        "pass_count",
        "max_x",
        "quality",
    ]


def test_batch_defaults_and_tuple_inputs():
    data = batch(tuple(Z), tuple(C), RAYS)
    decoded = json.loads(data)
    assert decoded["summary"] == {
        "count": 2,
        "pass_count": 2,
        "max_x": decoded["summary"]["max_x"],
        "quality": "pass",
    }
    assert isinstance(decoded["summary"]["count"], int)
    assert isinstance(decoded["summary"]["pass_count"], int)
    assert isinstance(decoded["summary"]["max_x"], float)


def test_batch_within_and_quality_fail():
    data = batch(Z, C, RAYS, 0.0, 6.0)
    decoded = json.loads(data)
    assert decoded["results"][0][2] is False
    assert decoded["results"][1][2] is True
    summary = decoded["summary"]
    assert summary["count"] == 2
    assert summary["pass_count"] == 1
    assert summary["quality"] == "fail"


def test_batch_within_is_inclusive_boundary():
    x, _ = trace(Z, C, 30.0, 0.02, 0.0)
    decoded = json.loads(batch(Z, C, [(30.0, 0.02)], 0.0, x))
    assert decoded["results"][0][2] is True
    assert decoded["summary"]["quality"] == "pass"
    decoded = json.loads(batch(Z, C, [(30.0, 0.02)], 0.0, x - 1e-9))
    assert decoded["results"][0][2] is False
    assert decoded["summary"]["quality"] == "fail"


def test_batch_max_x_is_float_and_largest():
    data = batch(Z, C, RAYS, 0.0, 0.0)
    decoded = json.loads(data)
    xs = [row[0] for row in decoded["results"]]
    assert decoded["summary"]["max_x"] == max(xs)


def test_batch_calls_trace_exactly_once_per_item_in_order(monkeypatch):
    calls = []

    def fake_trace(z, c, a, t, z0):
        calls.append((z, c, a, t, z0))
        return (float(len(calls)), float(len(calls)) / 2)

    monkeypatch.setattr(svp_mod, "trace", fake_trace)
    rays = [(1.0, 2.0), (3.0, 4.0), [5.0, 6.0]]
    data = batch("Z", "C", rays, 9.0, 1000.0)
    assert calls == [
        ("Z", "C", 1.0, 2.0, 9.0),
        ("Z", "C", 3.0, 4.0, 9.0),
        ("Z", "C", 5.0, 6.0, 9.0),
    ]
    decoded = json.loads(data)
    assert decoded["results"] == [
        [1.0, 0.5, True],
        [2.0, 1.0, True],
        [3.0, 1.5, True],
    ]
    assert decoded["summary"]["max_x"] == 3.0


def test_batch_does_not_modify_inputs():
    z = list(Z)
    c = list(C)
    rays = [list(item) for item in RAYS]
    batch(z, c, rays, 0.0, 1000.0)
    assert z == Z
    assert c == C
    assert rays == [list(item) for item in RAYS]


@pytest.mark.parametrize(
    "rays, expected",
    [
        pytest.param("x", TypeError, id="rays-str"),
        pytest.param({1: 2}, TypeError, id="rays-dict"),
        pytest.param(None, TypeError, id="rays-none"),
        pytest.param([], ValueError, id="rays-empty"),
        pytest.param([1], TypeError, id="item-int"),
        pytest.param(["ab"], TypeError, id="item-str"),
        pytest.param([None], TypeError, id="item-none"),
        pytest.param([(1.0,)], ValueError, id="item-length-1"),
        pytest.param([(1.0, 2.0, 3.0)], ValueError, id="item-length-3"),
        pytest.param([[1.0]], ValueError, id="list-item-length-1"),
    ],
)
def test_batch_rays_validation(rays, expected):
    with pytest.raises(expected):
        batch(Z, C, rays, 0.0, 1000.0)


@pytest.mark.parametrize(
    "limit, expected",
    [
        pytest.param(True, TypeError, id="limit-bool"),
        pytest.param(False, TypeError, id="limit-bool-false"),
        pytest.param("1", TypeError, id="limit-str"),
        pytest.param(None, TypeError, id="limit-none"),
        pytest.param(float("nan"), ValueError, id="limit-nan"),
        pytest.param(float("inf"), ValueError, id="limit-inf"),
        pytest.param(float("-inf"), ValueError, id="limit-neg-inf"),
        pytest.param(-0.01, ValueError, id="limit-negative-float"),
        pytest.param(-1, ValueError, id="limit-negative-int"),
    ],
)
def test_batch_limit_validation(limit, expected):
    with pytest.raises(expected):
        batch(Z, C, RAYS, 0.0, limit)


def test_batch_limit_zero_and_large_accepted():
    decoded = json.loads(batch(Z, C, RAYS, 0.0, 0))
    assert decoded["summary"]["pass_count"] == 0
    decoded = json.loads(batch(Z, C, RAYS, 0.0, 10**9))
    assert decoded["summary"]["pass_count"] == 2


def test_batch_validation_order_container_first():
    with pytest.raises(TypeError, match="rays"):
        batch(Z, C, "x", 0.0, -1.0)


def test_batch_validation_order_nonempty_before_limit():
    with pytest.raises(ValueError, match="non-empty"):
        batch(Z, C, [], 0.0, -1.0)


def test_batch_validation_order_items_before_limit():
    with pytest.raises(TypeError, match="rays elements"):
        batch(Z, C, [1], 0.0, -1.0)
    with pytest.raises(ValueError, match="length 2"):
        batch(Z, C, [(1.0,)], 0.0, -1.0)


def test_batch_first_bad_item_reported_first():
    good = (1.0, 2.0)
    with pytest.raises(ValueError, match="length 2"):
        batch(Z, C, [good, (3.0,), (4.0,)], 0.0, 1000.0)
    with pytest.raises(TypeError, match="rays elements"):
        batch(Z, C, [9, good], 0.0, 1000.0)


def test_batch_trace_exceptions_propagate_unchanged():
    # trace validates a, t, z0 itself: negative t is a ValueError.
    with pytest.raises(ValueError, match="t must be positive"):
        batch(Z, C, [(30.0, -1.0)], 0.0, 1000.0)
    # A non-numeric angle is a TypeError raised by trace, not batch.
    with pytest.raises(TypeError, match="a must be"):
        batch(Z, C, [("x", 1.0)], 0.0, 1000.0)


def test_batch_trace_error_aborts_before_later_items(monkeypatch):
    calls = []

    def fake_trace(z, c, a, t, z0):
        calls.append(a)
        if a == 3.0:
            raise ValueError("total internal reflection")
        return (1.0, 2.0)

    monkeypatch.setattr(svp_mod, "trace", fake_trace)
    with pytest.raises(ValueError, match="total internal reflection"):
        batch(Z, C, [(1.0, 1.0), (3.0, 1.0), (5.0, 1.0)], 0.0, 1000.0)
    assert calls == [1.0, 3.0]


def write_request(path: Path, **overrides):
    document = {
        "z": Z,
        "c": C,
        "rays": [list(item) for item in RAYS],
        "z0": 0.0,
        "limit": 1000.0,
    }
    document.update(overrides)
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return str(path)


def test_load_batch_request_success(tmp_path):
    path = write_request(tmp_path / "request.json")
    request = load_batch_request(path)
    assert list(request.keys()) == ["z", "c", "rays", "z0", "limit"]
    assert request["z"] == Z
    assert request["c"] == C
    assert request["rays"] == [list(item) for item in RAYS]
    assert request["z0"] == 0.0
    assert request["limit"] == 1000.0


def test_load_batch_request_roundtrip_with_batch(tmp_path):
    path = write_request(tmp_path / "request.json")
    request = load_batch_request(path)
    assert batch(**request) == batch(Z, C, [list(item) for item in RAYS], 0.0, 1000.0)


def test_load_batch_request_non_str_path():
    with pytest.raises(TypeError, match="path must be a str"):
        load_batch_request(123)


def test_load_batch_request_empty_path():
    with pytest.raises(ValueError, match="path must not be empty"):
        load_batch_request("")


def test_load_batch_request_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_batch_request(str(tmp_path / "missing.json"))


def test_load_batch_request_directory(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_batch_request(str(tmp_path))


def test_load_batch_request_invalid_utf8(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="valid UTF-8"):
        load_batch_request(str(path))


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"{", id="truncated"),
        pytest.param(b"[1,2,3]", id="array"),
        pytest.param(b'"hello"', id="string"),
        pytest.param(b"123", id="number"),
        pytest.param(b"null", id="null"),
    ],
)
def test_load_batch_request_illegal_content(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        load_batch_request(str(path))


def test_load_batch_request_wrong_key_order(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        '{"z":[0],"c":[1500],"rays":[[30.0,1.0]],'
        '"limit":1000.0,"z0":0.0}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="keys exactly"):
        load_batch_request(str(path))


def test_load_batch_request_missing_key(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        '{"z":[0],"c":[1500],"rays":[[30.0,1.0]],"z0":0.0}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="keys exactly"):
        load_batch_request(str(target))


def test_load_batch_request_extra_key(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        '{"z":[0],"c":[1500],"rays":[[30.0,1.0]],'
        '"z0":0.0,"limit":1000.0,"extra":1}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="keys exactly"):
        load_batch_request(str(target))


def test_load_batch_request_duplicate_key(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        '{"z":[0],"z":[0],"c":[1500],"rays":[[30.0,1.0]],'
        '"z0":0.0,"limit":1000.0}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_batch_request(str(target))


def test_load_batch_request_rejects_nan_constant(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        '{"z":[0],"c":[1500],"rays":[[30.0,1.0]],'
        '"z0":0.0,"limit":NaN}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid JSON constant"):
        load_batch_request(str(target))


def test_load_batch_request_does_not_validate_values(tmp_path):
    # Value-level validation belongs to batch(); the loader accepts any
    # JSON values under the correctly ordered keys.
    target = tmp_path / "loose.json"
    target.write_text(
        '{"z":"bad","c":null,"rays":{},"z0":[],"limit":"x"}',
        encoding="utf-8",
    )
    request = load_batch_request(str(target))
    assert request == {"z": "bad", "c": None, "rays": {}, "z0": [], "limit": "x"}


def test_load_batch_request_file_not_modified(tmp_path):
    path = write_request(tmp_path / "request.json")
    before = Path(path).read_bytes()
    load_batch_request(path)
    assert Path(path).read_bytes() == before
