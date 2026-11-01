"""Health endpoint behaviour: readiness must reflect database availability."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from src.database import get_async_db
from src.health import get_version, health_router


class _FakeSession:
    def __init__(self, fail: bool):
        self.fail = fail

    async def execute(self, *_args, **_kwargs):
        if self.fail:
            raise OperationalError("SELECT 1", {}, Exception("database is down"))


def _client(fail: bool) -> TestClient:
    app = FastAPI()
    app.include_router(health_router, prefix="/api")

    async def _override():
        yield _FakeSession(fail)

    app.dependency_overrides[get_async_db] = _override
    return TestClient(app)


def test_ready_returns_200_when_database_is_up():
    response = _client(fail=False).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["checks"]["database"] == "ok"


def test_ready_returns_503_when_database_is_down():
    response = _client(fail=True).get("/api/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"] == "error"


def test_liveness_stays_200_even_if_database_is_down():
    assert _client(fail=True).get("/api/health/live").status_code == 200


def test_version_endpoint_matches_get_version():
    response = _client(fail=False).get("/api/version")
    assert response.status_code == 200
    assert response.json()["version"] == get_version()
