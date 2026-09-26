"""End-to-end tests for the ``product-quality`` CLI subcommand.

The subcommand is exercised both through ``python -m ocean_sonar``
subprocesses (byte-exact stdout/stderr/exit-code assertions) and through
in-process ``ocean_sonar.cli.main`` calls (call-count semantics).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import ocean_sonar.cli as cli_mod
from ocean_sonar.product import build

REPO_ROOT = Path(__file__).resolve().parents[1]

POINTS = [
    (0.0, 0.0, 10.0),
    (0.5, 0.5, 12.0),
    (1.5, 1.5, 8.0),
    (1.9, 1.9, 9.0),
]
BOUNDS = (0.0, 0.0, 2.0, 2.0)
RESOLUTIONS = (1.0, 2.0)
CROSSINGS = [(0.0, 0.0, 10.0, 10.2), (1.0, 1.0, 5.0, 4.8)]


def _expected_bytes(product):
    total = sum(layer["quality"]["total"] for layer in product["layers"])
    valid = sum(layer["quality"]["valid"] for layer in product["layers"])
    terrain_exceed = sum(
        layer["quality"]["slope_exceed"] + layer["quality"]["roughness_exceed"]
        for layer in product["layers"]
    )
    unknown = sum(
        layer["substrate"]["counts"]["unknown"] for layer in product["layers"]
    )

    def key(index):
        layer = product["layers"][index]
        return (
            layer["substrate"]["counts"]["unknown"],
            layer["quality"]["slope_exceed"]
            + layer["quality"]["roughness_exceed"],
            -float(layer["quality"]["valid"] / layer["quality"]["total"]),
            -index,
        )

    worst = max(range(len(product["layers"])), key=key)
    summary = {
        "layers": len(product["layers"]),
        "total": total,
        "valid": valid,
        "coverage": round(float(valid / total), 6),
        "terrain_exceed": terrain_exceed,
        "unknown": unknown,
        "worst": worst,
        "crosspoint": product["crosspoint"]["quality"],
        "quality": product["overall"],
    }
    return (
        json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_product(path):
    from ocean_sonar.product import serialize

    product = build(POINTS, BOUNDS, RESOLUTIONS, CROSSINGS)
    path.write_bytes(serialize(product))
    return str(path), product


def run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "ocean_sonar", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
    )


def test_product_quality_success_exact_output(tmp_path):
    product_path, product = write_product(tmp_path / "product.json")
    result = run_cli(["product-quality", product_path], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == _expected_bytes(product)


def test_product_quality_input_file_not_modified(tmp_path):
    product_path, _ = write_product(tmp_path / "product.json")
    before = (tmp_path / "product.json").read_bytes()
    result = run_cli(["product-quality", product_path], cwd=tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "product.json").read_bytes() == before


def test_product_quality_calls_function_exactly_once(tmp_path, monkeypatch, capsys):
    product_path, product = write_product(tmp_path / "product.json")
    calls = []
    real_function = cli_mod._product_quality_report

    def spy(argument):
        calls.append(argument)
        return real_function(argument)

    monkeypatch.setattr(cli_mod, "_product_quality_report", spy)
    assert cli_mod.main(["product-quality", product_path]) == 0
    assert calls == [product_path]
    assert capsys.readouterr().out == _expected_bytes(product).decode("utf-8")


def test_product_quality_missing_file(tmp_path):
    missing = str(tmp_path / "missing.json")
    result = run_cli(["product-quality", missing], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR FileNotFoundError: ")
    assert b"missing.json" in result.stderr


def test_product_quality_corrupt_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    result = run_cli(["product-quality", str(bad)], cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.startswith(b"ERROR ValueError: ")


def test_product_quality_missing_argument_exit_code_2(tmp_path):
    result = run_cli(["product-quality"], cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == b""


def test_product_quality_extra_argument_exit_code_2(tmp_path):
    result = run_cli(
        ["product-quality", "a.json", "b.json"], cwd=tmp_path
    )
    assert result.returncode == 2
    assert result.stdout == b""
