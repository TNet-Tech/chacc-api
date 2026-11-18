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

MODULES_PATH = "/modules/"
DISCOVERY_PATH = "/.well-known/chacc"
DEFAULT_API_PREFIX = "/api"
RESTART_PATH = "/system/restart"
DEFAULT_RESTART_TIMEOUT = 180
RESTART_POLL_INTERVAL = 1.0
DEFAULT_AUTH_PATH = "/authentication"
DEFAULT_TIMEOUT = 600
CONNECT_TIMEOUT = 10
PROBE_TIMEOUT = 30
MAX_LOGIN_ATTEMPTS = 3


def normalize_prefix(value: str | None) -> str:
    """Return '' or '/segment[/segment]' (leading slash, no trailing slash)."""
    value = (value or "").strip().strip("/")
    return f"/{value}" if value else ""


def _safe_json(response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class DeployError(Exception):
    """Raised for any deploy failure; the message is user-facing."""


@dataclass
class DeploySettings:
    url: str
    api_key: str | None = None
    timeout: int = DEFAULT_TIMEOUT
    auth_path: str = DEFAULT_AUTH_PATH
    restart_timeout: int = DEFAULT_RESTART_TIMEOUT
    # None = discover from the server (GET /.well-known/chacc), falling back to /api.
    api_prefix: str | None = None
    username: str | None = None
    password: str | None = None

    @classmethod
    def from_env(cls) -> DeploySettings:
        try:
            url = config("CHACC_DEPLOY_URL", default=None)
            timeout = config("CHACC_DEPLOY_TIMEOUT", default=DEFAULT_TIMEOUT, cast=int)
            restart_timeout = config(
                "CHACC_DEPLOY_RESTART_TIMEOUT", default=DEFAULT_RESTART_TIMEOUT, cast=int
            )
        except (ValueError, TypeError) as exc:
            raise DeployError(f"Invalid deployment configuration: {exc}") from exc
        if not url:
            raise DeployError(
                "CHACC_DEPLOY_URL is not set. Add it to your .env file "
                "(e.g. CHACC_DEPLOY_URL=http://your-api.com)."
            )
        auth_path = config("CHACC_DEPLOY_AUTH_PATH", default=DEFAULT_AUTH_PATH) or ""
        # Set-but-empty CHACC_DEPLOY_API_PREFIX means "no prefix"; unset means discover.
        api_prefix = config("CHACC_DEPLOY_API_PREFIX", default=None)
        return cls(
            url=url.rstrip("/"),
            api_key=config("CHACC_DEPLOY_API_KEY", default=None) or None,
            timeout=timeout,
            restart_timeout=restart_timeout,
            auth_path="/" + auth_path.strip("/"),
            api_prefix=None if api_prefix is None else normalize_prefix(api_prefix),
            username=config("CHACC_DEPLOY_USERNAME", default=None) or None,
            password=config("CHACC_DEPLOY_PASSWORD", default=None) or None,
        )


@dataclass
class _AuthState:
    access_token: str | None = None
    refresh_token: str | None = None
    logged_in: bool = False
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
        self.api_prefix: str | None = None
        self.warnings: list[str] = []

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

    @staticmethod
    def _too_large(response: requests.Response) -> str:
        """
        ChaCC's own 413 carries a JSON ``detail``. Anything else came from a
        proxy in front of it (nginx answers with an HTML page), so say that
        instead of printing the page.
        """
        data = _safe_json(response)
        if isinstance(data, dict) and data.get("detail"):
            return f"Package too large (413): {data['detail']}"
        proxy = response.headers.get("Server", "").split("/")[0] or "a proxy"
        return (
            f"Package too large (413): rejected by {proxy} in front of ChaCC, not by ChaCC. "
            "Raise the proxy's upload limit (nginx: client_max_body_size 11m;). "
            "See https://chacc.dev/deployment/#behind-a-reverse-proxy"
        )

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
        login_path = f"{self.auth_base}/login"

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
            f"{self.auth_base}/refresh",
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
                f"{self.settings.url}{self.auth_base}/revoke",
                json={"refresh_token": self.auth.refresh_token},
                timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
            )
        except requests.exceptions.RequestException:
            pass

    def resolve_prefix(self) -> str:
        """
        Determine the server's API prefix.

        Order: CHACC_DEPLOY_API_PREFIX (if set) → GET /.well-known/chacc → '/api'.
        """
        if self.api_prefix is not None:
            return self.api_prefix
        if self.settings.api_prefix is not None:
            self.api_prefix = self.settings.api_prefix
            return self.api_prefix

        self.api_prefix = DEFAULT_API_PREFIX
        info = self.discover()
        if info and isinstance(info.get("api_prefix"), str):
            self.api_prefix = normalize_prefix(info["api_prefix"])
        cli_logger.info(f"Using API prefix '{self.api_prefix or '/'}'.")
        return self.api_prefix

    def discover(self, quiet: bool = False) -> dict | None:
        """GET /.well-known/chacc. Returns None if unavailable (older server / down)."""
        try:
            response = self._request(
                "GET", DISCOVERY_PATH, timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT)
            )
        except DeployError:
            if quiet:
                return None
            raise
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    @property
    def modules_path(self) -> str:
        return f"{self.resolve_prefix()}{MODULES_PATH}"

    @property
    def auth_base(self) -> str:
        """Modules (incl. authentication) are always mounted under the API prefix."""
        return f"{self.resolve_prefix()}{self.settings.auth_path}"

    def ensure_authenticated(self) -> None:
        """Probe the modules endpoint and log in only if the server answers 401."""
        response = self._request("GET", self.modules_path, timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT))
        if response.status_code == 401:
            self.login()

    def upload(self, chacc_file_path: str) -> requests.Response:
        name = os.path.basename(chacc_file_path)
        with open(chacc_file_path, "rb") as f, _Waiter("Uploading and waiting for server response"):
            return self._request(
                "POST",
                self.modules_path,
                timeout=(CONNECT_TIMEOUT, self.settings.timeout),
                files={"file": (name, f, "application/zip")},
            )

    def restart(self) -> str:
        """
        Ask the server to restart and wait until a new process is serving.

        Returns a user-facing message. Raises DeployError only for hard failures;
        an unsupported restart (409/404) is reported as a message, not an error,
        because the module itself was installed.
        """
        before = self.discover(quiet=True) or {}
        response = self._request(
            "POST",
            f"{self.resolve_prefix()}{RESTART_PATH}",
            timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
        )
        if response.status_code == 401 and (self.refresh() or self._login_quietly()):
            response = self._request(
                "POST",
                f"{self.resolve_prefix()}{RESTART_PATH}",
                timeout=(CONNECT_TIMEOUT, PROBE_TIMEOUT),
            )
        if response.status_code in (404, 405):
            return "This server does not support automatic restart; restart it manually."
        if response.status_code == 409:
            return f"Automatic restart unavailable: {self._detail(response)}"
        if response.status_code not in (200, 202):
            raise DeployError(
                f"Restart request failed with status {response.status_code}: "
                f"{self._detail(response)}"
            )

        old_boot = before.get("boot_id") or _safe_json(response).get("boot_id")
        deadline = time.monotonic() + self.settings.restart_timeout
        with _Waiter("Restarting server"):
            while time.monotonic() < deadline:
                time.sleep(RESTART_POLL_INTERVAL)
                info = self.discover(quiet=True)
                if info and info.get("boot_id") and info.get("boot_id") != old_boot:
                    return "Server restarted; the module is now active."
        raise DeployError(
            f"Server did not come back within {self.settings.restart_timeout}s. "
            "Check the server logs (CHACC_DEPLOY_RESTART_TIMEOUT to wait longer)."
        )

    def _dependency_conflict(self, response: requests.Response) -> str:
        """Readable message for a 409, listing missing required modules if given."""
        data = _safe_json(response)
        missing = data.get("missing_dependencies") or {}
        required = missing.get("required") or []
        if not required:
            return f"Deployment refused (409): {self._detail(response)}"
        lines = ["Deployment refused: required module(s) are not installed on the server:"]
        lines += [f"  - {name}" for name in required]
        optional = missing.get("optional") or []
        if optional:
            lines.append(f"Optional module(s) also missing: {', '.join(optional)}")
        lines.append("Deploy the required modules first, then deploy this one again.")
        return "\n".join(lines)

    def _login_quietly(self) -> bool:
        try:
            self.login()
            return True
        except DeployError:
            return False

    def deploy(self, chacc_file_path: str, restart: bool = False) -> str:
        """Deploy the package (and optionally restart). Returns a success message."""
        try:
            self.ensure_authenticated()
            response = self.upload(chacc_file_path)
            if response.status_code == 401:
                if not self.refresh():
                    self.login()
                response = self.upload(chacc_file_path)

            if response.status_code == 200:
                data = _safe_json(response)
                message = data.get("message", "Module deployed.")
                self.warnings = [w for w in data.get("warnings") or [] if isinstance(w, str)]
                if restart:
                    message = f"{message}\n{self.restart()}"
                return message
            if response.status_code == 409:
                raise DeployError(self._dependency_conflict(response))
            if response.status_code == 401:
                raise DeployError("The server rejected the credentials (401).")
            if response.status_code == 403:
                raise DeployError(f"Permission denied (403): {self._detail(response)}")
            if response.status_code == 413:
                raise DeployError(self._too_large(response))
            raise DeployError(
                f"Deployment failed with status {response.status_code}: {self._detail(response)}"
            )
        finally:
            self.revoke()


