"""Tests for the web console: pages, auth discovery, restart protection, graph API."""

import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import _auth_info, app
from src import lifecycle, system
from src.module_loader import dependencies


def meta(name, required=(), optional=()):
    return {
        "name": name,
        "display_name": name.title(),
        "version": "1.0.0",
        "module_dependencies": {"required": list(required), "optional": list(optional)},
    }


def write_archive(directory, m):
    with zipfile.ZipFile(directory / f"{m['name']}.chacc", "w") as zf:
        zf.writestr("module_meta.json", json.dumps(m))


class FakeContext:
    def __init__(self, user):
        self.user = user

    def get_service(self, name):
        if name != "get_current_user":
            return None

        async def get_current_user(credentials):
            return self.user if credentials.credentials == "good-token" else None

        return get_current_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def with_auth():
    previous = app.state.backbone_context
    app.state.backbone_context = FakeContext(user={"username": "admin"})
    yield
    app.state.backbone_context = previous


@pytest.fixture(autouse=True)
def _reset_restart_state(monkeypatch):
    monkeypatch.setattr(system, "_restart_pending", False)
    monkeypatch.setattr(system, "_restart_task", None)


# ---------- Pages ----------


def test_console_page_is_served(client):
    response = client.get("/console")
    assert response.status_code == 200
    assert "/static/js/console.js" in response.text
    assert 'content="/api"' in response.text
    for asset in ("/static/js/console.js", "/static/css/console.css"):
        assert client.get(asset).status_code == 200


def test_landing_page_links_to_console(client):
    assert 'href="/console"' in client.get("/").text


# ---------- Auth discovery and restart protection ----------


def test_discovery_reports_no_auth_without_auth_module(client):
    data = client.get("/.well-known/chacc").json()
    assert data["auth"] == {"required": False, "login_path": None}
    assert data["mode"] in {"development", "production"}


def test_auth_info_finds_login_route_in_nested_routers():
    """Module routers are included as nested routers; the login route must still be found."""
    from fastapi import APIRouter, FastAPI

    module_app = FastAPI()
    module_app.state.backbone_context = FakeContext(1)
    for prefix in ("/api/other", "/api/authentication"):
        router = APIRouter()
        router.add_api_route("/login", lambda: None, methods=["POST"])
        module_app.include_router(router, prefix=prefix)

    request = SimpleNamespace(app=module_app)
    assert _auth_info(request) == {"required": True, "login_path": "/api/authentication/login"}


def test_restart_requires_login_when_auth_module_loaded(client, with_auth, monkeypatch):
    monkeypatch.delenv(lifecycle.SUPERVISED_ENV, raising=False)
    assert client.post("/api/system/restart").status_code == 401
    bad = client.post("/api/system/restart", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    # With a valid token the request gets past auth (and is refused: not supervised).
    ok = client.post("/api/system/restart", headers={"Authorization": "Bearer good-token"})
    assert ok.status_code == 409


def test_restart_open_without_auth_module(client, monkeypatch):
    monkeypatch.delenv(lifecycle.SUPERVISED_ENV, raising=False)
    assert client.post("/api/system/restart").status_code == 409


def test_graph_requires_login_when_auth_module_loaded(client, with_auth):
    assert client.get("/api/modules/graph").status_code == 401


# ---------- Graph ----------


@pytest.fixture
def installed(tmp_path, monkeypatch):
    directory = tmp_path / "installed"
    directory.mkdir()
    monkeypatch.setattr(dependencies, "MODULES_INSTALLED_DIR", str(directory))
    monkeypatch.setattr(dependencies, "DEVELOPMENT_MODE", False)
    return directory


def test_graph_payload_production(installed):
    write_archive(installed, meta("menu", ["auth"], ["files"]))
    write_archive(installed, meta("outbound", [], ["menu"]))
    write_archive(installed, meta("billing"))

    graph = dependencies.graph_payload(dev=False)
    nodes = {n["name"]: n for n in graph["nodes"]}

    assert graph["mode"] == "production"
    assert nodes["menu"]["state"] == "blocked"
    assert "auth" in nodes["menu"]["reason"]
    assert nodes["auth"]["state"] == "missing"
    assert nodes["files"]["state"] == "missing"
    assert nodes["outbound"]["state"] == "ok"
    assert nodes["outbound"]["missing_optional"] == ["menu"]
    assert nodes["billing"]["state"] == "ok"
    assert set(graph["load_order"]) == {"outbound", "billing"}
    assert {"from": "menu", "to": "auth", "kind": "required", "satisfied": False} in graph["edges"]
    assert {"from": "outbound", "to": "menu", "kind": "optional", "satisfied": True} in graph[
        "edges"
    ]


def test_graph_payload_marks_disabled_modules(installed, monkeypatch):
    write_archive(installed, meta("auth"))
    write_archive(installed, meta("menu", ["auth"]))
    real = dependencies.available_module_metas

    def without_auth(db=None, dev=None):
        return {k: v for k, v in real(None, dev=dev).items() if k != "auth"}

    monkeypatch.setattr(dependencies, "available_module_metas", without_auth)
    nodes = {n["name"]: n for n in dependencies.graph_payload(dev=False)["nodes"]}
    assert nodes["auth"]["state"] == "disabled"
    assert nodes["menu"]["state"] == "blocked"


def test_graph_endpoint(client, installed):
    write_archive(installed, meta("auth"))
    write_archive(installed, meta("menu", ["auth"]))
    data = client.get("/api/modules/graph").json()
    assert data["load_order"] == ["auth", "menu"]
    assert {n["name"]: n["state"] for n in data["nodes"]} == {"auth": "ok", "menu": "ok"}
