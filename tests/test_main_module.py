"""Regression tests for the ``python -m ocean_sonar`` module entry point.

These tests build the wheel, install it into an isolated virtualenv, and run
both entry points (``python -m ocean_sonar`` and the ``ocean-sonar-modeling``
console script) as subprocesses from a working directory outside the source
tree, so they do not depend on the current working directory.
"""

from __future__ import annotations

import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True)


@pytest.fixture(scope="session")
def installed_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Build the wheel and install it into a fresh virtualenv."""
    work = tmp_path_factory.mktemp("installed-env")
    wheel_dir = work / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(PROJECT_ROOT),
        ],
        check=True,
        capture_output=True,
    )
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    env_dir = work / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    python = env_dir / "bin" / "python"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", str(wheels[0])],
        check=True,
        capture_output=True,
    )
    return {
        "python": python,
        "console_script": env_dir / "bin" / "ocean-sonar-modeling",
        "wheel": wheels[0],
        "cwd": work,
    }


def test_wheel_contains_main_module(installed_env: dict[str, Path]) -> None:
    with zipfile.ZipFile(installed_env["wheel"]) as zf:
        assert "ocean_sonar/__main__.py" in zf.namelist()


def test_main_module_discoverable_after_install(installed_env: dict[str, Path]) -> None:
    result = _run(
        [
            str(installed_env["python"]),
            "-c",
            "import ocean_sonar.__main__ as m; print(m.__file__)",
        ],
        cwd=installed_env["cwd"],
    )
    assert result.returncode == 0
    assert result.stdout.decode().strip().endswith("ocean_sonar/__main__.py")


@pytest.mark.parametrize("args", [["version"], ["--help"], []])
def test_module_entry_matches_console_script(
    installed_env: dict[str, Path], args: list[str]
) -> None:
    cwd = installed_env["cwd"]
    via_module = _run(
        [str(installed_env["python"]), "-m", "ocean_sonar", *args], cwd=cwd
    )
    via_script = _run([str(installed_env["console_script"]), *args], cwd=cwd)

    assert via_module.returncode == via_script.returncode == 0
    assert via_module.stdout == via_script.stdout
    assert via_module.stderr == via_script.stderr


def test_version_output(installed_env: dict[str, Path]) -> None:
    result = _run(
        [str(installed_env["python"]), "-m", "ocean_sonar", "version"],
        cwd=installed_env["cwd"],
    )
    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""


def test_main_forwards_argv_and_returns_int() -> None:
    import ocean_sonar.__main__ as module

    received: list[list[str] | None] = []

    def fake_main(argv: list[str] | None = None) -> int:
        received.append(argv)
        return 7

    original = module._cli_main
    module._cli_main = fake_main
    try:
        argv = ["version"]
        assert module.main(argv) == 7
        assert received == [argv]
        assert received[0] is argv  # argv passed through unchanged
    finally:
        module._cli_main = original


def test_main_delegates_to_cli_main() -> None:
    import ocean_sonar.__main__ as module
    from ocean_sonar.cli import main as cli_main

    assert module._cli_main is cli_main
