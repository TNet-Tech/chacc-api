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

    def has_service(self, name):
        return name == "get_current_user"

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
    assert '<script type="module" src="/static/js/console/main.js?v=' in response.text
    assert 'content="/api"' in response.text
    for asset in ("/static/js/console/main.js", "/static/css/console.css"):
        assert client.get(asset).status_code == 200


def test_console_script_modules_import_existing_files(client):
    """Every relative import in the console's scripts points to a served file."""
    import re

    from chacc_api.server.main import static_dir

    folder = static_dir / "js" / "console"
    for script in folder.glob("*.js"):
        for target in re.findall(
            r"^import .* from '(\./[\w-]+\.js)';$", script.read_text(), re.MULTILINE
        ):
            assert (folder / target).is_file(), f"{script.name} imports missing {target}"
            assert client.get(f"/static/js/console/{target[2:]}").status_code == 200


def test_static_files_are_revalidated_unless_fingerprinted(client):
    """Script modules are imported without ?v=, so browsers must check them each time."""
    plain = client.get("/static/js/console/api.js")
    assert plain.headers["cache-control"] == "no-cache"
    etag = plain.headers["etag"]
    assert (
        client.get("/static/js/console/api.js", headers={"If-None-Match": etag}).status_code == 304
    )
    pinned = client.get("/static/js/console/main.js?v=abc123")
    assert pinned.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_readme_viewer_and_bundled_diagram_library_are_served(client):
    script = client.get("/static/js/console/markdown.js").text
    url = script.split("const MERMAID_URL = '", 1)[1].split("'", 1)[0]
    library = client.get(url)
    assert library.status_code == 200
    assert 'globalThis["mermaid"]' in library.text


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


def test_graph_requires_login_in_production_when_auth_module_loaded(client, with_auth, monkeypatch):
    from src import modules

    monkeypatch.setattr(modules, "DEVELOPMENT_MODE", False)
    assert client.get("/api/modules/graph").status_code == 401
    ok = client.get("/api/modules/graph", headers={"Authorization": "Bearer good-token"})
    assert ok.status_code == 200


def test_graph_is_open_in_development_mode(client, with_auth, monkeypatch):
    from src import modules

    monkeypatch.setattr(modules, "DEVELOPMENT_MODE", True)
    assert client.get("/api/modules/graph").status_code == 200
    # Managing modules still needs a login.
    assert client.get("/api/modules/").status_code == 401


def test_graph_is_open_without_auth_module(client, monkeypatch):
    from src import modules

    monkeypatch.setattr(modules, "DEVELOPMENT_MODE", False)
    assert client.get("/api/modules/graph").status_code == 200


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


def test_static_assets_are_versioned_by_content():
    """A changed script or stylesheet gets a new URL, so browsers don't reuse an old copy."""
    import hashlib
    import re

    from fastapi.testclient import TestClient

    from chacc_api.server.main import app, static_dir

    client = TestClient(app)
    for page in ("/console", "/"):
        html = client.get(page).text
        links = re.findall(r'/static/([^"?]+\.(?:css|js))\?v=([0-9a-f]{12})"', html)
        assert links, f"no versioned assets on {page}"
        for path, version in links:
            expected = hashlib.sha256((static_dir / path).read_bytes()).hexdigest()[:12]
            assert version == expected
            assert client.get(f"/static/{path}?v={version}").status_code == 200


def test_production_page_cache_notices_changed_files(monkeypatch, tmp_path):
    """A cached page is rebuilt when its template or a static file changes."""
    import os

    from chacc_api.server import main

    template = tmp_path / "page.html"
    template.write_text('<script src="/static/js/console/main.js"></script>v1', encoding="utf-8")
    monkeypatch.setattr(main, "TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(main, "DEVELOPMENT_MODE", False)
    main._cached_template.cache_clear()

    assert main._render_template("page.html").endswith("v1")
    assert main._render_template("page.html").endswith("v1")  # served from the cache

    template.write_text('<script src="/static/js/console/main.js"></script>v2', encoding="utf-8")
    stamp = template.stat().st_mtime_ns + 1_000_000_000
    os.utime(template, ns=(stamp, stamp))
    assert main._render_template("page.html").endswith("v2")
    main._cached_template.cache_clear()
