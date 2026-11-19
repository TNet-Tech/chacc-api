"""
Process-level restart plumbing shared by the launcher and the API.

Kept free of FastAPI/database imports so the launchers
(``start_server.py`` / ``uvicorn_config.py``) can use it cheaply.
See :mod:`src.system` for the full restart flow.
"""

import os
import signal
import sys
from collections.abc import Callable

from src.constants import DEPENDENCY_CACHE_DIR

RESTART_EXIT_CODE = 75
SUPERVISED_ENV = "CHACC_SUPERVISED"
SERVER_ROOT_PID_ENV = "CHACC_SERVER_ROOT_PID"


def restart_supported() -> bool:
    return os.environ.get(SUPERVISED_ENV) == "1" and bool(os.environ.get(SERVER_ROOT_PID_ENV))


def marker_path(root_pid: int | str) -> str:
    return os.path.join(DEPENDENCY_CACHE_DIR, f"restart-{root_pid}.request")


def request_restart(root_pid: int, note: str = "") -> None:
    os.makedirs(DEPENDENCY_CACHE_DIR, exist_ok=True)
    with open(marker_path(root_pid), "w") as f:
        f.write(note)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def consume_restart_request() -> bool:
    path = marker_path(os.getpid())
    if os.path.exists(path):
        _remove(path)
        return True
    return False


def _sigterm_handler(signum, frame):
    """
    Uvicorn handles SIGTERM itself (graceful shutdown), restores the previous
    handler — this one — and re-raises the signal. Turn that into the restart
    exit code when a restart was requested; otherwise die by SIGTERM as usual.
    """
    if consume_restart_request():
        sys.exit(RESTART_EXIT_CODE)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGTERM)


def run_server(run: Callable[[], None]) -> None:
    """
    Run ``run`` (which calls ``uvicorn.run``) with restart support.

    - exports this PID so the API (possibly in a reload worker) knows whom to signal;
    - exits with :data:`RESTART_EXIT_CODE` after a requested graceful shutdown.
    """
    os.environ[SERVER_ROOT_PID_ENV] = str(os.getpid())
    _remove(marker_path(os.getpid()))
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sigterm_handler)

    run()

    if consume_restart_request():
        sys.exit(RESTART_EXIT_CODE)