def deploy_module(chacc_file_path: str, restart: bool = False) -> bool:
    """CLI entry point. Returns True on success."""
    if not os.path.isfile(chacc_file_path):
        cli_logger.error(f"ChaCC file '{chacc_file_path}' not found.")
        return False

    try:
        settings = DeploySettings.from_env()
        size_mb = os.path.getsize(chacc_file_path) / (1024 * 1024)
        cli_logger.info(f"Deploying '{chacc_file_path}' ({size_mb:.2f} MB) to {settings.url}...")
        deployer = Deployer(settings)
        message = deployer.deploy(chacc_file_path, restart=restart)
    except DeployError as exc:
        lines = str(exc).splitlines() or [""]
        cli_logger.error(f"FAILED: {lines[0]}")
        for line in lines[1:]:
            cli_logger.error(line)
        return False
    except KeyboardInterrupt:
        print()
        cli_logger.error("Deployment cancelled.")
        return False

    cli_logger.info("=" * 60)
    cli_logger.info("SUCCESS: Module deployed successfully!")
    for line in message.splitlines():
        cli_logger.info(f"SUCCESS: {line}")
    if not restart:
        cli_logger.info(
            "SUCCESS: Restart the server to activate the module "
            "(or deploy with --restart to do it automatically)."
        )
    for warning in deployer.warnings:
        cli_logger.warning(f"WARNING: {warning}")
    cli_logger.info("=" * 60)
    return True
