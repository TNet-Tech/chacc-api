"""
Rate limiting for ChaCC modules.

    from chacc_api.rate_limit import rate_limit

    @router.get("/status")
    @rate_limit("10/minute")
    async def status():
        ...

``limiter`` is the server's SlowAPI limiter (the same object as ``context.limiter``),
for advanced use such as shared limits.
"""

from src.rate_limiter import limiter, rate_limit

__all__ = ["limiter", "rate_limit"]
