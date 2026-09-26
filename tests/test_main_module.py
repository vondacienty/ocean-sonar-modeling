"""Installation-isolation regression tests for the ``ocean_sonar`` entry points.

These tests prove that an actually *installed* copy of the project (not the
source checkout) is what runs after installation:

* a wheel is built with the current interpreter and installed with
  ``pip install --no-index`` into a freshly created venv;
* every tested subprocess is started from a working directory outside the
  source tree with an environment that cannot inject the checkout
  (``PYTHONPATH`` and friends removed, user site-packages disabled);
* ``import ocean_sonar.__main__`` after installation is resolved from the
  venv's ``site-packages`` and never from ``REPO_ROOT``;
* ``python -m ocean_sonar`` and the installed ``ocean-sonar-modeling``
  console script produce byte-for-byte identical stdout/stderr/exit code for
  ``version``, ``--help`` and no subcommand;
* ``version`` prints exactly ``0.1.0\\n`` on stdout, nothing on stderr, and
  exits 0.

Negative-control cases deliberately reintroduce ``PYTHONPATH``/cwd leakage to
show the isolation assertions have teeth, so the suite cannot pass merely
because the source tree happens to be importable or the cwd is the checkout.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from email.parser import HeaderParser
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = REPO_ROOT / "ocean_sonar" / "__main__.py"

# Invocations used for the module/console-script equivalence matrix.
CASES = [
    pytest.param(["version"], id="version"),
    pytest.param(["--help"], id="help"),
    pytest.param([], id="no-subcommand"),
    pytest.param(["render-trends", "only-one.json"], id="render-trends-single-path"),
    pytest.param(
        ["render-trends", "missing-a.json", "missing-b.json"],
        id="render-trends-missing-files",
    ),
]

# Environment variables that can inject the source tree (or arbitrary code)
# into a launched interpreter. None of them is inherited by test subprocesses.
_INJECTABLE_ENV_VARS = (
    "PYTHONPATH",      # extra sys.path entries
    "PYTHONHOME",      # relocates prefix / standard library
    "PYTHONSTARTUP",  # executes a file at interactive startup
    "PYTHONUSERBASE",  # relocates the user site-packages directory
)


def _scrubbed_env(
    scripts_dir: Path,
    *,
    scrub: tuple[str, ...] = _INJECTABLE_ENV_VARS,
) -> dict[str, str]:
    """An environment that cannot inject the source tree into a subprocess.

    Every name in ``scrub`` is removed outright (rather than emptied) and the
    resulting mapping is asserted not to carry it, even under a differently
    cased spelling: on Windows environment names are case-insensitive, so a
    leftover ``pythonpath`` would defeat the removal of ``PYTHONPATH``.
    """
    scrub_upper = {name.upper() for name in scrub}
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in scrub_upper
    }
    leaked = [key for key in env if key.upper() in scrub_upper]
    assert not leaked, f"scrubbed environment variables survived: {leaked}"
    # Belt and braces: even a PYTHONUSERBASE slipped through elsewhere, the
    # user site-packages must not shadow the venv (no preinstalled packages).
    env["PYTHONNOUSERSITE"] = "1"
    # Do not litter the checkout (the cwd-leak negative control imports from
    # it) or the venv with __pycache__ directories.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # CLI output here is ASCII, but pin IO encoding for deterministic bytes.
    env["PYTHONIOENCODING"] = "utf-8"
    # Make the venv's console scripts discoverable without relying on the
    # caller's PATH.
    env["PATH"] = str(scripts_dir) + os.pathsep + env.get("PATH", "")
    return env


class InstalledEnv:
    """The fresh venv created for the test module."""

    def __init__(
        self,
        root: Path,
        python: Path,
        console_script: Path,
        site_packages: Path,
        scripts_dir: Path,
        wheel: Path,
        dist_info: Path,
    ) -> None:
        self.root = root
        self.python = python
        self.console_script = console_script
        self.site_packages = site_packages
        self.scripts_dir = scripts_dir
        self.wheel = wheel
        self.dist_info = dist_info


@pytest.fixture(scope="module")
def outside_cwd() -> Path:
    """A working directory outside the source tree.

    Using the system temp directory (rather than pytest's basetemp) keeps the
    guarantee explicit even when pytest is invoked with ``--basetemp`` inside
    the checkout.
    """
    workdir = Path(tempfile.mkdtemp(prefix="osm-outside-cwd-", dir=tempfile.gettempdir())).resolve()
    if workdir == REPO_ROOT or REPO_ROOT in workdir.parents or workdir in REPO_ROOT.parents:
        shutil.rmtree(workdir, ignore_errors=True)
        pytest.fail(f"outside working directory {workdir} is not outside {REPO_ROOT}")
    try:
        yield workdir
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _run(
    cmd: list[str | Path],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd),
        env=env,
        capture_output=True,
    )


def _run_check(
    cmd: list[str | Path],
    *,
    cwd: Path,
    env: dict[str, str],
    what: str,
) -> subprocess.CompletedProcess[bytes]:
    result = _run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        pytest.fail(
            f"{what} failed (exit {result.returncode})\n"
            f"command: {cmd}\n"
            f"stdout:\n{result.stdout.decode(errors='replace')}\n"
            f"stderr:\n{result.stderr.decode(errors='replace')}"
        )
    return result


def _venv_layout(venv_dir: Path) -> tuple[Path, Path]:
    """Interpreter/console-script paths for the actual venv layout."""
    if os.name == "nt":
        scripts_dir = venv_dir / "Scripts"
        interpreter = scripts_dir / "python.exe"
        console_script = scripts_dir / "ocean-sonar-modeling.exe"
    else:
        scripts_dir = venv_dir / "bin"
        interpreter = scripts_dir / "python"
        console_script = scripts_dir / "ocean-sonar-modeling"
    return interpreter, console_script


def _wheel_dist_info_name(wheel: Path) -> str:
    """Return the ``*.dist-info`` directory name carried by a wheel file.

    A wheel named ``name-version-*.whl`` contains a single top-level
    ``name-version.dist-info/`` directory; the installed project must land in
    site-packages under that same name.
    """
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    dist_info_dirs = {
        name.split("/", 1)[0]
        for name in names
        if name.count("/") >= 1 and name.split("/", 1)[0].endswith(".dist-info")
    }
    assert len(dist_info_dirs) == 1, (
        f"wheel {wheel.name} must contain exactly one .dist-info directory, got {dist_info_dirs}"
    )
    return next(iter(dist_info_dirs))


def _wheel_metadata_text(wheel: Path) -> str:
    """Read the ``METADATA`` file shipped inside the wheel as text."""
    return _wheel_metadata_bytes(wheel).decode("utf-8")


def _wheel_metadata_bytes(wheel: Path) -> bytes:
    """Read the raw ``METADATA`` bytes shipped inside the wheel."""
    dist_info = _wheel_dist_info_name(wheel)
    with zipfile.ZipFile(wheel) as zf:
        return zf.read(f"{dist_info}/METADATA")


def _metadata_version(metadata_text: str) -> str:
    """Parse the ``Version:`` header from a distribution METADATA file."""
    message = HeaderParser().parsestr(metadata_text)
    version = message.get("Version")
    assert version is not None, "distribution metadata is missing a Version header"
    return str(version)


@pytest.fixture(scope="module")
def installed_env(tmp_path_factory: pytest.TempPathFactory, outside_cwd: Path) -> InstalledEnv:
    """Build a wheel with the current interpreter and install it offline."""
    base = tmp_path_factory.mktemp("installed")
    wheel_dir = base / "wheels"
    build_env = _scrubbed_env(Path(os.defpath))
    # Build the wheel from the checkout path, but never with the checkout as
    # cwd and fully offline: --no-index forbids downloads, --no-deps avoids
    # dependency resolution, --no-build-isolation uses the ambient builder.
    _run_check(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-index", "--no-deps", "--no-build-isolation",
            "--wheel-dir", str(wheel_dir), str(REPO_ROOT),
        ],
        cwd=outside_cwd,
        env=build_env,
        what="build wheel",
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"
    wheel = wheels[0]

    # The wheel itself advertises the expected version, so later checks verify
    # the *installed* copy against the artifact rather than against the source.
    wheel_dist_info = _wheel_dist_info_name(wheel)
    assert _metadata_version(_wheel_metadata_text(wheel)) == "0.1.0", (
        f"wheel {wheel.name} does not advertise Version: 0.1.0"
    )

    venv_dir = base / "venv"
    # A plain EnvBuilder: pip bootstrapped from ensurepip, no system
    # site-packages, so nothing preinstalled on the host can satisfy imports.
    venv.EnvBuilder(with_pip=True, clear=True).create(str(venv_dir))

    interpreter, console_script = _venv_layout(venv_dir)
    assert interpreter.exists(), f"venv interpreter missing at {interpreter}"
    scripts_dir = interpreter.parent

    # The venv must not inherit the host interpreter's site-packages.
    pyvenv_cfg = (venv_dir / "pyvenv.cfg").read_text(encoding="utf-8")
    assert "include-system-site-packages = false" in pyvenv_cfg, pyvenv_cfg

    env = _scrubbed_env(scripts_dir)
    # Install strictly from the wheel file: --force-reinstall guarantees the
    # artifact's contents are what ends up in the venv even if an earlier copy
    # exists; the source tree path never appears on this command line.
    install_cmd = [
        interpreter, "-m", "pip", "install",
        "--no-index", "--no-deps", "--force-reinstall", str(wheel),
    ]
    assert str(REPO_ROOT) not in [str(part) for part in install_cmd]
    _run_check(
        install_cmd,
        cwd=outside_cwd,
        env=env,
        what="install wheel into fresh venv",
    )
    assert console_script.exists(), f"console script missing at {console_script}"
    if os.name != "nt":
        assert os.access(console_script, os.X_OK), f"{console_script} is not executable"

    # Ask the installed interpreter itself where its site-packages lives, so
    # the test follows POSIX and Windows layouts instead of guessing.
    probe = _run_check(
        [interpreter, "-c", "import site; print(site.getsitepackages()[0])"],
        cwd=outside_cwd,
        env=env,
        what="locate venv site-packages",
    )
    site_packages = Path(probe.stdout.decode().strip())
    assert site_packages.is_dir(), f"site-packages does not exist: {site_packages}"

    # The installed .dist-info must be the one carried by the wheel, and its
    # installed METADATA must byte-match the wheel's and keep Version: 0.1.0.
    dist_info = site_packages / wheel_dist_info
    assert dist_info.is_dir(), (
        f"installed dist-info {dist_info} missing; the venv does not match wheel {wheel.name}"
    )
    installed_metadata = dist_info / "METADATA"
    assert installed_metadata.is_file(), f"installed METADATA missing at {installed_metadata}"
    assert _metadata_version(installed_metadata.read_text(encoding="utf-8")) == "0.1.0"
    assert installed_metadata.read_bytes() == _wheel_metadata_bytes(wheel), (
        "installed METADATA differs from the METADATA inside the installed wheel"
    )

    return InstalledEnv(
        root=venv_dir,
        python=interpreter,
        console_script=console_script,
        site_packages=site_packages,
        scripts_dir=scripts_dir,
        wheel=wheel,
        dist_info=dist_info,
    )


# ---------------------------------------------------------------------------
# Source-level contract for ocean_sonar/__main__.py
# ---------------------------------------------------------------------------


def test_main_module_source_contract() -> None:
    """``main(argv=None) -> int`` delegates argv verbatim once to cli.main.

    Direct execution must remain ``sys.exit(main())``. Checked structurally so
    it does not depend on the checkout being importable from the test runner.
    """
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))

    main_fn = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"),
        None,
    )
    assert main_fn is not None, "ocean_sonar/__main__.py must define main()"
    assert len(main_fn.args.args) == 1
    assert main_fn.args.args[0].arg == "argv"
    assert len(main_fn.args.defaults) == 1
    assert isinstance(main_fn.args.defaults[0], ast.Constant)
    assert main_fn.args.defaults[0].value is None
    assert isinstance(main_fn.returns, ast.Name)
    assert main_fn.returns.id == "int"

    # Body must be a single `return <cli-main>(argv)`: argv forwarded once,
    # verbatim (the very same Name node), with the integer result returned.
    assert len(main_fn.body) == 1
    ret = main_fn.body[0]
    assert isinstance(ret, ast.Return)
    assert isinstance(ret.value, ast.Call)
    call = ret.value
    assert len(call.args) == 1
    assert call.keywords == []
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == "argv"

    guard = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(op, ast.Eq)
                and isinstance(comp, ast.Constant)
                and comp.value == "__main__"
                for op, comp in zip(node.test.ops, node.test.comparators)
            )
        ),
        None,
    )
    assert guard is not None, "missing `if __name__ == '__main__':` guard"
    # The guard body must be exactly `sys.exit(main())`.
    assert len(guard.body) == 1
    stmt = guard.body[0]
    assert isinstance(stmt, ast.Expr)
    assert isinstance(stmt.value, ast.Call)
    outer = stmt.value
    assert isinstance(outer.func, ast.Attribute)
    assert outer.func.attr == "exit"
    assert isinstance(outer.func.value, ast.Name)
    assert outer.func.value.id == "sys"
    assert len(outer.args) == 1
    assert outer.keywords == []
    assert isinstance(outer.args[0], ast.Call)
    inner = outer.args[0]
    assert isinstance(inner.func, ast.Name)
    assert inner.func.id == "main"
    assert inner.args == []
    assert inner.keywords == []


def _load_source_main_module() -> ModuleType:
    """Load the checkout's ``__main__.py`` under a private package alias.

    Loading by explicit file location means this works regardless of the
    pytest cwd or PYTHONPATH. The ``.cli`` submodule is stubbed so importing
    ``__main__`` never pulls cli's (possibly third-party) dependencies.
    """
    pkg_name = "_osm_source_package_under_test"
    main_name = pkg_name + ".__main__"
    cli_name = pkg_name + ".cli"
    if main_name in sys.modules:
        return sys.modules[main_name]

    pkg_dir = REPO_ROOT / "ocean_sonar"
    spec = importlib.util.spec_from_file_location(
        pkg_name,
        pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)],
    )
    assert spec is not None and spec.loader is not None
    package = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = package
    spec.loader.exec_module(package)

    cli_stub = ModuleType(cli_name)
    cli_stub.main = lambda argv=None: 0  # noqa: E731 - replaced per test
    sys.modules[cli_name] = cli_stub

    main_spec = importlib.util.spec_from_file_location(
        main_name,
        MAIN_SOURCE,
    )
    assert main_spec is not None and main_spec.loader is not None
    main_module = importlib.util.module_from_spec(main_spec)
    sys.modules[main_name] = main_module
    main_spec.loader.exec_module(main_module)
    return main_module


def test_main_forwards_argv_verbatim_once_and_returns_int() -> None:
    main_module = _load_source_main_module()

    calls: list[object] = []
    sentinel_argv = ["version"]

    def fake_cli_main(argv: object) -> int:
        calls.append(argv)
        return 7

    # __main__ binds `from .cli import main as _cli_main`; patch the binding.
    main_module._cli_main = fake_cli_main  # type: ignore[attr-defined]

    rc = main_module.main(sentinel_argv)
    assert rc == 7
    assert len(calls) == 1
    assert calls[0] is sentinel_argv  # the exact list object, unchanged

    # Default call must forward None rather than inventing an empty list.
    assert main_module.main() == 7
    assert len(calls) == 2
    assert calls[1] is None


# ---------------------------------------------------------------------------
# Installed-wheel isolation
# ---------------------------------------------------------------------------


def _probe_import(python: Path, *, cwd: Path, env: dict[str, str]) -> dict[str, object]:
    code = (
        "import json, os, site, sys;"
        "import ocean_sonar;"
        "import ocean_sonar.__main__ as m;"
        "print(json.dumps({"
        "'main': m.__file__,"
        " 'package': ocean_sonar.__file__,"
        " 'sys_path': sys.path,"
        " 'executable': sys.executable,"
        " 'prefix': sys.prefix,"
        " 'base_prefix': sys.base_prefix,"
        " 'user_site_enabled': site.ENABLE_USER_SITE,"
        " 'user_site': site.getusersitepackages(),"
        " 'env_keys': sorted(os.environ),"
        " 'pythonnousersite': os.environ.get('PYTHONNOUSERSITE')"
        "}))"
    )
    result = _run_check(
        [python, "-c", code],
        cwd=cwd,
        env=env,
        what="import ocean_sonar.__main__ in venv",
    )
    return json.loads(result.stdout.decode())  # type: ignore[no-any-return]


def test_installed_main_resides_in_venv_site_packages(
    installed_env: InstalledEnv, outside_cwd: Path
) -> None:
    env = _scrubbed_env(installed_env.scripts_dir)
    info = _probe_import(installed_env.python, cwd=outside_cwd, env=env)

    main_file = Path(str(info["main"])).resolve()
    package_file = Path(str(info["package"])).resolve()

    assert main_file.name == "__main__.py"
    assert main_file.is_relative_to(installed_env.site_packages.resolve())
    assert package_file.is_relative_to(installed_env.site_packages.resolve())
    # The installed copy must not be the checkout.
    assert not main_file.is_relative_to(REPO_ROOT)
    assert not package_file.is_relative_to(REPO_ROOT)

    # The interpreter really is the venv's (both sys.executable and the
    # prefixes), not the ambient one, and user site-packages (host
    # preinstalled packages) are disabled.
    assert Path(str(info["executable"])).resolve() == installed_env.python.resolve()
    assert Path(str(info["prefix"])).resolve() == installed_env.root.resolve()
    assert Path(str(info["base_prefix"])).resolve() != installed_env.root.resolve()
    assert info["user_site_enabled"] is False
    assert str(info["pythonnousersite"]) == "1"
    user_site = Path(str(info["user_site"])).resolve()
    assert not user_site.is_relative_to(installed_env.root.resolve())

    # The probe subprocess itself must not carry any source-injecting
    # environment variable (checked case-insensitively for Windows).
    probe_env_upper = {str(key).upper() for key in info["env_keys"]}  # type: ignore[union-attr]
    for name in _INJECTABLE_ENV_VARS:
        assert name.upper() not in probe_env_upper, (
            f"subprocess inherited {name}; isolation cannot be guaranteed"
        )

    # No sys.path entry may lead back into the source tree: empty entries
    # stand for cwd, which is the outside working directory here.
    for entry in info["sys_path"]:  # type: ignore[union-attr]
        assert isinstance(entry, str)
        resolved = Path(entry).resolve() if entry else outside_cwd.resolve()
        assert not resolved.is_relative_to(REPO_ROOT), (
            f"sys.path entry {entry!r} ({resolved}) leaks the source tree"
        )


def test_installed_distribution_metadata_matches_wheel(
    installed_env: InstalledEnv,
    outside_cwd: Path,
) -> None:
    """The venv's .dist-info is the one from the built wheel at version 0.1.0."""
    wheel = installed_env.wheel
    assert wheel.is_file()
    # The install command never copied the wheel into the venv; it lives in
    # the build scratch directory, outside both the venv and the checkout.
    assert not wheel.resolve().is_relative_to(installed_env.root.resolve())
    assert not wheel.resolve().is_relative_to(REPO_ROOT)

    expected_dist_info = _wheel_dist_info_name(wheel)
    assert installed_env.dist_info.name == expected_dist_info
    assert installed_env.dist_info.parent.resolve() == installed_env.site_packages.resolve()

    wheel_metadata = _wheel_metadata_text(wheel)
    installed_metadata = (installed_env.dist_info / "METADATA").read_text(encoding="utf-8")
    assert _metadata_version(wheel_metadata) == "0.1.0"
    assert _metadata_version(installed_metadata) == "0.1.0"
    assert installed_metadata == wheel_metadata

    # The wheel name itself must carry the 0.1.0 version.
    assert wheel.name.startswith("ocean_sonar_modeling-0.1.0-"), wheel.name

    # No other ocean-sonar installation/dist-info may share site-packages.
    sibling_dist_infos = sorted(installed_env.site_packages.glob("ocean_sonar_modeling-*.dist-info"))
    assert sibling_dist_infos == [installed_env.dist_info]

    # The installed package also reports 0.1.0 at runtime, from the venv,
    # with no possibility of the checkout satisfying the import.
    env = _scrubbed_env(installed_env.scripts_dir)
    result = _run_check(
        [
            installed_env.python,
            "-c",
            "import ocean_sonar; print(ocean_sonar.__version__, ocean_sonar.__file__)",
        ],
        cwd=outside_cwd,
        env=env,
        what="read installed ocean_sonar.__version__",
    )
    version_line, _, package_path = result.stdout.decode().strip().partition(" ")
    assert version_line == "0.1.0"
    assert Path(package_path).resolve().is_relative_to(installed_env.site_packages.resolve())
    assert not Path(package_path).resolve().is_relative_to(REPO_ROOT)


def test_installed_console_script_is_on_path(installed_env: InstalledEnv) -> None:
    assert installed_env.console_script.is_file()
    assert installed_env.python.is_file()


@pytest.mark.parametrize("args", CASES)
def test_installed_module_matches_console_script(
    args: list[str],
    installed_env: InstalledEnv,
    outside_cwd: Path,
) -> None:
    env = _scrubbed_env(installed_env.scripts_dir)

    module = _run(
        [installed_env.python, "-m", "ocean_sonar", *args],
        cwd=outside_cwd,
        env=env,
    )
    script = _run(
        [installed_env.console_script, *args],
        cwd=outside_cwd,
        env=env,
    )

    assert module.returncode == script.returncode, (
        f"exit codes differ for args={args!r}: "
        f"{module.returncode} vs {script.returncode}\n"
        f"module stderr: {module.stderr!r}\nscript stderr: {script.stderr!r}"
    )
    assert module.stdout == script.stdout, f"stdout differs for args={args!r}"
    assert module.stderr == script.stderr, f"stderr differs for args={args!r}"


@pytest.mark.parametrize("entry", ["module", "console-script"], ids=["python -m", "console-script"])
def test_installed_version_exact_output(
    entry: str,
    installed_env: InstalledEnv,
    outside_cwd: Path,
) -> None:
    env = _scrubbed_env(installed_env.scripts_dir)
    if entry == "module":
        cmd = [installed_env.python, "-m", "ocean_sonar", "version"]
    else:
        cmd = [installed_env.console_script, "version"]

    result = _run(cmd, cwd=outside_cwd, env=env)
    assert result.returncode == 0
    assert result.stdout == b"0.1.0\n"
    assert result.stderr == b""


def _write_trend_file(path: Path, *, degraded: bool) -> str:
    """Write a canonical serialize_trend-compatible JSON trend file."""
    document = {
        "count": 2,
        "changes": 1,
        "degraded": 1 if degraded else 0,
        "coverage_delta": -0.1 if degraded else 0.1,
        "score_delta": -1.0 if degraded else 2.0,
        "worst": [1, 0, 0, -0.1 if degraded else 0.1, -1.0 if degraded else 2.0],
        "quality": "fail" if degraded else "pass",
    }
    path.write_bytes(
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    )
    return str(path)


@pytest.mark.parametrize("entry", ["module", "console-script"], ids=["python -m", "console-script"])
def test_installed_render_trends_success_exact_output(
    entry: str,
    installed_env: InstalledEnv,
    tmp_path: Path,
) -> None:
    """``render-trends`` succeeds identically from an outside directory."""
    assert not tmp_path.resolve().is_relative_to(REPO_ROOT)
    paths = [
        _write_trend_file(tmp_path / "trend_0.json", degraded=False),
        _write_trend_file(tmp_path / "trend_1.json", degraded=True),
    ]
    env = _scrubbed_env(installed_env.scripts_dir)
    if entry == "module":
        cmd = [installed_env.python, "-m", "ocean_sonar", "render-trends", *paths]
    else:
        cmd = [installed_env.console_script, "render-trends", *paths]

    result = _run(cmd, cwd=tmp_path, env=env)
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == (
        b"TRENDS=2,2,1,0.000000,0.500000,fail\n"
        b"FILES=0:0.050000:1.000000|1:-0.050000:-0.500000;"
        b"RMSE=0.100000,1.500000;WORST_FILE=1\n"
        b"WORST=1,1,0,0,-0.100000,-1.000000\n"
    )


@pytest.mark.parametrize("args", CASES)
def test_installed_entry_runs_from_any_outside_directory(
    args: list[str],
    installed_env: InstalledEnv,
    tmp_path: Path,
    outside_cwd: Path,
) -> None:
    """Output must not depend on the working directory (both outside tree)."""
    env = _scrubbed_env(installed_env.scripts_dir)
    second_dir = tmp_path.resolve()
    assert not second_dir.is_relative_to(REPO_ROOT)

    first = _run(
        [installed_env.python, "-m", "ocean_sonar", *args],
        cwd=outside_cwd,
        env=env,
    )
    second = _run(
        [installed_env.python, "-m", "ocean_sonar", *args],
        cwd=second_dir,
        env=env,
    )
    assert (first.returncode, first.stdout, first.stderr) == (
        second.returncode,
        second.stdout,
        second.stderr,
    )


# ---------------------------------------------------------------------------
# Negative controls: prove the scrubbing assertions are capable of failing.
# Without env/cwd sanitization the checkout *would* shadow the install.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leak",
    [
        pytest.param("pythonpath", id="via-PYTHONPATH"),
        pytest.param("cwd", id="via-cwd"),
    ],
)
def test_negative_control_source_tree_leak_is_detected(
    leak: str,
    installed_env: InstalledEnv,
    outside_cwd: Path,
) -> None:
    env = _scrubbed_env(installed_env.scripts_dir)
    if leak == "pythonpath":
        # Reintroduce a source-injecting path variable explicitly.
        env["PYTHONPATH"] = str(REPO_ROOT)
        cwd = outside_cwd
    else:
        # cwd is on sys.path as '' for `python -m`; start inside the checkout.
        cwd = REPO_ROOT

    info = _probe_import(installed_env.python, cwd=cwd, env=env)
    leaked = Path(str(info["main"])).resolve()
    assert leaked.is_relative_to(REPO_ROOT), (
        f"expected {leak} leakage to resolve into the checkout, got {leaked}; "
        "the positive isolation test may no longer be meaningful"
    )
    assert not leaked.is_relative_to(installed_env.site_packages.resolve())
