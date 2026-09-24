"""Regression tests for the ``python -m ocean_sonar`` module entry point.

These tests guard *installation isolation*:

* the wheel is built with the current interpreter and installed with
  ``pip install --no-index`` into a brand new virtual environment;
* every subprocess is launched from a working directory **outside** the
  source tree with a scrubbed environment (no ``PYTHONPATH`` / user
  site-packages / startup hooks), so a result can only come from the
  installed wheel, never from the source tree or packages preinstalled
  on the machine;
* the installed ``python -m ocean_sonar`` and the installed
  ``ocean-sonar-modeling`` console script must behave byte-for-byte
  identically for ``version``, ``--help`` and no subcommand.

Both POSIX and Windows venv layouts are supported.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = sys.platform == "win32"

# Environment variables that could make a Python process import code from
# somewhere other than the venv (a source tree, user site-packages, a
# relocated interpreter, ...). They are dropped from every subprocess.
_INJECTABLE_ENV_VARS = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "PYTHONEXECUTABLE",
        "__PYVENV_LAUNCHER__",
        "VIRTUAL_ENV",
    }
)

CASES = [
    pytest.param(["version"], id="version"),
    pytest.param(["--help"], id="help"),
    pytest.param([], id="no-subcommand"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _run(
    cmd: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True)


def _run_checked(
    cmd: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    result = _run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{result.stdout.decode(errors='replace')}\n"
            f"--- stderr ---\n{result.stderr.decode(errors='replace')}"
        )
    return result


def _scrubbed_env(scripts_dir: Path | None = None) -> dict[str, str]:
    """An environment that cannot inject source code into Python subprocesses.

    * source-injecting ``PYTHON*`` variables are removed;
    * the user site-packages directory (which may contain preinstalled
      packages on the host) is disabled via ``PYTHONNOUSERSITE=1``;
    * only the venv scripts directory is put at the front of ``PATH``
      (system entries are kept because the Windows launcher needs them).
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _INJECTABLE_ENV_VARS
    }
    env["PYTHONNOUSERSITE"] = "1"
    path_entries: list[str] = []
    if scripts_dir is not None:
        path_entries.append(str(scripts_dir))
    path_entries.append(os.environ.get("PATH", os.defpath))
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def _venv_scripts_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if IS_WINDOWS else "bin")


def _venv_python(venv_dir: Path) -> Path:
    return _venv_scripts_dir(venv_dir) / ("python.exe" if IS_WINDOWS else "python")


def _console_script(venv_dir: Path) -> Path:
    return _venv_scripts_dir(venv_dir) / (
        "ocean-sonar-modeling.exe" if IS_WINDOWS else "ocean-sonar-modeling"
    )


def _assert_outside_repo(path: Path) -> None:
    resolved = path.resolve()
    assert resolved != REPO_ROOT.resolve()
    assert not resolved.is_relative_to(REPO_ROOT.resolve()), (
        f"subprocess working directory {resolved} must be outside the source tree"
    )


def _site_packages(venv_dir: Path, env: dict[str, str], cwd: Path) -> Path:
    result = _run_checked(
        [
            str(_venv_python(venv_dir)),
            "-c",
            "import site; print(site.getsitepackages()[0])",
        ],
        cwd=cwd,
        env=env,
    )
    return Path(result.stdout.decode().strip()).resolve()


# --------------------------------------------------------------------------- #
# Source-level contract for ocean_sonar/__main__.py
# --------------------------------------------------------------------------- #


def test_main_module_source_contract() -> None:
    text = (REPO_ROOT / "ocean_sonar" / "__main__.py").read_text(encoding="utf-8")
    assert "def main(argv: list[str] | None = None) -> int:" in text
    assert "sys.exit(main())" in text


def test_main_forwards_argv_to_cli_once_and_returns_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ocean_sonar import __main__ as entry

    calls: list[list[str] | None] = []

    def fake_cli_main(argv: list[str] | None) -> int:
        calls.append(argv)
        return 42

    monkeypatch.setattr(entry, "_cli_main", fake_cli_main)

    argv = ["version"]
    assert entry.main(argv) == 42
    assert calls == [argv]  # forwarded verbatim, exactly once

    assert entry.main(None) == 42
    assert calls[-1] is None  # None must be forwarded unchanged


