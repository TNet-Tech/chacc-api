"""Tests for the 429 response produced by the rate-limit handler."""

import asyncio
import json
from types import SimpleNamespace

from src.rate_limiter import (
    DEFAULT_RETRY_AFTER_SECONDS,
    get_retry_after_seconds,
    rate_limit_exceeded_handler,
)


def _exc(expiry=None, detail="5 per 1 minute"):
    """Build an object shaped like slowapi's RateLimitExceeded."""
    item = SimpleNamespace(get_expiry=lambda: expiry) if expiry is not None else None
    return SimpleNamespace(detail=detail, limit=SimpleNamespace(limit=item))


def test_retry_after_uses_window_length_not_request_count():
    assert get_retry_after_seconds(_exc(expiry=60)) == 60
    assert get_retry_after_seconds(_exc(expiry=3600, detail="10 per 1 hour")) == 3600


def test_retry_after_falls_back_when_limit_unknown():
    assert get_retry_after_seconds(_exc(expiry=None)) == DEFAULT_RETRY_AFTER_SECONDS
    assert get_retry_after_seconds(SimpleNamespace(detail="custom message")) == (
        DEFAULT_RETRY_AFTER_SECONDS
    )


def test_retry_after_is_never_zero():
    assert get_retry_after_seconds(_exc(expiry=0)) == 1


def test_handler_returns_429_with_integer_retry_after():
    response = asyncio.run(rate_limit_exceeded_handler(None, _exc(expiry=60)))
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.headers["retry-after"].isdigit()
    body = json.loads(response.body)
    assert "5 per 1 minute" in body["detail"]
