"""
Uvicorn configuration for development mode with auto-reload.
Reads host, port, and debug settings from environment variables.
"""

import os

from chacc_api.utils import (
    BACKBONE_REQUIREMENTS_LOCK_FILE,
    BASE_DIR,
    DEPENDENCY_CACHE_DIR,
    DEPENDENCY_CACHE_FILE,
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_HOT_RELOAD,
    MODULES_INSTALLED_DIR,
    MODULES_LOADED_DIR,
    MODULES_UPLOAD_DIR,
    PLUGINS_DIR,
)


def get_relative_path(abs_path):
    """
    The path relative to the project, or None when it lies outside it.

    Uvicorn accepts only relative reload patterns, and folders outside the
    project (for example MODULES_INSTALLED_DIR=/srv/chacc/modules) aren't
    watched anyway, so they need no exclude.
    """
    relative = os.path.relpath(abs_path, BASE_DIR)
    return None if relative == ".." or relative.startswith(".." + os.sep) else relative


def _excludes(*patterns):
    return [p for p in patterns if p]


def _dir(abs_path):
    relative = get_relative_path(abs_path)
    return f"{relative}/" if relative else None


# Read host and port from environment variables (set by CLI --host / --port)
_host = os.environ.get("CHACC_HOST", "0.0.0.0")
_port = int(os.environ.get("CHACC_PORT", "8085"))

config = {
    "app": "main:app",
    "host": _host,
    "port": _port,
    "reload": True,
    # Seconds to let in-flight requests finish on shutdown/restart before forcing it.
    "timeout_graceful_shutdown": int(os.environ.get("CHACC_GRACEFUL_SHUTDOWN_TIMEOUT", "30")),
    "reload_dirs": ["src", "main.py"],
    "reload_excludes": _excludes(
        _dir(MODULES_LOADED_DIR),
        _dir(MODULES_UPLOAD_DIR),
        _dir(DEPENDENCY_CACHE_DIR),
        get_relative_path(BACKBONE_REQUIREMENTS_LOCK_FILE),
        _dir(MODULES_INSTALLED_DIR),
        get_relative_path(DEPENDENCY_CACHE_FILE),
        "*.chacc",
        "__pycache__",
        ".pytest_cache",
        "tests/",
        "*.pyc",
        "*.db",
        "*.log",
        ".env",
        (
            _dir(PLUGINS_DIR)
            if "/" in (get_relative_path(PLUGINS_DIR) or "")
            else (
                get_relative_path(PLUGINS_DIR)
                if not DEVELOPMENT_MODE and ENABLE_PLUGIN_HOT_RELOAD
                else None
            )
        ),
    ),
}

if __name__ == "__main__":
    import uvicorn

    from src.lifecycle import run_server

    run_server(lambda: uvicorn.run(**config))
