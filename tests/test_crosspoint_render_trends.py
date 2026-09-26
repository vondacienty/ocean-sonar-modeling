"""Tests for crosspoint.render_trends."""

import json
import math

import pytest

import ocean_sonar.crosspoint as crosspoint_mod
from ocean_sonar.crosspoint import (
    aggregate_trends,
    load_trend,
    render_trends,
)


def _q6(value):
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def write_trend(path, count, changes, degraded, coverage_delta, score_delta,
                worst, quality):
    """Write a canonical serialize_trend-compatible JSON trend file."""
    document = {
        "count": int(count),
        "changes": int(changes),
        "degraded": int(degraded),
        "coverage_delta": _q6(coverage_delta),
        "score_delta": _q6(score_delta),
        "worst": [
            int(worst[0]),
            int(worst[1]),
            int(worst[2]),
            _q6(worst[3]),
            _q6(worst[4]),
        ],
        "quality": quality,
    }
    path.write_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return str(path)


@pytest.fixture
def two_trend_paths(tmp_path):
    # File 0: one change, +0.1 coverage, +2.0 score, no degradation.
    p0 = write_trend(
        tmp_path / "trend_0.json",
        2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
    )
    # File 1: one change, -0.1 coverage, -1.0 score, pass -> fail.
    p1 = write_trend(
        tmp_path / "trend_1.json",
        2, 1, 1, -0.1, -1.0, (1, 0, 0, -0.1, -1.0), "fail",
    )
    return [p0, p1]


@pytest.fixture
def weighted_trend_paths(tmp_path):
    # File 0: 2 changes, cd=0.1, sd=2.0.
    p0 = write_trend(
        tmp_path / "trend_w0.json",
        3, 2, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
    )
    # File 1: 3 changes, cd=-0.2, sd=-1.0.
    p1 = write_trend(
        tmp_path / "trend_w1.json",
        2, 3, 1, -0.2, -1.0, (1, 0, 0, -0.2, -1.0), "fail",
    )
    return [p0, p1]


def test_render_trends_exported():
    assert hasattr(crosspoint_mod, "render_trends")
    assert "render_trends" in crosspoint_mod.__all__
    assert crosspoint_mod.render_trends is render_trends
    # Sibling APIs remain exported.
    assert "aggregate_trends" in crosspoint_mod.__all__
    assert "load_trend" in crosspoint_mod.__all__


def test_render_trends_three_lines(two_trend_paths):
    text = render_trends(two_trend_paths)
    assert isinstance(text, str)
    assert not text.endswith("\n")
    lines = text.split("\n")
    assert len(lines) == 3
    assert lines[0].startswith("TRENDS=")
    assert lines[1].startswith("FILES=")
    assert lines[2].startswith("WORST=")


def test_render_trends_values(two_trend_paths):
    # K = 2; p(0, cov) = 0.1/2 = 0.05, p(0, score) = 2/2 = 1.0;
    # p(1, cov) = -0.05, p(1, score) = -0.5;
    # u(cov) = sqrt(((0.1-0)^2 + (-0.1-0)^2)/2) = 0.1;
    # u(score) = sqrt(((2-0.5)^2 + (-1-0.5)^2)/2) = 1.5.
    text = render_trends(two_trend_paths)
    assert text == (
        "TRENDS=2,2,1,0.000000,0.500000,fail\n"
        "FILES=0:0.050000:1.000000|1:-0.050000:-0.500000;"
        "RMSE=0.100000,1.500000;WORST_FILE=1\n"
        "WORST=1,1,0,0,-0.100000,-1.000000"
    )


def test_render_trends_weighted(weighted_trend_paths):
    # K = 5; aggregate cd = (0.2 - 0.6)/5 = -0.08, sd = (4 - 3)/5 = 0.2.
    # p: file0 cov 0.2/5 = 0.04, score 4/5 = 0.8;
    #    file1 cov -0.6/5 = -0.12, score -3/5 = -0.6.
    text = render_trends(weighted_trend_paths)
    lines = text.split("\n")
    assert lines[0] == "TRENDS=2,5,1,-0.080000,0.200000,fail"
    assert lines[1] == (
        "FILES=0:0.040000:0.800000|1:-0.120000:-0.600000;"
        "RMSE=0.146969,1.469694;WORST_FILE=1"
    )
    assert lines[2] == "WORST=1,1,0,0,-0.200000,-1.000000"

    # Independently recompute the spreads from the loaded trends.
    trends = [load_trend(p) for p in weighted_trend_paths]
    aggregate = aggregate_trends(weighted_trend_paths)
    k = aggregate["changes"]
    for x, rendered in (
        ("coverage_delta", "0.146969"),
        ("score_delta", "1.469694"),
    ):
        u = math.sqrt(
            math.fsum(
                t["changes"] * (t[x] - aggregate[x]) ** 2 for t in trends
            ) / k
        )
        assert format(_q6(u), ".6f") == rendered


