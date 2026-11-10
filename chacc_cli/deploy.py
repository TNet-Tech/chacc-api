"""
``chacc deploy`` — upload a .chacc package to a running ChaCC API server.

Flow:
1. Probe ``GET /api/modules/`` (cheap, same auth as the upload) so we learn
   whether the server requires authentication *before* sending a large file.
2. If the probe returns 401, authenticate against the
   ``chacc_authentication`` module (``POST <auth path>/login``) using
   ``CHACC_DEPLOY_USERNAME``/``CHACC_DEPLOY_PASSWORD`` or, on a TTY, by
   prompting for a username and password.
3. Upload the package and wait for the server's response (dependency
   resolution can take a while), showing elapsed time on a TTY.
4. If the token expires mid-flight (401 on upload), refresh it once and retry.
5. Revoke the refresh token we created so no session is left behind.

Credentials and tokens are only held in memory; nothing is persisted.
"""

from __future__ import annotations

import getpass
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from decouple import config

from src.logger import configure_logging

cli_logger = configure_logging(log_level="INFO")

MODULES_ENDPOINT = "/api/modules/"
DEFAULT_AUTH_PATH = "/authentication"
DEFAULT_TIMEOUT = 600
CONNECT_TIMEOUT = 10
PROBE_TIMEOUT = 30
MAX_LOGIN_ATTEMPTS = 3


class DeployError(Exception):
    """Raised for any deploy failure; the message is user-facing."""


@dataclass
class DeploySettings:
    url: str
    api_key: str | None = None
    timeout: int = DEFAULT_TIMEOUT
    auth_path: str = DEFAULT_AUTH_PATH
    username: str | None = None
    password: str | None = None

    @classmethod
    def from_env(cls) -> DeploySettings:
        try:
            url = config("CHACC_DEPLOY_URL", default=None)
            timeout = config("CHACC_DEPLOY_TIMEOUT", default=DEFAULT_TIMEOUT, cast=int)
        except (ValueError, TypeError) as exc:
            raise DeployError(f"Invalid deployment configuration: {exc}") from exc
        if not url:
            raise DeployError(
                "CHACC_DEPLOY_URL is not set. Add it to your .env file "
                "(e.g. CHACC_DEPLOY_URL=http://your-api.com)."
            )
        auth_path = config("CHACC_DEPLOY_AUTH_PATH", default=DEFAULT_AUTH_PATH) or ""
        return cls(
            url=url.rstrip("/"),
            api_key=config("CHACC_DEPLOY_API_KEY", default=None) or None,
            timeout=timeout,
            auth_path="/" + auth_path.strip("/"),
            username=config("CHACC_DEPLOY_USERNAME", default=None) or None,
            password=config("CHACC_DEPLOY_PASSWORD", default=None) or None,
        )


@dataclass
class _AuthState:
    access_token: str | None = None
    refresh_token: str | None = None
    logged_in: bool = False  # True only when *we* created the session
    prompted: bool = False


class _Waiter:
    """Shows ``Waiting for server response… 12s`` on a TTY while a request runs."""

    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tty = sys.stdout.isatty()

    def __enter__(self):
        if self._tty:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            print(f"{self.message}…", flush=True)
        return self

    def _run(self):
        start = time.monotonic()
        frames = "|/-\\"
        i = 0
        while not self._stop.wait(0.2):
            elapsed = int(time.monotonic() - start)
            sys.stdout.write(f"\r{frames[i % 4]} {self.message}… {elapsed}s ")
            sys.stdout.flush()
            i += 1

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
            sys.stdout.write("\r" + " " * (len(self.message) + 20) + "\r")
            sys.stdout.flush()
        return False


