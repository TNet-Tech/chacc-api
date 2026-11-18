"""GET {prefix}/system/services and the checks behind it."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from src import rate_limiter, service_status
from src.rate_limiter import mask_uri
from src.redis_service import RedisService


def by_id(payload):
    return {s["id"]: s for s in payload["services"]}


def test_endpoint_reports_every_service():
    from chacc_api.server.main import app

    with TestClient(app) as client:
        response = client.get("/api/system/services")
    assert response.status_code == 200
    payload = response.json()
    services = by_id(payload)
    assert list(services) == ["database", "redis", "rate_limit", "server"]

    assert services["database"]["status"] == "ok"
    assert services["database"]["description"]
    db_type = next(d["value"] for d in services["database"]["details"] if d["label"] == "Type")
    assert db_type.startswith(("SQLite", "PostgreSQL"))
    assert services["database"]["latency_ms"] is not None
    assert services["redis"]["status"] == "disabled"
    assert services["rate_limit"]["status"] == "ok"
    assert services["server"]["status"] == "ok"
    assert services["server"]["started_at"] > 0
    assert payload["status"] == "ok"  # disabled Redis is not a problem


def test_redis_enabled_but_unreachable_is_down():
    service = RedisService()
    service._enabled = True
    service._host, service._port = "127.0.0.1", 6390  # nothing listens here

    result = asyncio.run(service_status.redis_status(service))
    assert result["status"] == "down"
    assert result["message"] == "Nothing is answering at 127.0.0.1:6390."
    assert result["hint"] == "ChaCC keeps running and reconnects when Redis is back."
    assert "111" in result["error"] or "refused" in result["error"].lower()
    assert {"label": "Server", "value": "127.0.0.1:6390"} in result["details"]


def test_redis_reachable_shows_version_and_memory(monkeypatch):
    service = RedisService()
    service._enabled = True

    async def fake_check():
        return {"connected": True, "error": None, "version": "7.4.1", "memory": "1.2M"}

    monkeypatch.setattr(service, "check", fake_check)
    result = asyncio.run(service_status.redis_status(service))
    assert result["status"] == "ok"
    assert {"label": "Version", "value": "7.4.1"} in result["details"]
    assert {"label": "Memory", "value": "1.2 MB"} in result["details"]


def test_redis_coming_back_is_picked_up_without_restart():
    service = RedisService()
    service._enabled = True
    service._host, service._port = "127.0.0.1", 6390

    async def run():
        assert await service.get_client() is None
        assert service.connection_error
        # Within the reconnect wait, get_client() doesn't try again (no timeout per call).
        assert await service.get_client() is None
        # A status check always tries again.
        state = await service.check()
        assert state["connected"] is False and state["error"]

    asyncio.run(run())


def test_rate_limiting_with_unreachable_storage_is_degraded(monkeypatch):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_STORAGE_URI", "redis://:secret@redis:6379/0")

    def broken_check():
        raise ConnectionError("Connection refused")

    monkeypatch.setattr(rate_limiter.limiter._storage, "check", broken_check)
    result = asyncio.run(service_status.rate_limit_status())
    assert result["status"] == "degraded"
    assert result["message"] == (
        "Redis (redis:6379) is unreachable, so requests are counted on this server."
    )
    assert "secret" not in str(result)


def test_rate_limiting_disabled(monkeypatch):
    monkeypatch.setattr(rate_limiter.limiter, "enabled", False)
    result = asyncio.run(service_status.rate_limit_status())
    assert result["status"] == "disabled"


def test_database_down_is_reported(monkeypatch):
    async def broken():
        raise ConnectionError("could not connect to server")

    monkeypatch.setattr(service_status, "_database_version", broken)
    result = asyncio.run(service_status.database_status())
    assert result["status"] == "down"
    assert "could not connect" in result["error"]
    assert result["message"]


def test_slow_check_times_out(monkeypatch):
    async def hangs():
        await asyncio.sleep(10)

    monkeypatch.setattr(service_status, "_database_version", hangs)
    monkeypatch.setattr(service_status, "CHECK_TIMEOUT_SECONDS", 0.1)
    result = asyncio.run(service_status.database_status())
    assert result["status"] == "down"
    assert "didn't answer in time" in result["message"]


def test_overall_status_is_the_worst(monkeypatch):
    async def down():
        return service_status._service("database", "Database", "down", "x", [])

    monkeypatch.setattr(service_status, "database_status", down)
    payload = asyncio.run(service_status.collect(None, 0.0, False))
    assert payload["status"] == "down"


@pytest.mark.parametrize(
    ("uri", "shown"),
    [
        ("memory://", "memory://"),
        ("redis://redis:6379/0", "redis://redis:6379/0"),
        ("redis://:pw@redis:6379/0", "redis://:***@redis:6379/0"),
        ("rediss://user:pw@host:6380/1", "rediss://user:***@host:6380/1"),
    ],
)
def test_mask_uri(uri, shown):
    assert mask_uri(uri) == shown


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("Error 111 connecting to localhost:6390. Connect call failed", "Nothing is answering"),
        ("no answer within 2 s", "didn't answer in time"),
        ("Error -2 connecting to redis:6379. Name or service not known.", "can't be found"),
        ('FATAL:  password authentication failed for user "chacc"', "Wrong user name or password"),
        ("WRONGPASS invalid username-password pair", "Wrong user name or password"),
        ('FATAL:  database "nope" does not exist', "database doesn't exist"),
        ("unable to open database file", "can't be opened"),
        ("something unusual", "Can't connect to"),
    ],
)
def test_errors_are_explained_in_plain_words(error, expected):
    assert expected in service_status.explain_error(error, "host:1")