# --------------------------------------------------------------------------- #
# Wheel build + fresh-venv installation
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def installed_venv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel with this interpreter and install it offline in a venv."""
    base = tmp_path_factory.mktemp("install-isolation")
    work_dir = base / "work"
    work_dir.mkdir()
    wheel_dir = base / "wheels"

    _run_checked(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(REPO_ROOT),
        ],
        cwd=work_dir,
        env=_scrubbed_env(),
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    venv_dir = base / "venv"
    venv.EnvBuilder(
        system_site_packages=False, with_pip=True, clear=True
    ).create(str(venv_dir))

    python_exe = _venv_python(venv_dir)
    console_exe = _console_script(venv_dir)
    assert python_exe.is_file(), f"venv interpreter missing: {python_exe}"

    _run_checked(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(wheels[0]),
        ],
        cwd=work_dir,
        env=_scrubbed_env(_venv_scripts_dir(venv_dir)),
    )
    assert console_exe.is_file(), f"console script missing: {console_exe}"
    return venv_dir


# --------------------------------------------------------------------------- #
# Isolation probes
# --------------------------------------------------------------------------- #


def test_clean_venv_without_wheel_cannot_import_package(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Negative control: scrubbed env + fresh venv must not see the package.

    If the host leaked the source tree via PYTHONPATH or provided a
    preinstalled copy via user/system site-packages, this would import
    successfully and the isolation tests below would be meaningless.
    """
    base = tmp_path_factory.mktemp("empty-venv")
    cwd = base / "run"
    cwd.mkdir()
    _assert_outside_repo(cwd)

    empty_venv = base / "venv"
    venv.EnvBuilder(system_site_packages=False, with_pip=False, clear=True).create(
        str(empty_venv)
    )
    scripts_dir = _venv_scripts_dir(empty_venv)

    result = _run(
        [str(_venv_python(empty_venv)), "-c", "import ocean_sonar"],
        cwd=cwd,
        env=_scrubbed_env(scripts_dir),
    )
    assert result.returncode != 0
    assert b"ModuleNotFoundError" in result.stderr


def test_installed_package_loads_from_venv_site_packages(
    installed_venv: Path, tmp_path: Path
) -> None:
    _assert_outside_repo(tmp_path)
    scripts_dir = _venv_scripts_dir(installed_venv)
    env = _scrubbed_env(scripts_dir)

    site_packages = _site_packages(installed_venv, env, tmp_path)
    repo_root = REPO_ROOT.resolve()

    probe = (
        "import json, os, sys\n"
        "import ocean_sonar\n"
        "import ocean_sonar.__main__ as main_mod\n"
        "print(json.dumps({"
        "'cwd': os.getcwd(), "
        "'package_file': ocean_sonar.__file__, "
        "'main_file': main_mod.__file__, "
        "'sys_path': [p for p in sys.path if p], "
        "}))"
    )
    result = _run_checked(
        [str(_venv_python(installed_venv)), "-c", probe],
        cwd=tmp_path,
        env=env,
    )
    data: dict[str, Any] = json.loads(result.stdout.decode())

    for key in ("package_file", "main_file"):
        loaded = Path(data[key]).resolve()
        assert loaded.is_relative_to(site_packages), (
            f"{key}={loaded} is not under venv site-packages {site_packages}"
        )
        assert not loaded.is_relative_to(repo_root), (
            f"{key}={loaded} was imported from the source tree {repo_root}"
        )

    # The source tree must not be reachable through sys.path either.
    assert str(repo_root) not in {
        str(Path(entry).resolve()) for entry in data["sys_path"]
    }
    assert not Path(data["cwd"]).resolve().is_relative_to(repo_root)


# --------------------------------------------------------------------------- #
# Installed entry-point behaviour
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("args", CASES)
def test_installed_python_m_matches_console_script(
    args: list[str], installed_venv: Path, tmp_path: Path
) -> None:
    _assert_outside_repo(tmp_path)
    env = _scrubbed_env(_venv_scripts_dir(installed_venv))

    module = _run(
        [str(_venv_python(installed_venv)), "-m", "ocean_sonar", *args],
        cwd=tmp_path,
        env=env,
    )
    script = _run(
        [str(_console_script(installed_venv)), *args], cwd=tmp_path, env=env
    )

    assert (
        module.returncode,
        module.stdout,
        module.stderr,
    ) == (
        script.returncode,
        script.stdout,
        script.stderr,
    )


def test_installed_version_output_via_both_entry_points(
    installed_venv: Path, tmp_path: Path
) -> None:
    _assert_outside_repo(tmp_path)
    env = _scrubbed_env(_venv_scripts_dir(installed_venv))

    for cmd in (
        [str(_venv_python(installed_venv)), "-m", "ocean_sonar", "version"],
        [str(_console_script(installed_venv)), "version"],
    ):
        result = _run(cmd, cwd=tmp_path, env=env)
        assert result.returncode == 0
        assert result.stdout == b"0.1.0\n"
        assert result.stderr == b""


@pytest.mark.parametrize("args", [["--help"], []])
def test_installed_help_exits_clean_via_both_entry_points(
    args: list[str], installed_venv: Path, tmp_path: Path
) -> None:
    _assert_outside_repo(tmp_path)
    env = _scrubbed_env(_venv_scripts_dir(installed_venv))

    for cmd in (
        [str(_venv_python(installed_venv)), "-m", "ocean_sonar", *args],
        [str(_console_script(installed_venv)), *args],
    ):
        result = _run(cmd, cwd=tmp_path, env=env)
        assert result.returncode == 0
        assert result.stderr == b""
        assert b"ocean-sonar-modeling" in result.stdout
