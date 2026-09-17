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

from src.constants import DEPENDENCY_CACHE_DIR
from src.logger import configure_logging, get_default_log_level
from src.module_loader.archive import collect_module_requirements


def main() -> int:
    logger = configure_logging(log_level=get_default_log_level())
    logger.warning("Do not close, we're setting up your backend server")

    try:
        from chacc import DependencyManager

        modules_requirements = asyncio.run(collect_module_requirements())

        if not modules_requirements:
            logger.info("No module requirements found, skipping setup.")
            return 0

        dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=logger)
        asyncio.run(dm.resolve_dependencies(modules_requirements))
        logger.info("Intial setup completed successfully.")
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Dependency resolution failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
