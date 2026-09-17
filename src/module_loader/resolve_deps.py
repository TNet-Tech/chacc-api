"""Standalone dependency resolution entrypoint.

Runs as root in the Docker entrypoint before dropping to the chacc user,
so pip install has write access to site-packages.

Collects requirements from .chacc files directly (not from the database),
so it works on first startup when DB records don't exist yet.

Usage:
    python -m src.module_loader.resolve_deps
"""

import asyncio
import sys
import threading
from collections.abc import Callable
from typing import Any

from src.constants import DEPENDENCY_CACHE_DIR
from src.logger import configure_logging, get_default_log_level
from src.module_loader.archive import collect_module_requirements

_SPINNER_FRAMES = ["|", "/", "-", "\\"]
_SPINNER_INTERVAL = 0.1


def _spinner_loop(stop_event: threading.Event) -> None:
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r{_SPINNER_FRAMES[i]} ")
        sys.stdout.flush()
        stop_event.wait(_SPINNER_INTERVAL)
        i = (i + 1) % len(_SPINNER_FRAMES)


def _run_with_spinner(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if not sys.stdout.isatty():
        return func(*args, **kwargs)

    stop_event = threading.Event()
    thread = threading.Thread(target=_spinner_loop, args=(stop_event,), daemon=True)
    thread.start()
    try:
        return func(*args, **kwargs)
    finally:
        stop_event.set()
        thread.join()
        sys.stdout.write("\r   \r")
        sys.stdout.flush()


async def _resolve_dependencies_async(logger: Any) -> bool:
    """Async wrapper for dependency resolution logic."""
    modules_requirements = await collect_module_requirements()
    if not modules_requirements:
        logger.info("No module requirements found, skipping resolution.")
        return True

    from chacc import DependencyManager

    dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=logger)
    await dm.resolve_dependencies(modules_requirements)
    logger.info("Dependency resolution completed successfully.")
    return True


def main() -> int:
    logger = configure_logging(log_level=get_default_log_level())
    logger.info("Please wait, we're cleaning up and setting up your backend server...")

    try:
        _run_with_spinner(asyncio.run, _resolve_dependencies_async(logger))
        return 0
    except Exception:
        logger.exception("Dependency resolution failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
