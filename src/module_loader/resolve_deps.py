"""Standalone dependency resolution entrypoint.

Runs as root in the Docker entrypoint before dropping to the chacc user,
so pip install has write access to site-packages.

Collects requirements from .chacc files directly (not from the database),
so it works on first startup when DB records don't exist yet.

Writes a status file so the health endpoint can report progress to the UI.

Usage:
    python -m src.module_loader.resolve_deps
"""

import asyncio
import json
import logging
import os
import sys
import tempfile

from src.constants import BASE_DIR, DEPENDENCY_CACHE_DIR
from src.logger import configure_logging, get_default_log_level
from src.module_loader.archive import collect_module_requirements

STATUS_FILE = os.path.join(BASE_DIR, ".dependency_resolution_status")

logger = logging.getLogger(__name__)


def _write_status(state: str, message: str = "") -> None:
    """Write the resolution status file for the health endpoint to read."""
    try:
        dir_name = os.path.dirname(STATUS_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".dep_status_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"state": state, "message": message}, f)
            os.replace(tmp_path, STATUS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.warning(f"Failed to write dependency resolution status file: {e}")


def main() -> int:
    logger_instance = configure_logging(log_level=get_default_log_level())
    logger_instance.warning("Running dependency resolution as root...")

    _write_status("pending", "Initializing dependency resolution...")

    try:
        from chacc import DependencyManager

        _write_status("running", "Resolving module dependencies...")

        modules_requirements = asyncio.run(collect_module_requirements())

        if not modules_requirements:
            logger_instance.info("No module requirements found, skipping resolution.")
            _write_status("done", "No module requirements found, skipped")
            return 0

        dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=logger_instance)
        asyncio.run(dm.resolve_dependencies(modules_requirements))
        logger_instance.info("Dependency resolution completed successfully.")
        _write_status("done", "Resolution completed successfully")
        return 0
    except Exception as e:  # noqa: BLE001
        logger_instance.error(f"Dependency resolution failed: {e}")
        _write_status("failed", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
