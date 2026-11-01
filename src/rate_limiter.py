from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

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
