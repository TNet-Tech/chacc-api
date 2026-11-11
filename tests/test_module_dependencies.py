"""Tests for module dependencies (``module_dependencies`` in module_meta.json)."""

import io
import json
import logging
import zipfile

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import app
from src.module_graph import (
    DependencyDeclarationError,
    archive_metas,
    check_graph,
    declared_dependencies,
    dependents_of,
    missing_dependencies,
    scan_module_directory,
)


def meta(name, required=(), optional=()):
    return {
        "name": name,
        "module_dependencies": {"required": list(required), "optional": list(optional)},
    }


# ---------- Declaration ----------


def test_no_declaration_means_no_dependencies():
    assert declared_dependencies({"name": "a"}) == ([], [])


def test_declaration_is_parsed_and_deduplicated():
    m = {"name": "a", "module_dependencies": {"required": ["b", "b"], "optional": ["c"]}}
    assert declared_dependencies(m) == (["b"], ["c"])


@pytest.mark.parametrize(
    "block, message",
    [
        (["b"], "must be an object"),
        ({"required": "b"}, "list of module names"),
        ({"requires": ["b"]}, "Unknown key"),
        ({"required": ["not a name"]}, "Invalid module name"),
        ({"required": ["a"]}, "cannot depend on itself"),
        ({"required": ["b"], "optional": ["b"]}, "both required and optional"),
    ],
)
def test_invalid_declarations_are_rejected(block, message):
    with pytest.raises(DependencyDeclarationError, match=message):
        declared_dependencies({"name": "a", "module_dependencies": block})


def test_missing_dependencies():
    missing = missing_dependencies(meta("menu", ["auth"], ["files"]), {"auth"})
    assert missing.required == []
    assert missing.optional == ["files"]


# ---------- Graph ----------


def test_missing_required_blocks_module_and_its_dependents():
    report = check_graph(
        {
            "menu": meta("menu", ["auth"]),
            "reports": meta("reports", ["menu"]),
            "outbound": meta("outbound"),
        }
    )
    assert report.order == ["outbound"]
    assert "missing required module(s): auth" in report.blocked["menu"]
    assert "required module(s) not loaded: menu" in report.blocked["reports"]


def test_missing_optional_only_reported():
    report = check_graph({"menu": meta("menu", optional=["files"])})
    assert report.order == ["menu"]
    assert report.missing_optional == {"menu": ["files"]}
    assert report.blocked == {}


def test_dependencies_load_first():
    report = check_graph(
        {
            "menu": meta("menu", ["auth"], ["files"]),
            "files": meta("files", ["auth"]),
            "auth": meta("auth"),
        }
    )
    assert report.order == ["auth", "files", "menu"]
    assert report.problems() == []


def test_required_cycle_blocks_only_the_cycle():
    report = check_graph(
        {"a": meta("a", ["b"]), "b": meta("b", ["a"]), "c": meta("c"), "d": meta("d", ["a"])}
    )
    assert set(report.blocked) == {"a", "b", "d"}
    assert "cycle" in report.blocked["a"]
    assert report.order == ["c"]


def test_optional_cycle_does_not_block():
    report = check_graph({"a": meta("a", optional=["b"]), "b": meta("b", optional=["a"])})
    assert sorted(report.order) == ["a", "b"]
    assert report.blocked == {}


def test_invalid_declaration_blocks_module():
    report = check_graph({"a": {"name": "a", "module_dependencies": "auth"}})
    assert "a" in report.blocked and "a" in report.invalid


def test_dependents_of():
    modules = {"menu": meta("menu", ["auth"]), "out": meta("out", optional=["auth"])}
    assert dependents_of("auth", modules) == ["menu"]


def test_scan_directories(tmp_path):
    (tmp_path / "plugins" / "auth").mkdir(parents=True)
    (tmp_path / "plugins" / "auth" / "module_meta.json").write_text(json.dumps(meta("auth")))
    nested = tmp_path / "plugins" / "repo" / "menu"
    nested.mkdir(parents=True)
    (nested / "module_meta.json").write_text(json.dumps(meta("menu", ["auth"])))
    (tmp_path / "plugins" / "broken").mkdir()
    (tmp_path / "plugins" / "broken" / "module_meta.json").write_text("{not json")
    assert set(scan_module_directory(str(tmp_path / "plugins"))) == {"auth", "menu"}

    installed = tmp_path / "installed"
    installed.mkdir()
    with zipfile.ZipFile(installed / "x.chacc", "w") as zf:
        zf.writestr("module_meta.json", json.dumps(meta("auth")))
    (installed / "junk.chacc").write_bytes(b"nope")
    assert set(archive_metas(str(installed))) == {"auth"}


# ---------- Module management API ----------


def chacc_bytes(m):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("module_meta.json", json.dumps(m))
    buf.seek(0)
    return buf


@pytest.fixture
def client(monkeypatch, tmp_path):
    from src import modules

    monkeypatch.setattr(modules, "MODULES_INSTALLED_DIR", str(tmp_path / "installed"))
    monkeypatch.setattr(modules, "MODULES_LOADED_DIR", str(tmp_path / "loaded"))
    (tmp_path / "installed").mkdir()
    (tmp_path / "loaded").mkdir()
    return TestClient(app)


