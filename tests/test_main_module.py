"""Regression tests for the ``python -m ocean_sonar`` module entry point.

All subprocesses run with a working directory outside the source tree so the
tests do not depend on the current working directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CASES = [
    pytest.param(["version"], id="version"),
    pytest.param(["--help"], id="help"),
    pytest.param([], id="no-subcommand"),
]


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True)


def _source_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(REPO_ROOT)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath
    return env


def _module_cmd(args: list[str]) -> list[str]:
    return [sys.executable, "-m", "ocean_sonar", *args]


def _console_script_cmd(args: list[str]) -> list[str]:
    # Invoke ocean_sonar.cli.main exactly the way the installed
    # ``ocean-sonar-modeling`` console script does.
    code = "import sys; from ocean_sonar.cli import main; sys.exit(main(sys.argv[1:]))"
    return [sys.executable, "-c", code, *args]


@pytest.mark.parametrize("args", CASES)
def test_module_entry_matches_console_script(args: list[str], tmp_path: Path) -> None:
    env = _source_env()
    module = _run(_module_cmd(args), cwd=tmp_path, env=env)
    script = _run(_console_script_cmd(args), cwd=tmp_path, env=env)
    assert module.returncode == script.returncode
    assert module.stdout == script.stdout
    assert module.stderr == script.stderr


def test_module_entry_version_output(tmp_path: Path) -> None:
    result = _run(_module_cmd(["version"]), cwd=tmp_path, env=_source_env())
    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""


@pytest.fixture(scope="module")
def installed_venv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel and install it into a fresh venv; return the venv path."""
    base = tmp_path_factory.mktemp("installed")
    wheel_dir = base / "wheels"
    subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-build-isolation", "--no-deps",
            "--wheel-dir", str(wheel_dir), str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
    )
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, got {wheels}"

    venv_dir = base / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    venv_python = venv_dir / "bin" / "python"
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-index", str(wheels[0])],
        check=True,
        capture_output=True,
    )
    return venv_dir


def test_installed_wheel_contains_main_module(installed_venv: Path) -> None:
    result = _run(
        [str(installed_venv / "bin" / "python"), "-c",
         "import ocean_sonar.__main__ as m; print(m.__file__)"],
        cwd=installed_venv,
    )
    assert result.returncode == 0
    installed = Path(result.stdout.decode().strip())
    assert installed.name == "__main__.py"
    assert "site-packages" in installed.parts


@pytest.mark.parametrize("args", CASES)
def test_installed_module_entry_matches_console_script(args: list[str], installed_venv: Path, tmp_path: Path) -> None:
    bindir = installed_venv / "bin"
    module = _run([str(bindir / "python"), "-m", "ocean_sonar", *args], cwd=tmp_path)
    script = _run([str(bindir / "ocean-sonar-modeling"), *args], cwd=tmp_path)
    assert module.returncode == script.returncode
    assert module.stdout == script.stdout
    assert module.stderr == script.stderr


def test_installed_module_entry_version(installed_venv: Path, tmp_path: Path) -> None:
    result = _run(
        [str(installed_venv / "bin" / "python"), "-m", "ocean_sonar", "version"],
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""
