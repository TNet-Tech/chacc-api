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
    assert data["auth"] == {"required": False, "method": "none", "login_path": None}
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
    assert _auth_info(request)["login_path"] == "/api/authentication/login"


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


# ---------- Web console key (no authentication module) ----------

CONSOLE_KEY = "Zq8-console-key-for-the-tests-0123456789"


@pytest.fixture
def with_key(monkeypatch):
    from src import admin_access

    monkeypatch.setattr(admin_access, "CONSOLE_KEY", CONSOLE_KEY)


def test_key_protects_core_routes_without_auth_module(client, with_key, monkeypatch):
    monkeypatch.delenv(lifecycle.SUPERVISED_ENV, raising=False)
    for method, path in [
        ("get", "/api/modules/"),
        ("get", "/api/system/access"),
        ("post", "/api/system/restart"),
    ]:
        missing = getattr(client, method)(path)
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == "ChaCC-Key"
        wrong = getattr(client, method)(path, headers={"X-ChaCC-Key": "wrong"})
        assert wrong.status_code == 401
        assert wrong.json()["detail"] == "Wrong web console key."
    assert client.get("/api/modules/", headers={"X-ChaCC-Key": CONSOLE_KEY}).status_code == 200
    # Past the key check, refused only because the server isn't supervised.
    restart = client.post("/api/system/restart", headers={"X-ChaCC-Key": CONSOLE_KEY})
    assert restart.status_code == 409


def test_key_with_any_characters_works_encoded_or_raw(client, monkeypatch):
    from urllib.parse import quote

    from src import admin_access

    key = "pässwörd 你好 %41&+"
    monkeypatch.setattr(admin_access, "CONSOLE_KEY", key)
    encoded = client.get("/api/system/access", headers={"X-ChaCC-Key": quote(key, safe="")})
    assert encoded.status_code == 200
    raw = client.get("/api/system/access", headers={"X-ChaCC-Key": key.encode()})
    assert raw.status_code == 200
    assert (
        client.get("/api/system/access", headers={"X-ChaCC-Key": "pässwörd".encode()}).status_code
        == 401
    )


def test_discovery_says_a_key_is_needed_but_not_the_key(client, with_key):
    data = client.get("/.well-known/chacc")
    assert data.json()["auth"] == {"required": True, "method": "key", "login_path": None}
    assert CONSOLE_KEY not in data.text


def test_login_overrides_the_key(client, with_auth, with_key):
    """With the authentication module loaded, the key gets nobody in."""
    assert client.get("/api/modules/", headers={"X-ChaCC-Key": CONSOLE_KEY}).status_code == 401
    ok = client.get("/api/modules/", headers={"Authorization": "Bearer good-token"})
    assert ok.status_code == 200
    assert client.get("/.well-known/chacc").json()["auth"]["method"] == "login"


def test_unprotected_server_stays_open_with_a_warning(client):
    response = client.get("/api/modules/")
    assert response.status_code == 200
    assert "isn't protected" in response.headers["x-chacc-warning"]
    assert client.get("/api/system/access").json() == {"access": True}


def test_console_has_the_access_gate(client):
    page = client.get("/console").text
    for element in ('id="gate"', 'id="key-dialog"', 'id="login-dialog"'):
        assert element in page


# ---------- Admin privilege ----------


class PrivilegeContext(FakeContext):
    """An authentication module with RBAC: 'admin-token' holds the privilege, 'good-token' doesn't."""

    def __init__(self):
        super().__init__(user={"username": "someone"})
        self.checked = []
        self.registered = []
        self.fail_registration = False
        context = self

        class PrivilegeService:
            async def ensure(self, privileges):
                if context.fail_registration:
                    raise RuntimeError("database is locked")
                context.registered.append(privileges)
                return [{"name": name} for name, _, _ in privileges]

        self.privilege_service = PrivilegeService()

    def has_service(self, name):
        return name in {"get_current_user", "has_privileges", "privilege_service"}

    def get_service(self, name):
        if name == "privilege_service":
            return self.privilege_service
        if name != "has_privileges":
            return super().get_service(name)

        async def has_privileges(credentials, privilege_names, *, require_all=False):
            from fastapi import HTTPException

            self.checked.append(list(privilege_names))
            if credentials.credentials not in {"good-token", "admin-token"}:
                raise HTTPException(status_code=401, detail="Not authenticated")
            if credentials.credentials != "admin-token":
                raise HTTPException(
                    status_code=403,
                    detail="Missing required privilege(s): " + ", ".join(privilege_names),
                )
            return {"username": "admin"}

        return has_privileges


