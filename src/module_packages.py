"""
Python packages that modules need: where they live, how they are installed, and
what boot does about them.

Production
    Module packages are installed into ``MODULE_PACKAGES_DIR`` (a volume in Docker)
    with ``pip install --no-deps --target``. Only packages the core installation does
    not already provide go there. The directory is appended to ``sys.path`` *after*
    site-packages, so core packages always win, and a module can never replace them.
    Because the directory is persistent, restarts and recreated containers need no
    network.

Development
    Packages go into the active environment (the developer's virtualenv), as before.

Everywhere
    The core installation's versions (chacc-api and everything it depends on) are
    written to a constraints file and passed to every resolve, so a module can add
    packages but cannot change core versions. The backbone itself is never resolved
    at runtime: it was installed with ChaCC.

Boot (``boot_check``)
    Never resolves modules that are already resolved. It checks the cached pins
    against what is installed. If something is missing and ``CHACC_BOOT_INSTALL`` is
    ``missing`` (default), it makes one short attempt to fix it. Whatever is still
    missing blocks only the modules that need it; the server starts.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import site
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from src.constants import (
    CHACC_BOOT_INSTALL,
    CHACC_BOOT_INSTALL_TIMEOUT,
    DEPENDENCY_CACHE_DIR,
    DEVELOPMENT_MODE,
    MODULE_PACKAGES_DIR,
)

CORE_DISTRIBUTION = "chacc-api"
CORE_CONSTRAINTS_FILE = os.path.join(DEPENDENCY_CACHE_DIR, "core-constraints.txt")
STATUS_FILE = os.path.join(DEPENDENCY_CACHE_DIR, "deps_status.json")
ENV_MARKER_NAME = ".chacc_env.json"
LEGACY_MODULES = ("backbone",)
INSTALL_TIMEOUT = 900

_NETWORK_HINTS = (
    "newconnectionerror",
    "failed to establish a new connection",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
    "connecttimeouterror",
    "read timed out",
    "connection timed out",
    "could not fetch url",
    "proxyerror",
    "max retries exceeded",
    "connection refused",
)


class PackageInstallError(RuntimeError):
    """pip could not install module packages into the packages directory."""

    def __init__(self, message: str, network: bool = False):
        super().__init__(message)
        self.network = network


def looks_like_network_error(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _NETWORK_HINTS)


def uses_packages_dir() -> bool:
    """Module packages go into MODULE_PACKAGES_DIR in production only."""
    return not DEVELOPMENT_MODE


def _canonical(name: str) -> str:
    from chacc.utils import base_package_name, canonicalize_name

    return canonicalize_name(base_package_name(name))


def activate() -> None:
    """Make the packages directory importable, after site-packages (core wins)."""
    if not uses_packages_dir():
        return
    os.makedirs(MODULE_PACKAGES_DIR, exist_ok=True)
    if MODULE_PACKAGES_DIR not in sys.path:
        site.addsitedir(MODULE_PACKAGES_DIR)
    importlib.invalidate_caches()


def current_environment() -> dict[str, str]:
    """What compiled packages in the packages directory are tied to."""
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "machine": platform.machine(),
    }


def _marker_path() -> str:
    return os.path.join(MODULE_PACKAGES_DIR, ENV_MARKER_NAME)


def recorded_environment() -> dict | None:
    try:
        with open(_marker_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def environment_changed() -> bool:
    """True when the packages directory was filled by a different Python or platform."""
    recorded = recorded_environment()
    return recorded is not None and recorded != current_environment()


def write_environment_marker() -> None:
    os.makedirs(MODULE_PACKAGES_DIR, exist_ok=True)
    with open(_marker_path(), "w") as f:
        json.dump(current_environment(), f, indent=2)


def _in_packages_dir(dist: importlib.metadata.Distribution) -> bool:
    path = getattr(dist, "_path", None)
    if path is None:
        return False
    root = os.path.realpath(MODULE_PACKAGES_DIR)
    return os.path.realpath(str(path)).startswith(root + os.sep)


def site_versions() -> dict[str, str]:
    """Packages installed outside the packages directory (image / virtualenv)."""
    versions: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if not name or _in_packages_dir(dist):
            continue
        versions.setdefault(_canonical(name), dist.version)
    return versions


def target_versions() -> dict[str, str]:
    """Packages installed in the packages directory."""
    if not os.path.isdir(MODULE_PACKAGES_DIR):
        return {}
    versions: dict[str, str] = {}
    for dist in importlib.metadata.distributions(path=[MODULE_PACKAGES_DIR]):
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            versions.setdefault(_canonical(name), dist.version)
    return versions


def core_versions() -> dict[str, str]:
    """
    chacc-api and every package it depends on (following extras), with installed versions.

    Only these become constraints. Other packages in the environment (for example a
    module's packages in a development virtualenv) stay free to change.
    """
    from packaging.requirements import InvalidRequirement, Requirement

    versions: dict[str, str] = {}
    seen: dict[str, set[str]] = {}
    queue: list[tuple[str, frozenset[str]]] = [(CORE_DISTRIBUTION, frozenset())]
    while queue:
        name, extras = queue.pop()
        canonical = _canonical(name)
        done = seen.get(canonical)
        if done is not None and extras <= done:
            continue
        seen[canonical] = (done or set()) | set(extras)
        try:
            dist = importlib.metadata.distribution(canonical)
        except importlib.metadata.PackageNotFoundError:
            continue
        if _in_packages_dir(dist):
            continue
        versions[canonical] = dist.version
        for line in dist.requires or []:
            try:
                req = Requirement(line)
            except InvalidRequirement:
                continue
            if req.marker is not None:
                environments = [{"extra": e} for e in sorted(seen[canonical])] or [{"extra": ""}]
                if not any(req.marker.evaluate(env) for env in environments):
                    continue
            queue.append((req.name, frozenset(req.extras)))
    return versions


def write_core_constraints() -> str:
    """Write the core constraints file (only when it changes) and return its path."""
    lines = [f"{name}=={version}" for name, version in sorted(core_versions().items())]
    content = "# Generated by ChaCC: core packages, which modules cannot change.\n"
    content += "\n".join(lines) + "\n"
    try:
        with open(CORE_CONSTRAINTS_FILE) as f:
            if f.read() == content:
                return CORE_CONSTRAINTS_FILE
    except OSError:
        pass
    os.makedirs(os.path.dirname(CORE_CONSTRAINTS_FILE), exist_ok=True)
    tmp = f"{CORE_CONSTRAINTS_FILE}.tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, CORE_CONSTRAINTS_FILE)
    return CORE_CONSTRAINTS_FILE


def manager(logger, *, resolve_timeout=600, install_timeout=300, max_retries=5):
    """A DependencyManager on ChaCC's cache, with the core constraints applied."""
    from chacc import DependencyManager

    dm = DependencyManager(
        cache_dir=DEPENDENCY_CACHE_DIR,
        logger=logger,
        constraint_files=[write_core_constraints()],
        resolve_timeout=resolve_timeout,
        install_timeout=install_timeout,
        max_retries=max_retries,
    )
    for name in LEGACY_MODULES:
        dm.remove_module(name)
    return dm


def forget_module(name: str, logger) -> None:
    """Unregister a module from the cache (no network). Its packages stay installed."""
    manager(logger).remove_module(name)


@dataclass
class InstallPlan:
    to_install: list[str] = field(default_factory=list)
    stale_core: list[str] = field(default_factory=list)

    def missing_names(self) -> set[str]:
        return {_spec_name(spec) for spec in self.to_install}


def _spec_name(spec: str) -> str:
    """Canonical package name of ``name==1.0``, ``name @ url`` or a wheel file path."""
    base = os.path.basename(spec)
    if base.endswith(".whl"):
        return _canonical(base.split("-", 1)[0])
    return _canonical(spec.split("==", 1)[0].split(" @ ", 1)[0].strip())


def plan_install(pins: dict[str, str], ignore_target: bool = False) -> InstallPlan:
    """
    Which pins must be installed into the packages directory.

    A pin whose package the core already provides is never installed there (it
    would be shadowed anyway). If the core has a different version, the pin is
    reported as stale: the module was resolved against older core packages.
    """
    from chacc.utils import version_satisfies

    site = site_versions()
    target = {} if ignore_target else target_versions()
    plan = InstallPlan()
    for name, spec in sorted(pins.items()):
        canonical = _canonical(name)
        if canonical in site:
            if not version_satisfies(site[canonical], spec):
                plan.stale_core.append(f"{name}{spec} (core has {site[canonical]})")
            continue
        if canonical in target and version_satisfies(target[canonical], spec):
            continue
        plan.to_install.append(f"{name}{spec}")
    return plan


def _remove_from_target(names: set[str]) -> None:
    """Remove installed copies of these packages, so no stale dist-info is left behind."""
    root = os.path.realpath(MODULE_PACKAGES_DIR)
    for dist in list(importlib.metadata.distributions(path=[MODULE_PACKAGES_DIR])):
        name = dist.metadata["Name"] if dist.metadata else None
        if not name or _canonical(name) not in names:
            continue
        for file in dist.files or []:
            path = os.path.realpath(str(dist.locate_file(file)))
            if path.startswith(root + os.sep) and os.path.isfile(path):
                os.remove(path)
        dist_path = getattr(dist, "_path", None)
        if dist_path is not None:
            shutil.rmtree(str(dist_path), ignore_errors=True)


def install_into_target(
    specs: list[str],
    logger,
    *,
    timeout: int = INSTALL_TIMEOUT,
    network_timeout: int | None = None,
    retries: int | None = None,
) -> None:
    """``pip install --no-deps --target MODULE_PACKAGES_DIR`` for exact pins."""
    if not specs:
        return
    os.makedirs(MODULE_PACKAGES_DIR, exist_ok=True)
    _remove_from_target({_spec_name(spec) for spec in specs})

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input", "--no-deps", "--upgrade",
        "--target", MODULE_PACKAGES_DIR,
    ]  # fmt: skip
    if network_timeout is not None:
        cmd += ["--timeout", str(network_timeout)]
    if retries is not None:
        cmd += ["--retries", str(retries)]
    cmd += specs

    logger.info(f"Installing {len(specs)} module package(s) into {MODULE_PACKAGES_DIR}:")
    for spec in specs:
        logger.info(f"     + {spec}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise PackageInstallError(f"pip install timed out after {timeout}s", network=True)
    if result.returncode != 0:
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        tail = "\n".join(line for line in output.strip().splitlines()[-15:])
        raise PackageInstallError(
            f"pip install failed:\n{tail}", network=looks_like_network_error(output)
        )
    write_environment_marker()
    importlib.invalidate_caches()
    logger.info("Module packages installed.")


@dataclass
class ResolveResult:
    pins: dict[str, str]
    warnings: list[str]


async def resolve_and_install(requirements: dict[str, str], logger) -> ResolveResult:
    """
    Resolve modules' requirements (added to the registered modules) and install them.

    Production installs into the packages directory; development into the active
    environment. Raises ``chacc.ResolutionError`` or ``PackageInstallError``.
    """
    from chacc.utils import format_conflict

    requirements = {n: c for n, c in requirements.items() if c and c.strip()}
    if not requirements:
        return ResolveResult({}, [])
    activate()
    dm = manager(logger)
    pins = await dm.resolve_dependencies(requirements, install=not uses_packages_dir())
    if uses_packages_dir():
        plan = plan_install(pins, ignore_target=environment_changed())
        await asyncio.to_thread(install_into_target, plan.to_install, logger)
    warnings = [format_conflict(c) for c in dm.last_conflicts]
    return ResolveResult(pins, warnings)


@contextmanager
def _quick_pip():
    """Short network timeouts for pip subprocesses started while booting."""
    saved = {k: os.environ.get(k) for k in ("PIP_TIMEOUT", "PIP_RETRIES")}
    os.environ["PIP_TIMEOUT"] = "10"
    os.environ["PIP_RETRIES"] = "1"
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def unresolved_modules(requirements: dict[str, str], cache: dict) -> list[str]:
    """Modules whose current requirements are not what the cache resolved."""
    from chacc.utils import calculate_module_hash

    caches = cache.get("requirements_caches") or {}
    unresolved = []
    for name, content in requirements.items():
        entry = caches.get(name) or {}
        if (
            entry.get("hash") != calculate_module_hash(name, content)
            or entry.get("complete", True) is False
        ):
            unresolved.append(name)
    return unresolved


def unmet_requirements(content: str) -> list[str]:
    """Top-level requirements in ``content`` that the installed packages don't satisfy."""
    from packaging.requirements import InvalidRequirement, Requirement

    installed = {**target_versions(), **site_versions()}
    unmet = []
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement:
            unmet.append(line)
            continue
        if req.marker is not None and not req.marker.evaluate():
            continue
        version = installed.get(_canonical(req.name))
        if version is None or (req.specifier and not req.specifier.contains(version, True)):
            unmet.append(line)
    return unmet


@dataclass
class BootReport:
    blocked: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    installed: list[str] = field(default_factory=list)


def boot_check(
    requirements: dict[str, str], logger, allow_network: bool | None = None
) -> BootReport:
    """
    Make sure enabled modules' packages are installed, without resolving what is resolved.

    ``requirements`` is module -> requirements text for the enabled modules.
    ``allow_network`` defaults to ``CHACC_BOOT_INSTALL == "missing"``.
    """
    if allow_network is None:
        allow_network = CHACC_BOOT_INSTALL == "missing"
    report = BootReport()
    requirements = {n: c for n, c in requirements.items() if c and c.strip()}
    activate()
    if not requirements:
        _write_status(report)
        return report

    timeout = CHACC_BOOT_INSTALL_TIMEOUT
    dm = manager(logger, resolve_timeout=timeout, install_timeout=timeout, max_retries=1)
    cache = dm.load_cache()
    unresolved = unresolved_modules(requirements, cache)

    if unresolved and allow_network:
        logger.warning(
            f"Module requirements not resolved yet: {', '.join(unresolved)}. "
            "Trying once (needs network)..."
        )
        try:
            with _quick_pip():
                dm.resolve_dependencies_sync(
                    {n: requirements[n] for n in unresolved}, install=not uses_packages_dir()
                )
            cache = dm.load_cache()
            unresolved = unresolved_modules(requirements, cache)
        except Exception as exc:  # noqa: BLE001 - boot must go on
            logger.warning(f"Could not resolve module requirements at boot: {_first_line(exc)}")

    pins = cache.get("resolved_packages") or {}
    env_changed = uses_packages_dir() and environment_changed()
    plan = plan_install(pins, ignore_target=env_changed) if uses_packages_dir() else InstallPlan()

    if plan.to_install and allow_network:
        try:
            with _quick_pip():
                install_into_target(
                    plan.to_install, logger, timeout=timeout, network_timeout=10, retries=1
                )
            report.installed = list(plan.to_install)
            logger.warning(
                f"Installed {len(report.installed)} missing module package(s) at startup: "
                f"{', '.join(report.installed)}"
            )
            plan = plan_install(pins)
            env_changed = False
        except PackageInstallError as exc:
            logger.warning(f"Could not install missing module packages at boot: {_first_line(exc)}")

    missing = plan.missing_names()
    caches = cache.get("requirements_caches") or {}
    for name, content in requirements.items():
        if name in unresolved:
            unmet = unmet_requirements(content)
            if unmet:
                report.blocked[name] = (
                    f"Python packages not installed: {', '.join(unmet)}. Connect the server to "
                    "the network and restart it, or run `chacc deps sync`."
                )
            else:
                report.warnings.append(
                    f"{name}: requirements not resolved by ChaCC yet; using the packages "
                    "already installed."
                )
            continue
        needed = {_canonical(p) for p in (caches.get(name) or {}).get("packages") or {}}
        lacking = sorted(needed & missing)
        if not lacking:
            continue
        if env_changed:
            recorded = recorded_environment() or {}
            report.blocked[name] = (
                f"Its Python packages were installed for Python {recorded.get('python', '?')} and "
                f"this server runs Python {current_environment()['python']}. Reinstall them with "
                "`chacc deps sync` while connected to the network."
            )
        else:
            report.blocked[name] = (
                f"Python packages not installed: {', '.join(lacking)}. Connect the server to the "
                "network and restart it, or run `chacc deps sync`."
            )

    for line in plan.stale_core:
        report.warnings.append(
            f"Resolved against older core packages: {line}. Run `chacc deps sync` to re-resolve."
        )
    for name, reason in report.blocked.items():
        logger.error(f"Module '{name}' will not be loaded: {reason}")
    for line in report.warnings:
        logger.warning(line)
    _write_status(report)
    return report


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _write_status(report: BootReport) -> None:
    data = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ok": not report.blocked,
        "blocked": report.blocked,
        "warnings": report.warnings,
        "installed": report.installed,
    }
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        tmp = f"{STATUS_FILE}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        pass


def read_status() -> dict:
    """Result of the last boot check (empty dict if none)."""
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
