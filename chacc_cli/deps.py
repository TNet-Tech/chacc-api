"""
``chacc deps check`` and ``chacc deps sync``: the Python packages of installed modules.

check  Reports which enabled modules have their packages installed. No network.
sync   Resolves what changed and installs what is missing (needs network), then checks.
       Use it after a Python upgrade, or to fill the packages directory while online.
"""

import asyncio
import os
import sys


def _enabled_module_names() -> set[str] | None:
    """Enabled modules from the database, or None (meaning all archives) if it can't be read."""
    try:
        from src.database import ModuleRecord, SessionLocal

        db = SessionLocal()
        try:
            return {r.name for r in db.query(ModuleRecord).filter_by(is_enabled=True).all()}
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - fall back to every archive
        return None


def _owner_mismatch(path: str) -> bool:
    """Running as root on files the server user owns would leave root-owned cache files."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return False
    try:
        return os.stat(path).st_uid != 0
    except OSError:
        return False


def run_deps(action: str) -> int:
    from src.constants import DEPENDENCY_CACHE_DIR, DEVELOPMENT_MODE
    from src.logger import configure_logging, get_default_log_level
    from src.module_loader.archive import collect_module_requirements
    from src.module_packages import (
        PackageInstallError,
        activate,
        boot_check,
        manager,
        resolve_and_install,
    )

    if DEVELOPMENT_MODE:
        print(
            "Development mode: module packages are installed into the active environment "
            "when the server starts (ENABLE_PLUGIN_DEPENDENCY_RESOLUTION). Nothing to do."
        )
        return 0

    if _owner_mismatch(DEPENDENCY_CACHE_DIR):
        print(
            "Run this as the server's user, not root, so the files it writes stay writable "
            "by the server. In Docker: docker exec -u chacc <container> chacc deps " + action,
            file=sys.stderr,
        )
        return 2

    logger = configure_logging(log_level=get_default_log_level())
    activate()
    names = _enabled_module_names()
    requirements = collect_module_requirements(names)

    if action == "sync":
        dm = manager(logger)
        archived = set(collect_module_requirements(None))
        for registered in list(dm.load_cache().get("requirements_caches") or {}):
            if registered not in archived:
                dm.remove_module(registered)
        try:
            result = asyncio.run(resolve_and_install(requirements, logger))
        except PackageInstallError as exc:
            print(f"Installing module packages failed: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 - ResolutionError and friends
            print(f"Resolving module requirements failed: {exc}", file=sys.stderr)
            return 1
        for line in result.warnings:
            print(f"warning: {line}")

    report = boot_check(requirements, logger, allow_network=False)
    if not requirements:
        print("No enabled module declares Python requirements.")
    elif report.blocked:
        print(f"{len(report.blocked)} module(s) can't be loaded:")
        for name, reason in report.blocked.items():
            print(f"  {name}: {reason}")
    else:
        print(f"All Python packages of {len(requirements)} module(s) are installed.")
    for line in report.warnings:
        print(f"warning: {line}")
    return 1 if report.blocked else 0
