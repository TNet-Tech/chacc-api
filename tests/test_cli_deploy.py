"""Tests for ``chacc deploy`` prefix discovery, authentication and upload flow."""

import pytest

from chacc_cli.deploy import Deployer, DeployError, DeploySettings

BASE = "http://server"
DISCOVERY = ("GET", "/.well-known/chacc")


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = str(self._data)
        self.reason = ""

    def json(self):
        return self._data


class FakeSession:
    """
    Routes (method, path) to a queue of responses and records calls.

    The discovery endpoint answers 404 unless a route is given, mimicking an
    older server; the client must then fall back to '/api'.
    """

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.routes.setdefault(DISCOVERY, [FakeResponse(404)])
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, **kwargs):
        path = url.removeprefix(BASE)
        self.calls.append((method, path, dict(headers or {}), kwargs))
        queue = self.routes[(method, path)]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def calls_to(self, method, path):
        return [c for c in self.calls if c[:2] == (method, path)]


@pytest.fixture
def chacc_file(tmp_path):
    path = tmp_path / "demo.chacc"
    path.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    return str(path)


def make(routes, *, interactive=True, answers=("alice",), typed_password="secret", **settings):
    session = FakeSession(routes)
    prompts = list(answers)
    deployer = Deployer(
        DeploySettings(url=BASE, **settings),
        session=session,
        prompt=lambda _msg: prompts.pop(0),
        prompt_password=lambda _msg: typed_password,
        interactive=interactive,
    )
    return deployer, session


OK_UPLOAD = FakeResponse(200, {"message": "Module 'demo' installed/updated successfully."})
LOGIN_OK = FakeResponse(200, {"access_token": "tok", "refresh_token": "ref"})


# ---------- Prefix handling ----------


def test_falls_back_to_api_prefix_when_discovery_missing(chacc_file):
    deployer, session = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [OK_UPLOAD]}
    )
    deployer.deploy(chacc_file)
    assert session.calls_to("POST", "/api/modules/")


def test_uses_discovered_custom_prefix_for_modules_and_auth(chacc_file):
    deployer, session = make(
        {
            DISCOVERY: [FakeResponse(200, {"api_prefix": "/backbone/v1/"})],
            ("GET", "/backbone/v1/modules/"): [FakeResponse(401)],
            ("POST", "/backbone/v1/authentication/login"): [LOGIN_OK],
            ("POST", "/backbone/v1/modules/"): [OK_UPLOAD],
            ("POST", "/backbone/v1/authentication/revoke"): [FakeResponse(200)],
        }
    )
    deployer.deploy(chacc_file)
    assert session.calls_to("POST", "/backbone/v1/modules/")
    assert len(session.calls_to(*DISCOVERY)) == 1


def test_discovered_empty_prefix(chacc_file):
    deployer, session = make(
        {
            DISCOVERY: [FakeResponse(200, {"api_prefix": ""})],
            ("GET", "/modules/"): [FakeResponse(200)],
            ("POST", "/modules/"): [OK_UPLOAD],
        }
    )
    deployer.deploy(chacc_file)
    assert session.calls_to("POST", "/modules/")


def test_env_prefix_overrides_discovery(chacc_file):
    deployer, session = make(
        {
            ("GET", "/custom/modules/"): [FakeResponse(200)],
            ("POST", "/custom/modules/"): [OK_UPLOAD],
        },
        api_prefix="/custom",
    )
    deployer.deploy(chacc_file)
    assert not session.calls_to(*DISCOVERY)


def test_settings_normalize_env_prefix(monkeypatch):
    monkeypatch.setenv("CHACC_DEPLOY_URL", "http://x/")
    monkeypatch.setenv("CHACC_DEPLOY_API_PREFIX", "gateway/api/")
    settings = DeploySettings.from_env()
    assert settings.url == "http://x"
    assert settings.api_prefix == "/gateway/api"

    monkeypatch.setenv("CHACC_DEPLOY_API_PREFIX", "")
    assert DeploySettings.from_env().api_prefix == ""

    monkeypatch.delenv("CHACC_DEPLOY_API_PREFIX")
    assert DeploySettings.from_env().api_prefix is None


# ---------- Authentication ----------


def test_no_auth_server_does_not_prompt(chacc_file):
    deployer, session = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [OK_UPLOAD]},
        answers=(),
    )
    assert "installed" in deployer.deploy(chacc_file)
    assert "Authorization" not in session.calls_to("POST", "/api/modules/")[0][2]


def test_prompts_on_401_then_uploads_with_token_and_revokes(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/api/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/api/authentication/revoke"): [FakeResponse(200)],
        }
    )
    deployer.deploy(chacc_file)
    login = session.calls_to("POST", "/api/authentication/login")[0]
    assert login[3]["json"] == {"username": "alice", "password": "secret"}
    upload = session.calls_to("POST", "/api/modules/")[0]
    assert upload[2]["Authorization"] == "Bearer tok"
    assert session.calls[-1][1] == "/api/authentication/revoke"
    assert session.calls[-1][3]["json"] == {"refresh_token": "ref"}


def test_wrong_password_retries_then_gives_up(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/api/authentication/login"): [FakeResponse(400, {"detail": "Incorrect"})],
        },
        answers=("a", "b", "c"),
    )
    with pytest.raises(DeployError, match="Authentication failed"):
        deployer.deploy(chacc_file)
    assert len(session.calls_to("POST", "/api/authentication/login")) == 3