def test_render_trends_identical_files_zero_spread(tmp_path):
    paths = []
    for k in range(2):
        paths.append(
            write_trend(
                tmp_path / f"same_{k}.json",
                2, 1, 0, 0.1, 2.0, (1, 0, 0, 0.1, 2.0), "pass",
            )
        )
    text = render_trends(paths)
    lines = text.split("\n")
    assert lines[0] == "TRENDS=2,2,0,0.100000,2.000000,pass"
    assert lines[1] == (
        "FILES=0:0.050000:1.000000|1:0.050000:1.000000;"
        "RMSE=0.000000,0.000000;WORST_FILE=0"
    )
    assert lines[2] == "WORST=0,1,0,0,0.100000,2.000000"
    # Zero spreads and shares render without a negative sign.
    assert "-0.000000" not in text


def test_render_trends_worst_file_tie_breaks_on_coverage_then_j(tmp_path):
    # Equal score shares: file 0 has the smaller coverage share, so it
    # wins; another pair with both shares equal resolves to the smallest j.
    paths_equal_score = [
        write_trend(
            tmp_path / "es_0.json",
            2, 1, 0, -0.2, 1.0, (1, 0, 0, -0.2, 1.0), "pass",
        ),
        write_trend(
            tmp_path / "es_1.json",
            2, 1, 0, -0.1, 1.0, (1, 0, 0, -0.1, 1.0), "pass",
        ),
    ]
    line = render_trends(paths_equal_score).split("\n")[1]
    assert line.endswith("WORST_FILE=0")

    paths_all_equal = [
        write_trend(
            tmp_path / "eq_0.json",
            2, 1, 0, 0.1, 1.0, (1, 0, 0, 0.1, 1.0), "pass",
        ),
        write_trend(
            tmp_path / "eq_1.json",
            2, 1, 0, 0.1, 1.0, (1, 0, 0, 0.1, 1.0), "pass",
        ),
    ]
    line = render_trends(paths_all_equal).split("\n")[1]
    assert line.endswith("WORST_FILE=0")


def test_render_trends_worst_file_uses_unrounded_shares(tmp_path):
    # K = 8: file 0 and file 1 each have 1 change, file 2 has 6.
    # Score shares: 0.000009/8 = 0.000001125 for file 0,
    # 0.000008/8 = 0.000001 for file 1; both round to "0.000001", so a
    # rounded comparison would tie and pick j = 0, while the unrounded
    # minimum is file 1.
    paths = [
        write_trend(
            tmp_path / "r0.json",
            2, 1, 0, 0.0, 0.000009, (1, 0, 0, 0.0, 0.000009), "pass",
        ),
        write_trend(
            tmp_path / "r1.json",
            2, 1, 0, 0.0, 0.000008, (1, 0, 0, 0.0, 0.000008), "pass",
        ),
        write_trend(
            tmp_path / "r2.json",
            2, 6, 0, 0.0, 1.0, (1, 0, 0, 0.0, 1.0), "pass",
        ),
    ]
    line = render_trends(paths).split("\n")[1]
    assert "0:0.000000:0.000001|1:0.000000:0.000001" in line
    assert line.endswith("WORST_FILE=1")


def test_render_trends_calls_aggregate_once_and_loads_each_path(
    monkeypatch, two_trend_paths
):
    aggregate_calls = []
    load_calls = []
    original_aggregate = crosspoint_mod.aggregate_trends
    original_load = crosspoint_mod.load_trend

    def counting_aggregate(paths):
        aggregate_calls.append(list(paths))
        return original_aggregate(paths)

    def counting_load(path):
        load_calls.append(path)
        return original_load(path)

    monkeypatch.setattr(crosspoint_mod, "aggregate_trends", counting_aggregate)
    monkeypatch.setattr(crosspoint_mod, "load_trend", counting_load)

    paths = list(two_trend_paths)
    render_trends(paths)

    assert aggregate_calls == [paths]
    # aggregate_trends itself loads every path once, then render_trends
    # loads every path once more, in input order each time.
    assert load_calls == paths + paths


def test_render_trends_validation_passthrough():
    with pytest.raises(TypeError, match="^paths must be a list or tuple$"):
        render_trends({})
    with pytest.raises(ValueError, match="at least 2 items"):
        render_trends(["only"])
    with pytest.raises(TypeError, match=r"^paths\[1\]: must be a str$"):
        render_trends(["a", 5])
    with pytest.raises(ValueError, match=r"^paths\[0\]: must not be empty$"):
        render_trends(["", "b"])


def test_render_trends_load_exception_propagates(tmp_path):
    missing = str(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        render_trends([missing, missing])

    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{")
    with pytest.raises(ValueError):
        render_trends([str(bad), str(bad)])


def test_render_trends_does_not_modify_inputs_or_files(two_trend_paths):
    paths = list(two_trend_paths)
    before = [open(p, "rb").read() for p in paths]
    render_trends(paths)
    assert paths == two_trend_paths
    assert [open(p, "rb").read() for p in paths] == before
