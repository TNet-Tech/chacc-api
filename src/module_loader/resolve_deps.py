"""Standalone dependency resolution entrypoint.

Runs as root in the Docker entrypoint before dropping to the chacc user,
so pip install has write access to site-packages.

Collects requirements from .chacc files directly (not from the database),
so it works on first startup when DB records don't exist yet.

Usage:
    python -m src.module_loader.resolve_deps
"""

import asyncio
import logging
import sys
import threading
from collections.abc import Callable
from typing import Any

from src.constants import DEPENDENCY_CACHE_DIR
from src.logger import configure_logging, get_default_log_level
from src.module_loader.archive import collect_module_requirements

_SPINNER_FRAMES = ["|", "/", "-", "\\"]
_SPINNER_INTERVAL = 0.1
_SPINNER_LABEL = "Resolving dependencies"


def _spinner_loop(stop_event: threading.Event) -> None:
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r{_SPINNER_LABEL}... {_SPINNER_FRAMES[i]} ")
        sys.stdout.flush()
        stop_event.wait(_SPINNER_INTERVAL)
        i = (i + 1) % len(_SPINNER_FRAMES)


def _run_with_spinner(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if not sys.stdout.isatty():
        return func(*args, **kwargs)

    root = logging.getLogger()
    original_level = root.level
    root.setLevel(logging.CRITICAL)

    stop_event = threading.Event()
    thread = threading.Thread(target=_spinner_loop, args=(stop_event,), daemon=True)
    thread.start()
    try:
        return func(*args, **kwargs)
    finally:
        stop_event.set()
        thread.join()
        root.setLevel(original_level)
        clear_line = " " * (len(_SPINNER_LABEL) + 6)
        sys.stdout.write(f"\r{clear_line}\r")
        sys.stdout.flush()


async def _resolve_dependencies_async(logger: Any) -> bool:
    modules_requirements = await collect_module_requirements()
    if not modules_requirements:
        return False
    from chacc import DependencyManager

    dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=logger)
    await dm.resolve_dependencies(modules_requirements)
    return True


def main() -> int:
    logger = configure_logging(log_level=get_default_log_level())
    logger.warning("Do not close, we're setting up your backend server")

    try:
        success = _run_with_spinner(asyncio.run, _resolve_dependencies_async(logger))
        if success:
            logger.info("Dependency resolution completed successfully.")
        else:
            logger.info("No module requirements found, skipping resolution.")
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Dependency resolution failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