def test_non_interactive_without_credentials_fails_clearly(chacc_file):
    deployer, _ = make({("GET", "/api/modules/"): [FakeResponse(401)]}, interactive=False)
    with pytest.raises(DeployError, match="CHACC_DEPLOY_USERNAME"):
        deployer.deploy(chacc_file)


def test_non_interactive_uses_env_credentials(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/api/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/api/authentication/revoke"): [FakeResponse(200)],
        },
        interactive=False,
        username="ci",
        password="pw",
    )
    deployer.deploy(chacc_file)
    login = session.calls_to("POST", "/api/authentication/login")[0]
    assert login[3]["json"] == {"username": "ci", "password": "pw"}


def test_expired_token_on_upload_is_refreshed_once(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/api/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [FakeResponse(401), OK_UPLOAD],
            ("POST", "/api/authentication/refresh"): [
                FakeResponse(200, {"access_token": "tok2", "refresh_token": "ref2"})
            ],
            ("POST", "/api/authentication/revoke"): [FakeResponse(200)],
        }
    )
    deployer.deploy(chacc_file)
    uploads = session.calls_to("POST", "/api/modules/")
    assert uploads[-1][2]["Authorization"] == "Bearer tok2"
    assert session.calls[-1][3]["json"] == {"refresh_token": "ref2"}


def test_api_key_is_sent_and_not_revoked(chacc_file):
    deployer, session = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [OK_UPLOAD]},
        api_key="KEY",
    )
    deployer.deploy(chacc_file)
    api_calls = [c for c in session.calls if c[1].startswith("/api/")]
    assert all(c[2].get("Authorization") == "Bearer KEY" for c in api_calls)
    assert not any("revoke" in c[1] for c in session.calls)


def test_server_error_surfaces_detail(chacc_file):
    deployer, _ = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [FakeResponse(413, {"detail": "too big"})],
        }
    )
    with pytest.raises(DeployError, match="too big"):
        deployer.deploy(chacc_file)


def test_proxy_413_names_the_proxy_instead_of_printing_its_page(chacc_file):
    class ProxyPage(FakeResponse):
        def __init__(self):
            super().__init__(413)
            self.text = "<html><head><title>413 Request Entity Too Large</title></head></html>"
            self.headers = {"Server": "nginx/1.31.8"}

        def json(self):
            raise ValueError("not JSON")

    deployer, _ = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [ProxyPage()]}
    )
    with pytest.raises(DeployError) as error:
        deployer.deploy(chacc_file)
    assert "rejected by nginx in front of ChaCC" in str(error.value)
    assert "client_max_body_size" in str(error.value)
    assert "<html>" not in str(error.value)


# ---------- Restart ----------


@pytest.fixture
def no_sleep(monkeypatch):
    import chacc_cli.deploy as deploy_mod

    monkeypatch.setattr(deploy_mod.time, "sleep", lambda _s: None)


def test_deploy_with_restart_waits_for_new_boot_id(chacc_file, no_sleep):
    deployer, session = make(
        {
            DISCOVERY: [
                FakeResponse(200, {"api_prefix": "/api", "boot_id": "old"}),  # prefix
                FakeResponse(200, {"api_prefix": "/api", "boot_id": "old"}),  # before restart
                FakeResponse(200, {"api_prefix": "/api", "boot_id": "old"}),  # still shutting down
                FakeResponse(200, {"api_prefix": "/api", "boot_id": "new"}),
            ],
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/api/system/restart"): [FakeResponse(202, {"boot_id": "old"})],
        }
    )
    message = deployer.deploy(chacc_file, restart=True)
    assert "Server restarted" in message
    assert session.calls_to("POST", "/api/system/restart")


def test_restart_unsupported_is_reported_not_fatal(chacc_file, no_sleep):
    deployer, _ = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/api/system/restart"): [
                FakeResponse(409, {"detail": "not running under the ChaCC supervisor"})
            ],
        }
    )
    message = deployer.deploy(chacc_file, restart=True)
    assert "installed" in message
    assert "supervisor" in message


def test_restart_timeout_raises(chacc_file, no_sleep, monkeypatch):
    deployer, _ = make(
        {
            DISCOVERY: [FakeResponse(200, {"api_prefix": "/api", "boot_id": "old"})],
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/api/system/restart"): [FakeResponse(202, {"boot_id": "old"})],
        },
        restart_timeout=0,
    )
    with pytest.raises(DeployError, match="did not come back"):
        deployer.deploy(chacc_file, restart=True)


# ---------- Module dependencies ----------


def test_missing_required_modules_are_listed(chacc_file):
    deployer, _ = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [
                FakeResponse(
                    409,
                    {
                        "detail": "requires modules",
                        "missing_dependencies": {"required": ["auth"], "optional": ["files"]},
                    },
                )
            ],
        }
    )
    with pytest.raises(DeployError) as exc:
        deployer.deploy(chacc_file)
    text = str(exc.value)
    assert "  - auth" in text
    assert "Optional module(s) also missing: files" in text
    assert "Deploy the required modules first" in text


def test_server_warnings_are_kept(chacc_file):
    deployer, _ = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(200)],
            ("POST", "/api/modules/"): [
                FakeResponse(200, {"message": "ok", "warnings": ["Optional module(s) x"]})
            ],
        }
    )
    deployer.deploy(chacc_file)
    assert deployer.warnings == ["Optional module(s) x"]
