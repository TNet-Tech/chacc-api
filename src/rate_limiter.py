import functools
import inspect
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .constants import RATE_LIMIT_ENABLED, RATE_LIMIT_STORAGE_URI

# One limiter for the whole server (app.state.limiter, context.limiter).
# The client is identified by its IP. Behind a reverse proxy, uvicorn takes it from
# X-Forwarded-For when the proxy's address is in FORWARDED_ALLOW_IPS.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
    storage_uri=RATE_LIMIT_STORAGE_URI,
    # If Redis is unreachable, count in memory instead of failing requests.
    in_memory_fallback_enabled=not RATE_LIMIT_STORAGE_URI.startswith("memory://"),
)

# endpoint name -> the original function its limits were registered for
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


def rate_limit(
    limit_value: str | Callable[..., str],
    *,
    key: Callable[[Request], str] | None = None,
):
    """
    Limit how often a route can be called, e.g. ``"10/minute"`` or
    ``"5/second;100/hour"``. Put it under the route decorator:

        @router.get("/status")
        @rate_limit("10/minute")
        async def status():
            ...

    Clients are counted by IP; pass ``key`` (a function of the request) to count
    by something else, such as an API key header. Over the limit, the client gets
    429 with a Retry-After header.
    """

    def decorator(func: Callable) -> Callable:
        name = f"{func.__module__}.{func.__name__}"
        original = inspect.unwrap(func)
        if _limited.get(name) not in (None, original):
            # The route was defined again (module reloaded): drop the old limits
            # instead of counting every request twice.
            limiter._route_limits.pop(name, None)
            limiter._dynamic_route_limits.pop(name, None)
        _limited[name] = original
        return limiter.limit(limit_value, key_func=key)(_with_request_parameter(func))

    return decorator


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
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests. You have exceeded the rate limit of {exc.detail}."},
        headers={"Retry-After": str(get_retry_after_seconds(exc))},
    )
