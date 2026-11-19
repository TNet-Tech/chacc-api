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


def _reload_dirs():
    """
    What the development server watches.

    Plugin hot reload on (ENABLE_PLUGIN_HOT_RELOAD=True): the whole project
    folder, so src/, main.py and the modules in plugins/ restart the server.
    plugins/ is added when it is configured outside the project.

    Off: only src/. Uvicorn's default reloader can't leave a folder out of a
    watched one, so the project folder itself isn't watched. A project without
    src/ then doesn't reload at all.
    """
    if ENABLE_PLUGIN_HOT_RELOAD:
        dirs = ["."]
        if get_relative_path(PLUGINS_DIR) is None and os.path.isdir(PLUGINS_DIR):
            dirs.append(PLUGINS_DIR)
        return dirs
    return [d for d in ("src",) if os.path.isdir(os.path.join(BASE_DIR, d))]


_RELOAD_DIRS = _reload_dirs()

_host = os.environ.get("CHACC_HOST", "0.0.0.0")
_port = int(os.environ.get("CHACC_PORT", "8085"))

config = {
    "app": "main:app",
    "host": _host,
    "port": _port,
    # With nothing to watch, uvicorn would fall back to the whole folder.
    "reload": bool(_RELOAD_DIRS),
    # Seconds to let in-flight requests finish on shutdown/restart before forcing it.
    "timeout_graceful_shutdown": int(os.environ.get("CHACC_GRACEFUL_SHUTDOWN_TIMEOUT", "30")),
    # See _reload_dirs. Plugin hot reload used to watch the project folder only as
    # a side effect of an empty exclude pattern, so it is spelled out there.
    "reload_dirs": _RELOAD_DIRS,
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
    ),
}

if not _RELOAD_DIRS:
    # Uvicorn warns about reload settings when it doesn't reload.
    del config["reload_dirs"], config["reload_excludes"]

if __name__ == "__main__":
    import uvicorn

    from src.lifecycle import run_server

    run_server(lambda: uvicorn.run(**config))
