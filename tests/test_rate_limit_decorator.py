"""chacc_api.rate_limit.rate_limit on real FastAPI routes."""

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from chacc_api.rate_limit import limiter, rate_limit
from src.rate_limiter import rate_limit_exceeded_handler


@pytest.fixture(autouse=True)
def fresh_counts():
    limiter.reset()
    yield
    limiter.reset()


def client_for(router: APIRouter) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(router)
    return TestClient(app)


def statuses(client, path, n, **kwargs):
    return [client.get(path, **kwargs).status_code for _ in range(n)]


def test_route_without_request_parameter():
    router = APIRouter()

    @router.get("/items/{item_id}")
    @rate_limit("2/minute")
    async def rl_no_request(item_id: int, q: str = "x"):
        return {"item_id": item_id, "q": q}

    client = client_for(router)
    first = client.get("/items/3?q=y")
    assert first.json() == {"item_id": 3, "q": "y"}
    assert statuses(client, "/items/3", 2) == [200, 429]

    over = client.get("/items/3")
    assert over.headers["retry-after"] == "60"
    assert "2 per 1 minute" in over.json()["detail"]


def test_route_with_own_request_parameter_and_sync_route():
    router = APIRouter()

    @router.get("/mine")
    @rate_limit("1/minute")
    async def rl_with_request(request: Request):
        return {"path": request.url.path}

    @router.get("/sync")
    @rate_limit("1/minute")
    def rl_sync():
        return {"ok": True}

    client = client_for(router)
    assert client.get("/mine").json() == {"path": "/mine"}
    assert statuses(client, "/mine", 1) == [429]
    assert statuses(client, "/sync", 2) == [200, 429]


def test_custom_key_counts_separately():
    router = APIRouter()

    @router.get("/keyed")
    @rate_limit("1/minute", key=lambda request: request.headers.get("x-api-key", "anon"))
    async def rl_keyed():
        return {}

    client = client_for(router)
    assert statuses(client, "/keyed", 2, headers={"x-api-key": "a"}) == [200, 429]
    assert statuses(client, "/keyed", 1, headers={"x-api-key": "b"}) == [200]


def test_stacked_limits_both_apply():
    router = APIRouter()

    @router.get("/stacked")
    @rate_limit("3/minute")
    @rate_limit("2/minute")
    async def rl_stacked():
        return {}

    assert statuses(client_for(router), "/stacked", 3) == [200, 200, 429]


def test_redefined_route_is_not_counted_twice():
    def define():
        router = APIRouter()

        @router.get("/reloaded")
        @rate_limit("2/minute")
        async def rl_reloaded():
            return {}

        return router

    define()  # first load
    client = client_for(define())  # module reloaded: same name, new function
    assert statuses(client, "/reloaded", 3) == [200, 200, 429]


def test_public_limiter_is_the_server_limiter():
    from chacc_api.server.main import app

    assert app.state.limiter is limiter
