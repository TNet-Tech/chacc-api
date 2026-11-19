"""chacc_api.rate_limit.rate_limit on real FastAPI routes."""

import types

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from chacc_api.rate_limit import check_rate_limit, limiter, rate_limit, shared_rate_limit
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


def test_shared_limit_counts_routes_together():
    router = APIRouter()
    search = shared_rate_limit("3/minute", scope="test:search")

    @router.get("/s/items")
    @search
    async def rl_search_items():
        return {}

    @router.get("/s/users")
    @search
    async def rl_search_users():
        return {}

    @router.get("/s/other")
    @rate_limit("3/minute")
    async def rl_other():
        return {}

    client = client_for(router)
    assert statuses(client, "/s/items", 2) == [200, 200]
    assert statuses(client, "/s/users", 2) == [200, 429]
    assert statuses(client, "/s/other", 1) == [200]  # not part of the scope


def test_cost_counts_heavy_calls_more():
    router = APIRouter()

    @router.get("/export")
    @rate_limit("10/minute", cost=4)
    async def rl_export():
        return {}

    @router.get("/dyn")
    @rate_limit("3/minute", cost=lambda request: int(request.query_params.get("n", 1)))
    async def rl_dynamic_cost():
        return {}

    client = client_for(router)
    assert statuses(client, "/export", 3) == [200, 200, 429]
    assert client.get("/dyn?n=3").status_code == 200
    assert client.get("/dyn").status_code == 429


def test_exempt_when_skips_counting():
    router = APIRouter()

    @router.get("/internal")
    @rate_limit("1/minute", exempt_when=lambda request: request.headers.get("x-internal") == "1")
    async def rl_exempt():
        return {}

    client = client_for(router)
    assert statuses(client, "/internal", 3, headers={"x-internal": "1"}) == [200, 200, 200]
    assert statuses(client, "/internal", 2) == [200, 429]


def test_error_message_is_used_as_detail():
    router = APIRouter()

    @router.get("/msg")
    @rate_limit("1/minute", error_message="Slow down, please.")
    async def rl_message():
        return {}

    client = client_for(router)
    client.get("/msg")
    over = client.get("/msg")
    assert over.status_code == 429
    assert over.json() == {"detail": "Slow down, please."}
    assert over.headers["retry-after"] == "60"


def test_methods_limits_only_listed_methods():
    router = APIRouter()

    @router.api_route("/form", methods=["GET", "POST"])
    @rate_limit("1/minute", methods=["POST"])
    async def rl_form():
        return {}

    client = client_for(router)
    assert statuses(client, "/form", 3) == [200, 200, 200]
    assert [client.post("/form").status_code for _ in range(2)] == [200, 429]


def test_check_rate_limit_outside_routes():
    assert [check_rate_limit("2/minute", "test:login", "alice") for _ in range(3)] == [
        True,
        True,
        False,
    ]
    assert check_rate_limit("2/minute", "test:login", "bob")  # counted separately
    assert check_rate_limit("1/minute;5/hour", "test:multi", "x")
    assert not check_rate_limit("1/minute;5/hour", "test:multi", "x")
    with pytest.raises(ValueError):
        check_rate_limit("1/minute")


def test_check_rate_limit_allows_everything_when_disabled(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    assert all(check_rate_limit("1/minute", "test:off", "x") for _ in range(3))


def test_context_limiter_is_deprecated_but_works():
    import logging

    from src.core_services import BackboneContext

    ctx = BackboneContext(None, limiter, logging.getLogger("t"), None, None)
    with pytest.warns(DeprecationWarning, match="chacc_api.rate_limit"):
        assert ctx.limiter is limiter


def test_public_limiter_is_the_server_limiter():
    from chacc_api.server.main import app

    assert app.state.limiter is limiter


def _route_in(package: str, path: str, decorate):
    """Define a route as if it lived in another module's package."""

    async def endpoint():
        return {}

    endpoint.__module__ = f"{package}.routes"
    endpoint.__name__ = endpoint.__qualname__ = f"ep_{package}_{path.strip('/')}"
    return path, decorate(endpoint)


def test_same_scope_name_in_two_modules_is_kept_apart():
    router = APIRouter()
    for package, path in [("mod_a_src", "/a1"), ("mod_a_src", "/a2"), ("mod_b_src", "/b")]:
        # Each module creates its own "search" limit, as module code would.
        p, ep = _route_in(package, path, shared_rate_limit("2/minute", scope="search"))
        router.get(p)(ep)

    client = client_for(router)
    assert statuses(client, "/a1", 1) == [200]
    assert statuses(client, "/a2", 2) == [200, 429]  # same module: shared
    assert statuses(client, "/b", 2) == [200, 200]  # other module: own counter


def test_check_rate_limit_names_are_per_module():
    def login_attempt():
        return check_rate_limit("1/minute", "login", "alice")

    def call_from(package):
        # The same code, run as if it lived in `package`.
        module_globals = {"__name__": f"{package}.services", "check_rate_limit": check_rate_limit}
        return types.FunctionType(login_attempt.__code__, module_globals)()

    assert call_from("mod_a_src") is True
    assert call_from("mod_a_src") is False  # same module: same counter
    assert call_from("mod_b_src") is True  # other module, same names: own counter
