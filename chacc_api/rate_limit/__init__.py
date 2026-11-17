"""
Rate limiting for ChaCC modules.

    from chacc_api.rate_limit import rate_limit, shared_rate_limit, check_rate_limit

    @router.get("/status")
    @rate_limit("10/minute")
    async def status():
        ...

- ``rate_limit``: limit one route.
- ``shared_rate_limit``: one limit for several routes together.
- ``check_rate_limit``: count something that isn't a route, such as login attempts.
- ``limiter``: the server's SlowAPI limiter, for anything else.
"""

from src.rate_limiter import check_rate_limit, limiter, rate_limit, shared_rate_limit

__all__ = ["check_rate_limit", "limiter", "rate_limit", "shared_rate_limit"]