class Deployer:
    def __init__(
        self,
        settings: DeploySettings,
        session: requests.Session | None = None,
        prompt: Callable[[str], str] = input,
        prompt_password: Callable[[str], str] = getpass.getpass,
        interactive: bool | None = None,
    ):
        self.settings = settings
        self.session = session or requests.Session()
        self.prompt = prompt
        self.prompt_password = prompt_password
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.auth = _AuthState(access_token=settings.api_key)

    
    def _headers(self) -> dict[str, str]:
        if self.auth.access_token:
            return {"Authorization": f"Bearer {self.auth.access_token}"}
        return {}

    def _request(self, method: str, path: str, timeout, **kwargs) -> requests.Response:
        url = f"{self.settings.url}{path}"
        try:
            return self.session.request(
                method, url, headers=self._headers(), timeout=timeout, **kwargs
            )
        except requests.exceptions.ConnectionError as exc:
            raise DeployError(
                f"Could not connect to {self.settings.url}. "
                "Check that the ChaCC API server is running and reachable."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise DeployError(
                f"Timed out waiting for {url}. Increase CHACC_DEPLOY_TIMEOUT if the "
                "server needs longer (e.g. while resolving dependencies)."
            ) from exc

    @staticmethod
    def _detail(response: requests.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict) and data.get("detail"):
                return str(data["detail"])
        except ValueError:
            pass
        return response.text.strip()[:500] or response.reason or "no details"

    
    def _credentials(self, attempt: int) -> tuple[str, str]:
        s = self.settings
        if s.username and s.password and attempt == 1:
            return s.username, s.password
        if not self.interactive:
            raise DeployError(
                "The server requires authentication. Set CHACC_DEPLOY_USERNAME and "
                "CHACC_DEPLOY_PASSWORD (or CHACC_DEPLOY_API_KEY) to deploy non-interactively."
            )
        if not self.auth.prompted:
            print(f"Authentication required for {s.url}.", flush=True)
            self.auth.prompted = True
        default_user = s.username or ""
        suffix = f" [{default_user}]" if default_user else ""
        username = self.prompt(f"Username{suffix}: ").strip() or default_user
        password = self.prompt_password("Password: ")
        if not username or not password:
            raise DeployError("Username and password are required.")
        return username, password

    def login(self) -> None:
        if self.settings.api_key and self.auth.access_token == self.settings.api_key:
            cli_logger.warning("CHACC_DEPLOY_API_KEY was rejected by the server (401).")
        self.auth.access_token = None
        login_path = f"{self.settings.auth_path}/login"

        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            username, password = self._credentials(attempt)
            response = self._request(
                "POST",
                login_path,
                timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
                json={"username": username, "password": password},
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if not token:
                    raise DeployError("Login succeeded but no access_token was returned.")
                self.auth.access_token = token
                self.auth.refresh_token = data.get("refresh_token")
                self.auth.logged_in = True
                cli_logger.info(f"Authenticated as '{username}'.")
                return
            if response.status_code == 404:
                raise DeployError(
                    f"Login endpoint not found at {self.settings.url}{login_path}. "
                    "Set CHACC_DEPLOY_AUTH_PATH to the authentication module's base path."
                )
            if response.status_code in (400, 401, 403, 422):
                cli_logger.error(f"Login failed: {self._detail(response)}")
                if not self.interactive:
                    break
                continue
            raise DeployError(
                f"Login failed with status {response.status_code}: {self._detail(response)}"
            )
        raise DeployError("Authentication failed.")

    def refresh(self) -> bool:
        """Try to refresh the access token. Returns True on success."""
        if not self.auth.refresh_token:
            return False
        self.auth.access_token = None
        response = self._request(
            "POST",
            f"{self.settings.auth_path}/refresh",
            timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
            json={"refresh_token": self.auth.refresh_token},
        )
        if response.status_code != 200:
            return False
        data = response.json()
        self.auth.access_token = data.get("access_token")
        self.auth.refresh_token = data.get("refresh_token") or self.auth.refresh_token
        return bool(self.auth.access_token)

    def revoke(self) -> None:
        """Revoke the session we created. Failures are ignored."""
        if not (self.auth.logged_in and self.auth.refresh_token):
            return
        try:
            self.session.post(
                f"{self.settings.url}{self.settings.auth_path}/revoke",
                json={"refresh_token": self.auth.refresh_token},
                timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
            )
        except requests.exceptions.RequestException:
            pass

    
    def ensure_authenticated(self) -> None:
        """Probe the modules endpoint and log in only if the server answers 401."""
        response = self._request("GET", MODULES_ENDPOINT, timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT))
        if response.status_code == 401:
            self.login()

    def upload(self, chacc_file_path: str) -> requests.Response:
        name = os.path.basename(chacc_file_path)
        with open(chacc_file_path, "rb") as f, _Waiter("Uploading and waiting for server response"):
            return self._request(
                "POST",
                MODULES_ENDPOINT,
                timeout=(CONNECT_TIMEOUT, self.settings.timeout),
                files={"file": (name, f, "application/zip")},
            )

    def deploy(self, chacc_file_path: str) -> str:
        """Deploy the package. Returns the server's success message."""
        try:
            self.ensure_authenticated()
            response = self.upload(chacc_file_path)
            if response.status_code == 401:
                if not self.refresh():
                    self.login()
                response = self.upload(chacc_file_path)

            if response.status_code == 200:
                try:
                    return response.json().get("message", "Module deployed.")
                except ValueError:
                    return "Module deployed."
            if response.status_code == 401:
                raise DeployError("The server rejected the credentials (401).")
            if response.status_code == 403:
                raise DeployError(f"Permission denied (403): {self._detail(response)}")
            if response.status_code == 413:
                raise DeployError(f"Package too large (413): {self._detail(response)}")
            raise DeployError(
                f"Deployment failed with status {response.status_code}: {self._detail(response)}"
            )
        finally:
            self.revoke()


def deploy_module(chacc_file_path: str) -> bool:
    """CLI entry point. Returns True on success."""
    if not os.path.isfile(chacc_file_path):
        cli_logger.error(f"ChaCC file '{chacc_file_path}' not found.")
        return False

    try:
        settings = DeploySettings.from_env()
        size_mb = os.path.getsize(chacc_file_path) / (1024 * 1024)
        cli_logger.info(f"Deploying '{chacc_file_path}' ({size_mb:.2f} MB) to {settings.url}...")
        message = Deployer(settings).deploy(chacc_file_path)
    except DeployError as exc:
        cli_logger.error(f"FAILED: {exc}")
        return False
    except KeyboardInterrupt:
        print()
        cli_logger.error("Deployment cancelled.")
        return False

    cli_logger.info("=" * 60)
    cli_logger.info("SUCCESS: Module deployed successfully!")
    cli_logger.info(f"SUCCESS: {message}")
    cli_logger.info("SUCCESS: Restart the remote ChaCC API server to activate the module.")
    cli_logger.info("=" * 60)
    return True
