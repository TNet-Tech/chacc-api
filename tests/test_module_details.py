"""Module load status, failure reasons and the details shown in the console."""

import asyncio
import json
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from src import module_details, module_packages, module_status
from src.module_loader.loader import load_single_module


@pytest.fixture(autouse=True)
def isolated_status(tmp_path, monkeypatch):
    """Each test gets its own failures file and an empty load registry."""
    monkeypatch.setattr(module_status, "FAILURES_FILE", str(tmp_path / "module_failures.json"))
    monkeypatch.setattr(module_status, "_loaded", {})


def make_module(root, name, main_code, meta=None):
    """A module folder like an extracted archive: module_meta.json + module/main.py."""
    folder = root / name
    (folder / "module").mkdir(parents=True)
    (folder / "module" / "__init__.py").write_text("")
    (folder / "module" / "main.py").write_text(main_code)
    meta = {
        "name": name,
        "version": "0.1.0",
        "entry_point": "module.main:setup_plugin",
        **(meta or {}),
    }
    (folder / "module_meta.json").write_text(json.dumps(meta))
    return str(folder), meta


def load(folder, name, meta, discover_first=True):
    app = FastAPI()
    context = SimpleNamespace(logger=__import__("logging").getLogger("test"))

    async def run():
        if discover_first:  # as the server does: model discovery, then loading
            await load_single_module(name, folder, meta, app, context, discover_only=True)
        return await load_single_module(name, folder, meta, app, context)

    try:
        return asyncio.run(run())
    finally:
        for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
            del sys.modules[mod]


def test_successful_load_is_recorded_and_clears_an_old_failure(tmp_path):
    module_status.mark_failed("good_mod", "old problem")
    folder, meta = make_module(
        tmp_path,
        "good_mod",
        "from fastapi import APIRouter\n\ndef setup_plugin(context):\n    return APIRouter()\n",
    )
    assert load(folder, "good_mod", meta) is True
    assert module_status.loaded("good_mod")["api_path"] == "/api/good_mod"
    assert module_status.failure("good_mod") is None


def test_missing_package_reports_the_real_import_error(tmp_path):
    """Model discovery used to leave a half-imported module behind, which hid the
    real error behind 'setup function not found'."""
    folder, meta = make_module(
        tmp_path,
        "broken_mod",
        "import totally_missing_package_xyz\n\ndef setup_plugin(context):\n    pass\n",
    )
    assert load(folder, "broken_mod", meta) is False
    reason = module_status.failure("broken_mod")["reason"]
    assert reason == "Its code couldn't be imported: No module named 'totally_missing_package_xyz'"
    assert module_status.loaded("broken_mod") is None


@pytest.mark.parametrize(
    ("main_code", "meta", "expected"),
    [
        ("def other():\n    pass\n", None, "The setup function 'setup_plugin' wasn't found"),
        ("def setup_plugin(context):\n    return None\n", None, "didn't return an APIRouter"),
        ("", {"entry_point": "nonsense"}, "no valid 'entry_point'"),
        ("", {"entry_point": "module.missing:setup_plugin"}, "entry point file is missing"),
    ],
)
def test_failure_reasons_are_plain(tmp_path, main_code, meta, expected):
    folder, full_meta = make_module(tmp_path, "odd_mod", main_code, meta)
    assert load(folder, "odd_mod", full_meta) is False
    assert expected in module_status.failure("odd_mod")["reason"]


def test_setup_exception_is_recorded_and_raised(tmp_path):
    folder, meta = make_module(
        tmp_path, "boom_mod", "def setup_plugin(context):\n    raise ValueError('bad config')\n"
    )
    with pytest.raises(ValueError):
        load(folder, "boom_mod", meta)
    assert module_status.failure("boom_mod")["reason"] == "ValueError: bad config"


def test_failures_survive_a_restart_and_can_be_forgotten():
    module_status.mark_failed("m", "it broke")
    module_status._loaded.clear()  # a new process only has the file
    assert module_status.failure("m")["reason"] == "it broke"
    module_status.forget("m")
    assert module_status.failure("m") is None


def test_requirement_report(monkeypatch):
    monkeypatch.setattr(module_packages, "target_versions", dict)
    monkeypatch.setattr(
        module_packages, "site_versions", lambda: {"requests": "2.32.0", "qrcode": "6.0"}
    )
    report = module_packages.requirement_report(
        "requests>=2.0  # http\nqrcode>=7.4\nnot-installed-pkg\n\n-r other.txt\n"
    )
    assert [(r["name"], r["installed"], r["ok"]) for r in report] == [
        ("requests", "2.32.0", True),
        ("qrcode", "6.0", False),
        ("not-installed-pkg", None, False),
    ]


def record(**fields):
    defaults = {"name": "m", "is_enabled": True}
    return types.SimpleNamespace(**{**defaults, **fields})


@pytest.mark.parametrize(
    ("setup", "enabled", "node", "code"),
    [
        (lambda: module_status.mark_loaded("m", "/api/m"), True, None, "loaded"),
        (lambda: module_status.mark_loaded("m", "/api/m"), False, None, "stopping"),
        (lambda: module_status.mark_failed("m", "x"), False, None, "failed"),
        (lambda: None, False, None, "disabled"),
        (lambda: None, True, {"state": "blocked", "reason": "needs auth"}, "blocked"),
        (lambda: None, True, {"state": "ok"}, "pending"),
    ],
)
def test_state(monkeypatch, setup, enabled, node, code):
    monkeypatch.setattr(module_details, "DEVELOPMENT_MODE", False)
    setup()
    state = module_details._state(record(is_enabled=enabled), node, 3)
    assert state["code"] == code
    if code == "loaded":
        assert state["message"] == "Running. Serves 3 routes under /api/m."
    if code == "failed":
        assert state["reason"] == "x"


def test_state_in_development_for_a_module_not_in_plugins(monkeypatch):
    monkeypatch.setattr(module_details, "DEVELOPMENT_MODE", True)
    state = module_details._state(record(), None, 0)
    assert "Not in plugins/" in state["message"]


def test_routes_come_from_the_schema_including_nested_routers():
    from fastapi import APIRouter

    def endpoint():
        return None

    inner = APIRouter()
    inner.add_api_route("/items", endpoint, methods=["GET"])
    outer = APIRouter()
    outer.include_router(inner, prefix="/shop")
    outer.add_api_route("/orders", endpoint, methods=["POST"])
    app = FastAPI()
    app.include_router(outer, prefix="/api/demo")
    app.add_api_route("/api/demography", endpoint, methods=["GET"])  # same start, other module

    assert module_details._routes(app, "/api/demo") == [
        {"methods": ["POST"], "path": "/api/demo/orders"},
        {"methods": ["GET"], "path": "/api/demo/shop/items"},
    ]


def test_used_by():
    graph = {
        "edges": [
            {"from": "menu", "to": "auth", "kind": "required"},
            {"from": "files", "to": "auth", "kind": "optional"},
            {"from": "menu", "to": "files", "kind": "optional"},
        ]
    }
    assert module_details._used_by("auth", graph) == {"required": ["menu"], "optional": ["files"]}


def test_details_endpoint_404_and_graph_route_still_works():
    from fastapi.testclient import TestClient

    from chacc_api.server.main import app

    client = TestClient(app)
    response = client.get("/api/modules/no_such_module_xyz")
    assert response.status_code == 404
    assert response.json()["detail"] == "Module not found."
    assert "nodes" in client.get("/api/modules/graph").json()
