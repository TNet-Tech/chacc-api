"""Development-mode uvicorn settings."""

import os

from chacc_api.server import uvicorn_config


def test_reload_excludes_are_relative_even_for_folders_outside_the_project(monkeypatch):
    """Uvicorn refuses absolute reload patterns, e.g. MODULES_INSTALLED_DIR=/srv/chacc/modules."""
    base = uvicorn_config.BASE_DIR
    assert (
        uvicorn_config.get_relative_path(os.path.join(base, ".modules_loaded")) == ".modules_loaded"
    )
    assert uvicorn_config.get_relative_path("/srv/chacc/modules") is None
    assert uvicorn_config.get_relative_path(base + "-other/x") is None  # a sibling, not inside

    excludes = uvicorn_config.config["reload_excludes"]
    assert excludes and all(p and not os.path.isabs(p) for p in excludes)
