"""Tests for the restart endpoint and the launcher's restart plumbing."""

import asyncio
import os
import signal
import subprocess
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import app
from src import lifecycle, system


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_restart_state(monkeypatch):
    monkeypatch.setattr(system, "_restart_pending", False)
    monkeypatch.setattr(system, "_restart_task", None)
    yield


def test_discovery_exposes_boot_id(client):
    data = client.get("/.well-known/chacc").json()
    assert data["boot_id"] == system.BOOT_ID
    assert data["restart_supported"] is False
    assert data["restart_pending"] is False


def test_restart_refused_when_not_supervised(client, monkeypatch):
    monkeypatch.delenv(lifecycle.SUPERVISED_ENV, raising=False)
    response = client.post("/api/system/restart")
    assert response.status_code == 409
    assert "chacc run server" in response.json()["detail"]


def test_restart_writes_marker_and_schedules_sigterm(client, monkeypatch, tmp_path):
    fake_pid = 999_999
    monkeypatch.setenv(lifecycle.SUPERVISED_ENV, "1")
    monkeypatch.setenv(lifecycle.SERVER_ROOT_PID_ENV, str(fake_pid))
    monkeypatch.setattr(lifecycle, "DEPENDENCY_CACHE_DIR", str(tmp_path))
    scheduled = []
    monkeypatch.setattr(system, "_signal_shutdown", lambda pid: scheduled.append(pid) or _noop())

    response = client.post("/api/system/restart")
    assert response.status_code == 202
    assert response.json()["boot_id"] == system.BOOT_ID
    assert (tmp_path / f"restart-{fake_pid}.request").exists()
    assert scheduled == [fake_pid]

    # A second request while pending does not schedule another shutdown.
    again = client.post("/api/system/restart")
    assert again.status_code == 202
    assert "already in progress" in again.json()["message"]
    assert scheduled == [fake_pid]
    assert client.get("/.well-known/chacc").json()["restart_pending"] is True


async def _noop():
    return None


def test_signal_shutdown_sends_sigterm(monkeypatch):
    sent = []
    monkeypatch.setattr(system, "RESTART_DELAY_SECONDS", 0)
    monkeypatch.setattr(system.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    asyncio.run(system._signal_shutdown(1234))
    assert sent == [(1234, signal.SIGTERM)]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize(
    ("request_restart", "expected"),
    [(True, lifecycle.RESTART_EXIT_CODE), (False, -signal.SIGTERM)],
)
def test_run_server_maps_sigterm_to_exit_code(tmp_path, request_restart, expected):
    """
    Mimic uvicorn: it captures SIGTERM, shuts down, restores the previous
    handler and re-raises the signal. The launcher must turn that into the
    restart exit code only when a restart was requested.
    """
    script = textwrap.dedent(
        f"""
        import os, signal
        from src import lifecycle
        lifecycle.DEPENDENCY_CACHE_DIR = {str(tmp_path)!r}

        def fake_uvicorn_run():
            original = signal.signal(signal.SIGTERM, lambda *a: None)
            if {request_restart!r}:
                lifecycle.request_restart(int(os.environ[lifecycle.SERVER_ROOT_PID_ENV]))
            signal.signal(signal.SIGTERM, original)
            signal.raise_signal(signal.SIGTERM)

        lifecycle.run_server(fake_uvicorn_run)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        timeout=60,
        check=False,
    )
    assert result.returncode == expected
    assert not list(tmp_path.glob("restart-*.request"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_run_server_reload_mode_returns_normally(tmp_path):
    """In --dev mode uvicorn.run returns normally; the marker alone decides."""
    script = textwrap.dedent(
        f"""
        import os
        from src import lifecycle
        lifecycle.DEPENDENCY_CACHE_DIR = {str(tmp_path)!r}
        lifecycle.run_server(
            lambda: lifecycle.request_restart(int(os.environ[lifecycle.SERVER_ROOT_PID_ENV]))
        )
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        timeout=60,
        check=False,
    )
    assert result.returncode == lifecycle.RESTART_EXIT_CODE


def test_restart_refused_in_dev_mode(client, monkeypatch, tmp_path):
    monkeypatch.setenv(lifecycle.SUPERVISED_ENV, "1")
    monkeypatch.setenv(lifecycle.SERVER_ROOT_PID_ENV, "999999")
    monkeypatch.setattr(lifecycle, "DEPENDENCY_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(system, "DEVELOPMENT_MODE", True)
    response = client.post("/api/system/restart")
    assert response.status_code == 409
    assert "development mode" in response.json()["detail"]
    assert list(tmp_path.iterdir()) == []
    assert client.get("/.well-known/chacc").json()["restart_supported"] is False
