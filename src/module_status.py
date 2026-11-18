"""
What happened to each module when the server started: loaded (and where it is
mounted) or failed (with the reason).

The load state is kept in memory for this server process. Failures are also
written to ``module_failures.json`` in the cache folder, because a module that
fails in production is disabled and isn't tried again on the next start, so
the reason would otherwise be lost. A failure is cleared when the module loads,
or is enabled, updated or uninstalled.
"""

import json
import os
import threading
import time

from src.constants import DEPENDENCY_CACHE_DIR
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

FAILURES_FILE = os.path.join(DEPENDENCY_CACHE_DIR, "module_failures.json")

_loaded: dict[str, dict] = {}
_lock = threading.Lock()


def _read_failures() -> dict:
    try:
        with open(FAILURES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_failures(failures: dict) -> None:
    try:
        os.makedirs(os.path.dirname(FAILURES_FILE), exist_ok=True)
        tmp = f"{FAILURES_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=2)
        os.replace(tmp, FAILURES_FILE)
    except OSError as e:
        chacc_logger.warning(f"Could not save module load failures: {e}")


def mark_loaded(name: str, api_path: str) -> None:
    """The module loaded and is mounted at ``api_path``."""
    _loaded[name] = {"loaded_at": time.time(), "api_path": api_path}
    clear_failure(name)


def mark_failed(name: str, reason: str) -> None:
    _loaded.pop(name, None)
    with _lock:
        failures = _read_failures()
        failures[name] = {"reason": reason, "at": time.time()}
        _write_failures(failures)


def clear_failure(name: str) -> None:
    with _lock:
        failures = _read_failures()
        if failures.pop(name, None) is not None:
            _write_failures(failures)


def forget(name: str) -> None:
    """The module was uninstalled."""
    _loaded.pop(name, None)
    clear_failure(name)


def loaded(name: str) -> dict | None:
    return _loaded.get(name)


def failure(name: str) -> dict | None:
    return _read_failures().get(name)
