"""
End-to-end tests for automatic restarts.

These start a real ``chacc run server`` (the supervisor) in a temporary
working directory, talk to it over HTTP and check that:

- ``POST /api/system/restart`` replaces the server process while the
  supervisor keeps running (production; ``--dev`` refuses restarts);
- a request already in progress finishes during a restart (graceful shutdown);
- ``chacc deploy --restart`` makes a new module live with no manual step;
- Ctrl+C still stops everything cleanly.

Each server start takes a few seconds; deselect with ``-m "not e2e"``.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform == "win32", reason="relies on POSIX signals"),
]

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT = 90
RESTART_TIMEOUT = 60


# ---------- helpers ----------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _base_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CHACC_", "API_PREFIX", "MODULES_", "PLUGINS_DIR"))
    }
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["SECRET_KEY"] = "e2e-" + "k9Qz7Lr2Vx5Mw8Np3Ts6Yb1Hc4Jf0Gd"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _get_json(url: str, timeout: float = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def _status(url: str, method: str = "GET", timeout: float = 30) -> int:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


class Server:
    """A ``chacc run server`` process in its own session/process group."""

    def __init__(self, workdir: Path, dev: bool = False):
        self.workdir = workdir
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = workdir / ("dev.log" if dev else "server.log")
        cmd = [sys.executable, "-m", "chacc_cli", "run", "server", "--port", str(self.port)]
        if dev:
            cmd.append("--dev")
        self._log = open(self.log_path, "w")  # noqa: SIM115
        self.proc = subprocess.Popen(
            cmd,
            cwd=workdir,
            env=_base_env(),
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # own process group: we can signal it safely
        )

    def info(self) -> dict | None:
        try:
            return _get_json(f"{self.base}/.well-known/chacc", timeout=2)
        except (OSError, ValueError):
            return None

    def wait_up(self, timeout: float = STARTUP_TIMEOUT) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                pytest.fail(f"supervisor exited early ({self.proc.returncode}):\n{self.log()}")
            info = self.info()
            if info:
                return info
            time.sleep(0.5)
        pytest.fail(f"server did not start within {timeout}s:\n{self.log()}")

    def wait_new_boot(self, old_boot_id: str, timeout: float = RESTART_TIMEOUT) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.info()
            if info and info["boot_id"] != old_boot_id and not info["restart_pending"]:
                return info
            assert self.proc.poll() is None, f"supervisor died during restart:\n{self.log()}"
            time.sleep(0.5)
        pytest.fail(f"server did not restart within {timeout}s:\n{self.log()}")

    def log(self) -> str:
        self._log.flush()
        return self.log_path.read_text(errors="replace")[-4000:]

    def stop(self) -> int:
        """Ctrl+C equivalent: SIGINT to the whole process group."""
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGINT)
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        self._log.close()
        return self.proc.returncode


def _make_module(path: Path, name: str, routes: str, required: tuple[str, ...] = ()) -> Path:
    meta = {
        "name": name,
        "display_name": name,
        "version": "1.0.0",
        "entry_point": "module.main:setup",
        "base_path_prefix": f"/{name}",
    }
    if required:
        meta["module_dependencies"] = {"required": list(required)}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("module_meta.json", json.dumps(meta))
        z.writestr("module/__init__.py", "")
        z.writestr(
            "module/main.py",
            "import asyncio\nfrom fastapi import APIRouter\n\n"
            "def setup(ctx):\n    r = APIRouter()\n" + routes + "    return r\n",
        )
    return path


PING_ROUTE = "    @r.get('/ping')\n    async def ping():\n        return {'pong': True}\n"
SLOW_ROUTE = (
    "    @r.get('/slow')\n    async def slow():\n"
    "        await asyncio.sleep(3)\n        return {'done': True}\n"
)


def _deploy(server: Server, chacc: Path, restart: bool) -> subprocess.CompletedProcess:
    env = _base_env() | {"CHACC_DEPLOY_URL": server.base}
    cmd = [sys.executable, "-m", "chacc_cli", "deploy", str(chacc)]
    if restart:
        cmd.append("--restart")
    return subprocess.run(
        cmd,
        cwd=server.workdir,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )


@pytest.fixture
def server(tmp_path):
    srv = Server(tmp_path)
    srv.wait_up()
    yield srv
    srv.stop()


# ---------- tests ----------


def test_restart_replaces_process_and_keeps_supervisor(server):
    before = server.info()
    assert before["restart_supported"] is True

    assert _status(f"{server.base}/api/system/restart", method="POST") == 202
    after = server.wait_new_boot(before["boot_id"])

    assert after["started_at"] > before["started_at"]
    assert server.proc.poll() is None, "supervisor must keep running"
    assert "Restarting ChaCC server (restart #1)" in server.log()
    assert not list((server.workdir / ".chacc_cache").glob("restart-*.request"))

    # And it can do it again.
    assert _status(f"{server.base}/api/system/restart", method="POST") == 202
    server.wait_new_boot(after["boot_id"])
    assert "restart #2" in server.log()


def test_deploy_with_restart_activates_module(server, tmp_path):
    chacc = _make_module(tmp_path / "hello_e2e.chacc", "hello_e2e", PING_ROUTE)
    assert _status(f"{server.base}/api/hello_e2e/ping") == 404

    result = _deploy(server, chacc, restart=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Server restarted" in result.stdout + result.stderr

    assert _get_json(f"{server.base}/api/hello_e2e/ping") == {"pong": True}


def test_in_flight_request_completes_during_restart(server, tmp_path):
    chacc = _make_module(tmp_path / "slow_e2e.chacc", "slow_e2e", SLOW_ROUTE)
    assert _deploy(server, chacc, restart=True).returncode == 0
    boot = server.info()["boot_id"]

    result: dict = {}

    def call_slow():
        try:
            result["body"] = _get_json(f"{server.base}/api/slow_e2e/slow", timeout=30)
        except Exception as exc:
            result["error"] = repr(exc)

    worker = threading.Thread(target=call_slow)
    worker.start()
    time.sleep(0.5)  # make sure the slow request is in flight
    assert _status(f"{server.base}/api/system/restart", method="POST") == 202
    worker.join(timeout=30)

    assert result.get("body") == {"done": True}, result
    server.wait_new_boot(boot)


def test_ctrl_c_stops_supervisor_cleanly(tmp_path):
    srv = Server(tmp_path)
    srv.wait_up()
    assert srv.stop() == 0
    assert "Shutting down ChaCC server" in srv.log_path.read_text()
    assert srv.info() is None


def test_restart_refused_in_dev_mode(tmp_path):
    srv = Server(tmp_path, dev=True)
    try:
        before = srv.wait_up()
        assert before["restart_supported"] is False
        assert _status(f"{srv.base}/api/system/restart", method="POST") == 409
        assert srv.info()["boot_id"] == before["boot_id"]
    finally:
        srv.stop()


def test_broken_module_is_skipped_and_server_still_restarts(server, tmp_path):
    good = _make_module(tmp_path / "good_e2e.chacc", "good_e2e", PING_ROUTE)
    assert _deploy(server, good, restart=True).returncode == 0

    broken = tmp_path / "broken_e2e.chacc"
    with zipfile.ZipFile(broken, "w") as z:
        z.writestr(
            "module_meta.json",
            json.dumps(
                {
                    "name": "broken_e2e",
                    "version": "1.0.0",
                    "entry_point": "module.main:setup",
                    "base_path_prefix": "/broken_e2e",
                }
            ),
        )
        z.writestr("module/__init__.py", "")
        z.writestr("module/main.py", "raise RuntimeError('boom on import')\n")

    result = _deploy(server, broken, restart=True)
    assert result.returncode == 0, result.stdout + result.stderr

    assert server.proc.poll() is None
    assert _get_json(f"{server.base}/api/good_e2e/ping") == {"pong": True}
    assert _status(f"{server.base}/api/broken_e2e/ping") == 404
    assert "broken_e2e" in server.log()


def test_startup_failure_ends_supervision_instead_of_looping(tmp_path):
    """If the server cannot start (port taken), the supervisor exits non-zero."""
    with socket.socket() as blocker:
        blocker.bind(("0.0.0.0", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        result = subprocess.run(
            [sys.executable, "-m", "chacc_cli", "run", "server", "--port", str(port)],
            cwd=tmp_path,
            env=_base_env(),
            capture_output=True,
            text=True,
            timeout=STARTUP_TIMEOUT,
            check=False,
        )
    assert result.returncode != 0
    assert "Restarting ChaCC server" not in result.stdout + result.stderr


def _children(pid: int) -> list[int]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    if not path.exists():
        pytest.skip("needs /proc children (Linux)")
    return [int(p) for p in path.read_text().split()]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still "exists"; treat it as gone.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")


def test_sigterm_to_supervisor_shuts_down_gracefully(server, tmp_path):
    """
    Same as `docker stop`: SIGTERM to the supervisor (PID 1 in the container)
    only. The server must finish in-flight requests, then everything exits.
    """
    chacc = _make_module(tmp_path / "slow_stop.chacc", "slow_stop", SLOW_ROUTE)
    assert _deploy(server, chacc, restart=True).returncode == 0
    server_pids = _children(server.proc.pid)
    assert server_pids, "supervisor should have a server child"

    result: dict = {}

    def call_slow():
        try:
            result["body"] = _get_json(f"{server.base}/api/slow_stop/slow", timeout=30)
        except Exception as exc:
            result["error"] = repr(exc)

    worker = threading.Thread(target=call_slow)
    worker.start()
    time.sleep(0.5)

    server.proc.send_signal(signal.SIGTERM)  # supervisor only, not the group
    worker.join(timeout=30)
    assert result.get("body") == {"done": True}, result

    assert server.proc.wait(timeout=30) == 0
    deadline = time.monotonic() + 10
    while any(_alive(p) for p in server_pids) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not any(_alive(p) for p in server_pids), "server process was orphaned"
    assert server.info() is None


def test_module_dependencies_end_to_end(server, tmp_path):
    """Deploy refuses a missing required module; startup skips and highlights it."""
    menu = _make_module(tmp_path / "menu_e2e.chacc", "menu_e2e", PING_ROUTE, ("auth_e2e",))
    auth = _make_module(tmp_path / "auth_e2e.chacc", "auth_e2e", PING_ROUTE)

    refused = _deploy(server, menu, restart=False)
    assert refused.returncode == 1
    assert "- auth_e2e" in refused.stdout + refused.stderr

    # Bypass the API (e.g. copied by hand): the server must skip it, not crash.
    installed = server.workdir / ".modules_installed"
    (installed / "menu_e2e.chacc").write_bytes(menu.read_bytes())
    boot = server.info()["boot_id"]
    assert _status(f"{server.base}/api/system/restart", method="POST") == 202
    server.wait_new_boot(boot)
    assert _status(f"{server.base}/api/menu_e2e/ping") == 404
    assert "MODULE DEPENDENCIES NEED ATTENTION" in server.log()
    assert "menu_e2e: NOT LOADED - missing required module(s): auth_e2e" in server.log()

    # Install the dependency: both load after the restart.
    result = _deploy(server, auth, restart=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _get_json(f"{server.base}/api/auth_e2e/ping") == {"pong": True}
    assert _get_json(f"{server.base}/api/menu_e2e/ping") == {"pong": True}
