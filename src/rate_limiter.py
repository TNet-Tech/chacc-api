import functools
import inspect
import sys
import time
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .constants import RATE_LIMIT_ENABLED, RATE_LIMIT_STORAGE_URI
from .logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
    storage_uri=RATE_LIMIT_STORAGE_URI,
    in_memory_fallback_enabled=not RATE_LIMIT_STORAGE_URI.startswith("memory://"),
)

_limited: dict[str, Callable] = {}


def _with_request_parameter(func: Callable) -> Callable:
    """
    SlowAPI needs a ``request`` parameter. If the route has none, add a hidden one
    that FastAPI fills in and the route never sees.
    """
    sig = inspect.signature(func)
    if "request" in sig.parameters or "websocket" in sig.parameters:
        return func

    params = list(sig.parameters.values())
    hidden = inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request)
    if params and params[-1].kind is inspect.Parameter.VAR_KEYWORD:
        params.insert(len(params) - 1, hidden)
    else:
        params.append(hidden)

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def wrapper(*args, request: Request, **kwargs):
            return await func(*args, **kwargs)

    else:

        @functools.wraps(func)
        def wrapper(*args, request: Request, **kwargs):
            return func(*args, **kwargs)

    wrapper.__signature__ = sig.replace(parameters=params)
    return wrapper


def _owner(module_name: str) -> str:
    """The top-level package a module's code lives in, e.g. ``shop_demo_src``.

    Every loaded ChaCC module has its own top-level package (Python can't import
    two with the same name), so it is used to keep shared counters apart.
    """
    return module_name.split(".", 1)[0]


def _register(func: Callable, decorate: Callable[[Callable], Callable]) -> Callable:
    """Apply a SlowAPI decorator, dropping limits left over from an older definition."""
    name = f"{func.__module__}.{func.__name__}"
    original = inspect.unwrap(func)
    if _limited.get(name) not in (None, original):
        limiter._route_limits.pop(name, None)
        limiter._dynamic_route_limits.pop(name, None)
    _limited[name] = original
    return decorate(_with_request_parameter(func))


def rate_limit(
    limit_value: str | Callable[..., str],
    *,
    key: Callable[[Request], str] | None = None,
    cost: int | Callable[[Request], int] = 1,
    exempt_when: Callable[[Request], bool] | None = None,
    error_message: str | None = None,
    methods: list[str] | None = None,
    per_method: bool = False,
):
    """
    Limit how often a route can be called, e.g. ``"10/minute"`` or
    ``"5/second;100/hour"``. Put it under the route decorator:

        @router.get("/status")
        @rate_limit("10/minute")
        async def status():
            ...

    - ``key``: what to count by, a function of the request (default: client IP).
    - ``cost``: how many requests one call counts as (a number, or a function of
      the request).
    - ``exempt_when``: a function of the request; when it returns True the call
      isn't counted.
    - ``error_message``: the 429 ``detail`` text instead of the default.
    - ``methods``: only limit these HTTP methods, e.g. ``["POST"]``.
    - ``per_method``: count each HTTP method separately.

    Over the limit, the client gets 429 with a Retry-After header.
    """

    def decorator(func: Callable) -> Callable:
        return _register(
            func,
            limiter.limit(
                limit_value,
                key_func=key,
                cost=cost,
                exempt_when=exempt_when,
                error_message=error_message,
                methods=methods,
                per_method=per_method,
            ),
        )

    return decorator


def shared_rate_limit(
    limit_value: str | Callable[..., str],
    *,
    scope: str,
    key: Callable[[Request], str] | None = None,
    cost: int | Callable[[Request], int] = 1,
    exempt_when: Callable[[Request], bool] | None = None,
    error_message: str | None = None,
):
    """
    One limit shared by several routes: calls to any of them count together.
    Create it once and decorate each route with it:

        search_limit = shared_rate_limit("60/minute", scope="search")

        @router.get("/search/items")
        @search_limit
        async def search_items(): ...

    ``scope`` names the shared counter. It only needs to be unique within your
    module: ChaCC prefixes it with the module's package, so two modules using
    ``"search"`` get separate counters. The other options are the same as
    ``rate_limit``.
    """

    def decorator(func: Callable) -> Callable:
        return _register(
            func,
            limiter.shared_limit(
                limit_value,
                f"{_owner(func.__module__)}:{scope}",
                key_func=key,
                cost=cost,
                exempt_when=exempt_when,
                error_message=error_message,
            ),
        )

    return decorator


_memory_fallback = FixedWindowRateLimiter(MemoryStorage())
_STORAGE_RETRY_SECONDS = 30
_storage_down_until = 0.0


def check_rate_limit(limit_value: str, *identifiers: str, cost: int = 1) -> bool:
    """
    Count one use of something that isn't a route and say whether it is allowed.
    Returns False once the limit is reached:

        if not check_rate_limit("5/minute", "login", username):
            raise HTTPException(429, "Too many attempts, try again later.")

    ``identifiers`` name what is counted. They only need to be unique within your
    module: ChaCC prefixes them with the calling module's package. Uses the same
    storage as route limits, and always allows when ``RATE_LIMIT_ENABLED`` is false.
    """
    if not identifiers:
        raise ValueError("check_rate_limit needs at least one identifier.")
    identifiers = (_owner(sys._getframe(1).f_globals.get("__name__", "")), *identifiers)
    if not limiter.enabled:
        return True
    global _storage_down_until
    allowed = True
    for item in parse_many(limit_value):
        backend = limiter.limiter
        if time.monotonic() < _storage_down_until:
            backend = _memory_fallback
        try:
            hit = backend.hit(item, "check", *identifiers, cost=cost)
        except Exception as e:  # noqa: BLE001 - storage unreachable: count in memory
            if _storage_down_until == 0.0:
                chacc_logger.warning(f"Rate limit storage unreachable, counting in memory: {e}")
            _storage_down_until = time.monotonic() + _STORAGE_RETRY_SECONDS
            hit = _memory_fallback.hit(item, "check", *identifiers, cost=cost)
        else:
            if backend is not _memory_fallback and _storage_down_until:
                chacc_logger.info("Rate limit storage reachable again.")
                _storage_down_until = 0.0
        allowed = allowed and hit
    return allowed


DEFAULT_RETRY_AFTER_SECONDS = 60


def get_retry_after_seconds(exc: RateLimitExceeded) -> int:
    """
    Return how many whole seconds a client should wait before retrying.

    ``Retry-After`` must be an integer number of seconds (RFC 9110). We read the
    window length from the limit that was hit (e.g. "5 per 1 minute" -> 60) and
    fall back to a safe default if it cannot be determined (for example when a
    custom error message replaced the default detail text).
    """
    limit_item = getattr(getattr(exc, "limit", None), "limit", None)
    try:
        return max(1, int(limit_item.get_expiry()))
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for RateLimitExceeded errors.
    Returns HTTP 429 with a JSON body and a valid ``Retry-After`` header.
    """
    custom = getattr(getattr(exc, "limit", None), "error_message", None)
    detail = (
        exc.detail
        if custom
        else (f"Too many requests. You have exceeded the rate limit of {exc.detail}.")
    )
    return JSONResponse(
        status_code=429,
        content={"detail": detail},
        headers={"Retry-After": str(get_retry_after_seconds(exc))},
    )