@pytest.fixture
def with_rbac(monkeypatch):
    from src import admin_access

    monkeypatch.setattr(admin_access, "_registered", set())
    previous = app.state.backbone_context
    app.state.backbone_context = PrivilegeContext()
    yield app.state.backbone_context
    app.state.backbone_context = previous


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_only_admins_use_the_console_routes(client, with_rbac, monkeypatch):
    monkeypatch.delenv(lifecycle.SUPERVISED_ENV, raising=False)
    assert client.get("/api/modules/").status_code == 401
    assert client.get("/api/modules/", headers=bearer("good-token")).status_code == 403
    assert client.get("/api/system/services", headers=bearer("good-token")).status_code == 403
    assert client.post("/api/system/restart", headers=bearer("good-token")).status_code == 403
    assert client.get("/api/modules/", headers=bearer("admin-token")).status_code == 200
    assert with_rbac.checked[-1] == ["MANAGE_WEB_CONSOLE", "ALL"]


def test_opening_the_console_registers_the_privilege_once(client, with_rbac):
    assert client.get("/console").status_code == 200
    assert client.get("/console").status_code == 200
    assert len(with_rbac.registered) == 1
    name, _description, severity = with_rbac.registered[0][0]
    assert (name, severity) == ("MANAGE_WEB_CONSOLE", "CRITICAL")


def test_admin_check_registers_the_privilege_without_the_console(client, with_rbac):
    """chacc deploy never opens the console page."""
    client.get("/api/modules/", headers=bearer("admin-token"))
    assert with_rbac.registered and with_rbac.registered[0][0][0] == "MANAGE_WEB_CONSOLE"


def test_failed_registration_is_retried_and_never_breaks_the_page(client, with_rbac):
    with_rbac.fail_registration = True
    assert client.get("/console").status_code == 200
    assert client.get("/api/modules/", headers=bearer("admin-token")).status_code == 200
    with_rbac.fail_registration = False
    client.get("/console")
    assert len(with_rbac.registered) == 1


def test_refusal_does_not_reveal_the_privilege(client, with_rbac):
    response = client.get("/api/modules/", headers=bearer("good-token"))
    assert response.status_code == 403
    assert "MANAGE_WEB_CONSOLE" not in response.text
    assert response.json()["detail"] == "You don't have access to manage this server."


def test_configured_privilege_is_checked_and_registered(client, with_rbac, monkeypatch):
    from src import admin_access

    monkeypatch.setattr(admin_access, "ADMIN_PRIVILEGE", "CONSOLE_ACCESS")
    client.get("/api/modules/", headers=bearer("admin-token"))
    assert with_rbac.checked[-1] == ["CONSOLE_ACCESS", "ALL"]
    assert with_rbac.registered[-1][0][0] == "CONSOLE_ACCESS"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "MANAGE_WEB_CONSOLE"),
        ("  ", "MANAGE_WEB_CONSOLE"),
        ("CONSOLE_ACCESS", "CONSOLE_ACCESS"),
        (" OPS_2 ", "OPS_2"),
        ("console access", "MANAGE_WEB_CONSOLE"),
        ("lower", "MANAGE_WEB_CONSOLE"),
        ("ALL", "MANAGE_WEB_CONSOLE"),
    ],
)
def test_privilege_setting_never_weakens_access(value, expected):
    from src.admin_access import resolve_admin_privilege

    assert resolve_admin_privilege(value) == expected


def test_no_registration_without_auth_module(client):
    from src import admin_access

    assert client.get("/console").status_code == 200
    assert not admin_access._registered


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