def set_available(monkeypatch, names):
    from src import modules

    monkeypatch.setattr(
        modules, "available_module_metas", lambda db=None, dev=None: {n: meta(n) for n in names}
    )


def test_upload_refused_when_required_module_missing(client, monkeypatch, tmp_path):
    set_available(monkeypatch, ["outbound"])
    response = client.post(
        "/api/modules/",
        files={"file": ("menu.chacc", chacc_bytes(meta("menu", ["auth"], ["files"])))},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["missing_dependencies"] == {"required": ["auth"], "optional": ["files"]}
    assert "auth" in body["detail"]
    assert list((tmp_path / "installed").iterdir()) == []


def test_upload_with_missing_optional_succeeds_with_warning(client, monkeypatch, tmp_path):
    import src.chacc_dependency_manager as dm_mod

    class FakeDM:
        def __init__(self, *a, **k):
            self.dm = self

        async def resolve_dependencies(self, *a, **k):
            return None

    monkeypatch.setattr(dm_mod, "ChaCCDependencyManager", FakeDM)
    set_available(monkeypatch, ["auth"])
    response = client.post(
        "/api/modules/",
        files={"file": ("menu.chacc", chacc_bytes(meta("menu", ["auth"], ["files"])))},
    )
    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    assert len(warnings) == 1 and "files" in warnings[0]
    assert (tmp_path / "installed" / "menu.chacc").exists()


def test_upload_invalid_declaration_is_400(client, monkeypatch):
    set_available(monkeypatch, [])
    bad = {"name": "menu", "module_dependencies": {"required": "auth"}}
    response = client.post("/api/modules/", files={"file": ("menu.chacc", chacc_bytes(bad))})
    assert response.status_code == 400
    assert "module_dependencies" in response.json()["detail"]


def test_list_modules_shows_dependencies(client, monkeypatch):
    from src.database import ModuleRecord, SessionLocal

    set_available(monkeypatch, ["dep_test_menu"])
    db = SessionLocal()
    try:
        db.query(ModuleRecord).filter_by(name="dep_test_menu").delete()
        db.add(
            ModuleRecord(
                name="dep_test_menu",
                version="1.0.0",
                is_enabled=True,
                base_path_prefix="/dep-test-menu",
                meta_data=meta("dep_test_menu", ["auth"], ["files"]),
            )
        )
        db.commit()
        modules = client.get("/api/modules/").json()["modules"]
        entry = next(m for m in modules if m["name"] == "dep_test_menu")
        assert entry["dependencies"] == {"required": ["auth"], "optional": ["files"]}
        assert entry["missing_dependencies"] == {"required": ["auth"], "optional": ["files"]}
    finally:
        db.query(ModuleRecord).filter_by(name="dep_test_menu").delete()
        db.commit()
        db.close()


# ---------- Startup (dev loader) ----------


def test_dev_loader_skips_blocked_modules_before_model_discovery(monkeypatch):
    import asyncio

    import src.database
    import src.migration.runner
    from src import plugin_loader

    calls = []

    async def fake_load(module_name, discover_only=False, **kwargs):
        calls.append((module_name, discover_only))
        return True

    async def fake_migration(mode=None, **kwargs):
        calls.append(("migration", mode))

    monkeypatch.setattr(plugin_loader, "load_single_module", fake_load)
    monkeypatch.setattr(plugin_loader, "resolve_dependencies", lambda *a: _noop())
    monkeypatch.setattr(src.migration.runner, "run_migration", fake_migration)
    monkeypatch.setattr(src.database, "initialize_database_models", lambda ctx: None)
    monkeypatch.setattr(plugin_loader, "apply_deferred_schema_changes", lambda ctx: False)
    monkeypatch.setattr(plugin_loader._module_state, "should_reload", lambda *a: True)
    monkeypatch.setattr("src.module_loader.loader.MIGRATION_MODE", "full")
    # Collect log lines directly; the ChaCC logger does not reach caplog.
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    test_logger = logging.getLogger("test_module_deps")
    test_logger.addHandler(handler)
    monkeypatch.setattr(plugin_loader, "chacc_logger", test_logger)

    modules = {
        name: {"name": name, "module_path": f"/x/{name}", "meta": m}
        for name, m in {
            "menu": meta("menu", ["auth"]),
            "files": meta("files", optional=["outbound"]),
            "core": meta("core"),
        }.items()
    }
    asyncio.run(plugin_loader._load_modules(None, None, modules, None, None, "plugins"))
    test_logger.removeHandler(handler)
    log = "\n".join(lines)

    loaded = [c[0] for c in calls if c[0] != "migration"]
    assert "menu" not in loaded
    assert set(loaded) == {"files", "core"}
    # Something was skipped, so 'full' must not drop its tables.
    assert ("migration", "auto") in calls
    assert "MODULE DEPENDENCIES NEED ATTENTION" in log
    assert "menu: NOT LOADED - missing required module(s): auth" in log
    assert "files: optional module(s) not installed: outbound" in log


async def _noop():
    return None
