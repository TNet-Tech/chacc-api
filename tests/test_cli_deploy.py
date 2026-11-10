"""Tests for ``chacc deploy`` authentication and upload flow."""

import pytest

from chacc_cli.deploy import Deployer, DeployError, DeploySettings


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = str(self._data)
        self.reason = ""

    def json(self):
        return self._data


class FakeSession:
    """Routes (method, path) to a queue of responses and records calls."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, **kwargs):
        path = url.replace("http://api", "")
        self.calls.append((method, path, dict(headers or {}), kwargs))
        queue = self.routes[(method, path)]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


@pytest.fixture
def chacc_file(tmp_path):
    path = tmp_path / "demo.chacc"
    path.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    return str(path)


def make(routes, *, interactive=True, answers=("alice",), typed_password="secret", **settings):
    session = FakeSession(routes)
    prompts = list(answers)
    deployer = Deployer(
        DeploySettings(url="http://api", **settings),
        session=session,
        prompt=lambda _msg: prompts.pop(0),
        prompt_password=lambda _msg: typed_password,
        interactive=interactive,
    )
    return deployer, session


OK_UPLOAD = FakeResponse(200, {"message": "Module 'demo' installed/updated successfully."})
LOGIN_OK = FakeResponse(200, {"access_token": "tok", "refresh_token": "ref"})


def test_no_auth_server_does_not_prompt(chacc_file):
    deployer, session = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [OK_UPLOAD]},
        answers=(),
    )
    assert "installed" in deployer.deploy(chacc_file)
    assert [c[:2] for c in session.calls] == [("GET", "/api/modules/"), ("POST", "/api/modules/")]
    assert "Authorization" not in session.calls[1][2]


def test_prompts_on_401_then_uploads_with_token_and_revokes(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/authentication/revoke"): [FakeResponse(200)],
        }
    )
    deployer.deploy(chacc_file)
    login = session.calls[1]
    assert login[3]["json"] == {"username": "alice", "password": "secret"}
    upload = session.calls[2]
    assert upload[2]["Authorization"] == "Bearer tok"
    assert session.calls[-1][1] == "/authentication/revoke"
    assert session.calls[-1][3]["json"] == {"refresh_token": "ref"}


def test_wrong_password_retries_then_gives_up(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/authentication/login"): [FakeResponse(400, {"detail": "Incorrect"})],
        },
        answers=("a", "b", "c"),
    )
    with pytest.raises(DeployError, match="Authentication failed"):
        deployer.deploy(chacc_file)
    assert sum(1 for c in session.calls if c[1] == "/authentication/login") == 3


def test_non_interactive_without_credentials_fails_clearly(chacc_file):
    deployer, _ = make({("GET", "/api/modules/"): [FakeResponse(401)]}, interactive=False)
    with pytest.raises(DeployError, match="CHACC_DEPLOY_USERNAME"):
        deployer.deploy(chacc_file)


def test_non_interactive_uses_env_credentials(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [OK_UPLOAD],
            ("POST", "/authentication/revoke"): [FakeResponse(200)],
        },
        interactive=False,
        username="ci",
        password="pw",
    )
    deployer.deploy(chacc_file)
    assert session.calls[1][3]["json"] == {"username": "ci", "password": "pw"}


def test_expired_token_on_upload_is_refreshed_once(chacc_file):
    deployer, session = make(
        {
            ("GET", "/api/modules/"): [FakeResponse(401)],
            ("POST", "/authentication/login"): [LOGIN_OK],
            ("POST", "/api/modules/"): [FakeResponse(401), OK_UPLOAD],
            ("POST", "/authentication/refresh"): [
                FakeResponse(200, {"access_token": "tok2", "refresh_token": "ref2"})
            ],
            ("POST", "/authentication/revoke"): [FakeResponse(200)],
        }
    )
    deployer.deploy(chacc_file)
    uploads = [c for c in session.calls if c[:2] == ("POST", "/api/modules/")]
    assert uploads[-1][2]["Authorization"] == "Bearer tok2"
    assert session.calls[-1][3]["json"] == {"refresh_token": "ref2"}


def test_api_key_is_sent_and_not_revoked(chacc_file):
    deployer, session = make(
        {("GET", "/api/modules/"): [FakeResponse(200)], ("POST", "/api/modules/"): [OK_UPLOAD]},
        api_key="KEY",
    )
    deployer.deploy(chacc_file)
    assert all(c[2].get("Authorization") == "Bearer KEY" for c in session.calls)
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
