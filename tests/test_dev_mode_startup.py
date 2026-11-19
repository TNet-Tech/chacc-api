"""
Development mode and ENABLE_PLUGIN_HOT_RELOAD.

By design the setting covers both: with it on, the server restarts when plugins/
changes and the plugins' tables are created before their setup runs. With it
off, neither happens.
"""

import asyncio
import json
import logging
import sys
import textwrap
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import inspect

from src import plugin_loader
from src.core_services import BackboneContext
from src.database import engine, get_async_db, get_db


def write_plugin(plugins_dir, module, table):
    root = plugins_dir / module
    (root / "probe").mkdir(parents=True)
    (root / "module_meta.json").write_text(
        json.dumps(
            {
                "name": module,
                "version": "1.0.0",
                "entry_point": "probe.main:setup_plugin",
                "base_path_prefix": "/devstart-probe",
            }
        )
    )
    (root / "probe" / "__init__.py").write_text("")
    (root / "probe" / "models.py").write_text(
        textwrap.dedent(
            f"""
            from sqlalchemy import Column, String

            from src.database import ChaCCBaseModel


            class ProbeItem(ChaCCBaseModel):
                __tablename__ = "{table}"
                label = Column(String, nullable=True)
            """
        )
    )
    (root / "probe" / "main.py").write_text(
        textwrap.dedent(
            f"""
            from fastapi import APIRouter
            from sqlalchemy import inspect

            from src.database import engine

            SEEN = {{}}


            def setup_plugin(context):
                # Like real modules: setup reads its own tables.
                SEEN["table_existed"] = inspect(engine).has_table("{table}")
                return APIRouter()
            """
        )
    )


def load_plugin(tmp_path, monkeypatch, *, hot_reload, module, table):
    monkeypatch.setattr("src.module_loader.loader.MIGRATION_MODE", "auto")
    monkeypatch.setattr(plugin_loader, "ENABLE_PLUGIN_HOT_RELOAD", hot_reload)
    write_plugin(tmp_path, module, table)
    assert not inspect(engine).has_table(table)

    app = FastAPI()
    context = BackboneContext(
        app=app,
        limiter=None,
        logger=logging.getLogger("test"),
        db_session_factory=get_db,
        async_db_session_factory=get_async_db,
    )
    modules = plugin_loader.discover_modules_from_directory(str(tmp_path))
    try:
        asyncio.run(
            plugin_loader._load_modules(
                app=app,
                backbone_context=context,
                modules=modules,
                only_modules=[],
                exclude_modules=[],
                source="plugins",
            )
        )
        return dict(sys.modules[f"{module}.probe.main"].SEEN)
    finally:
        for name in [m for m in sys.modules if m.startswith(module)]:
            del sys.modules[name]


def test_hot_reload_on_creates_tables_before_setup(tmp_path, monkeypatch):
    seen = load_plugin(
        tmp_path, monkeypatch, hot_reload=True, module="devon_probe", table="devon_probe_items"
    )
    assert inspect(engine).has_table("devon_probe_items")
    assert seen == {"table_existed": True}


def test_hot_reload_off_creates_no_tables(tmp_path, monkeypatch):
    seen = load_plugin(
        tmp_path, monkeypatch, hot_reload=False, module="devoff_probe", table="devoff_probe_items"
    )
    assert not inspect(engine).has_table("devoff_probe_items")
    assert seen == {"table_existed": False}  # setup still runs


def watched_dirs(monkeypatch, hot_reload):
    from uvicorn.config import Config

    from chacc_api.server import uvicorn_config

    monkeypatch.setattr(uvicorn_config, "ENABLE_PLUGIN_HOT_RELOAD", hot_reload)
    dirs = uvicorn_config._reload_dirs()
    if not dirs:
        return []
    config = Config(app="main:app", reload=True, reload_dirs=dirs)
    return [d.resolve() for d in config.reload_dirs]


def watches(dirs, folder):
    folder = Path(folder).resolve()
    return any(d == folder or d in folder.parents for d in dirs)


def test_hot_reload_on_watches_plugins(monkeypatch):
    from chacc_api.server import uvicorn_config

    assert watches(watched_dirs(monkeypatch, True), uvicorn_config.PLUGINS_DIR)


def test_hot_reload_off_does_not_watch_plugins(monkeypatch):
    from chacc_api.server import uvicorn_config

    dirs = watched_dirs(monkeypatch, False)
    assert not watches(dirs, uvicorn_config.PLUGINS_DIR)
    assert dirs == [Path(uvicorn_config.BASE_DIR, "src").resolve()]  # core code still reloads
