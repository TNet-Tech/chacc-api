"""
The web console's module list and details in development mode come from
plugins/, like the dependency graph; in production from the installed modules.
"""

import json

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import app
from src import module_details, module_status, module_view
from src.database import ModuleRecord, SessionLocal
from src.module_loader import dependencies


def write_plugin(folder, name, **meta):
    folder.mkdir(parents=True)
    (folder / "module_meta.json").write_text(
        json.dumps({"name": name, "display_name": name.title(), "version": "1.2.0", **meta})
    )
    return folder


@pytest.fixture
def plugins(tmp_path, monkeypatch):
    """Development mode with two plugins: one directly in plugins/, one nested in a repo."""
    directory = tmp_path / "plugins"
    write_plugin(
        directory / "menu",
        "menu",
        author="Kitchen team",
        module_dependencies={"required": ["auth"], "optional": []},
    )
    nested = write_plugin(directory / "files-repo" / "files", "files", description="File storage")
    (nested / "README.md").write_text("# Files\n\nStores files.")
    (nested / "requirements.txt").write_text("not-installed-package-xyz==1.0\n")

    for target in (module_view, dependencies):
        monkeypatch.setattr(target, "PLUGINS_DIR", str(directory))
        monkeypatch.setattr(target, "DEVELOPMENT_MODE", True)
    monkeypatch.setattr(module_details, "DEVELOPMENT_MODE", True)
    yield directory
    for name in ("menu", "files"):
        module_status.forget(name)


@pytest.fixture
def installed_record():
    """A module uploaded earlier: a row in the modules table."""
    with SessionLocal() as db:
        db.add(ModuleRecord(name="billing", version="2.0.0", is_enabled=True, meta_data={}))
        db.commit()
    yield "billing"
    with SessionLocal() as db:
        db.query(ModuleRecord).filter_by(name="billing").delete()
        db.commit()


@pytest.fixture
def client():
    return TestClient(app)


def test_development_lists_the_plugins_not_the_installed_modules(client, plugins, installed_record):
    modules = {m["name"]: m for m in client.get("/api/modules/").json()["modules"]}

    assert set(modules) == {"menu", "files"}  # files is nested one folder down
    assert all(m["source"] == "plugins" and m["is_enabled"] for m in modules.values())
    assert modules["menu"]["display_name"] == "Menu"
    assert modules["menu"]["author"] == "Kitchen team"
    assert modules["files"]["description"] == "File storage"
    # Dependencies are checked against the other plugins, like the graph does.
    assert modules["menu"]["missing_dependencies"]["required"] == ["auth"]


def test_plugin_state_comes_from_the_last_load(client, plugins):
    module_status.mark_loaded("files", "/api/files")
    module_status.mark_failed("menu", "ImportError: no module named qrcode")

    modules = {m["name"]: m for m in client.get("/api/modules/").json()["modules"]}

    assert modules["files"]["is_loaded"] is True
    assert modules["menu"]["load_failure"] == "ImportError: no module named qrcode"


def test_plugin_details_read_the_plugin_folder(client, plugins):
    details = client.get("/api/modules/files").json()

    assert details["source"] == "plugins"
    assert details["display_name"] == "Files"
    assert details["readme"].startswith("# Files")
    assert [p["requirement"] for p in details["packages"]] == ["not-installed-package-xyz==1.0"]
    assert details["archive"] is None
    assert details["state"]["code"] == "pending"
    assert "development server" in details["state"]["message"]


def test_unknown_plugin_is_not_found(client, plugins):
    assert client.get("/api/modules/nothing-here").status_code == 404


def test_production_lists_the_installed_modules(client, installed_record, monkeypatch):
    monkeypatch.setattr(module_view, "DEVELOPMENT_MODE", False)

    modules = {m["name"]: m for m in client.get("/api/modules/").json()["modules"]}

    assert modules["billing"]["source"] == "installed"
    assert client.get("/api/modules/billing").json()["source"] == "installed"
