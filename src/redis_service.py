"""
Redis service for ChaCC backbone.
Provides Redis client to modules via context.
"""

import time

from redis.asyncio import Redis

from src.constants import REDIS_DB, REDIS_ENABLED, REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

# After a failed connection, wait this long before trying again, so callers
# don't each wait for a connect timeout while Redis is down.
RECONNECT_INTERVAL_SECONDS = 10


class RedisService:
    """
    Async Redis service for the backbone.
    Exposed to modules via BackboneContext.
    """

    def __init__(self):
        self._redis: Redis | None = None
        self._host = REDIS_HOST
        self._port = REDIS_PORT
        self._db = REDIS_DB
        self._password = REDIS_PASSWORD
        self._enabled = REDIS_ENABLED
        self._connection_attempted = False
        self._connection_error: str | None = None
        self._retry_at = 0.0

    @property
    def is_enabled(self) -> bool:
        """Check if Redis is enabled"""
        return self._enabled

    @property
    def is_connected(self) -> bool:
        """Check if Redis is currently connected"""
        return self._redis is not None and self._connection_error is None

    @property
    def connection_error(self) -> str | None:
        """Get the last connection error message if any"""
        return self._connection_error

    @property
    def address(self) -> str:
        """host:port/db, without the password."""
        return f"{self._host}:{self._port}/{self._db}"

    async def get_client(self) -> Redis | None:
        """
        Get Redis client. Returns None if Redis is disabled or can't be reached.

        If Redis was unreachable, a new connection is tried at most every
        RECONNECT_INTERVAL_SECONDS, so Redis coming back is picked up without a restart.
        """
        if not self._enabled:
            return None

        if self._redis is not None and self._connection_error is None:
            return self._redis

        if self._connection_attempted and time.monotonic() < self._retry_at:
            return None

        self._connection_attempted = True
        await self._drop_client()
        try:
            await self._probe()
            self._redis = self._new_client()
            if self._connection_error is not None:
                chacc_logger.info(f"Redis reachable again: {self.address}")
            else:
                chacc_logger.info(f"Redis connected: {self.address}")
            self._connection_error = None
        except Exception as e:  # noqa: BLE001
            self.mark_unreachable(str(e) or type(e).__name__)
            chacc_logger.debug(f"Redis not available: {e}")

        return self._redis

    async def check(self) -> dict:
        """
        Ping Redis now and report its state:
        ``{"connected": bool, "error": str | None, "version": str | None, "memory": str | None}``.
        A failed ping marks the connection as broken, so the next ``get_client()``
        reconnects; a successful one reconnects right away if it was broken.
        """
        result = {"connected": False, "error": None, "version": None, "memory": None}
        if not self._enabled:
            return result
        try:
            server, memory = await self._probe(info=True)
        except Exception as e:  # noqa: BLE001
            self.mark_unreachable(str(e) or type(e).__name__)
            result["error"] = self._connection_error
            return result
        result.update(
            connected=True,
            version=server.get("redis_version"),
            memory=memory.get("used_memory_human"),
        )
        if self._connection_error is not None or self._redis is None:
            self._retry_at = 0.0
            await self.get_client()
        return result

    def _new_client(self, retry: bool = True) -> Redis:
        options = {} if retry else {"retry": None}
        return Redis(
            host=self._host,
            port=self._port,
            db=self._db,
            password=self._password,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            **options,
        )

    async def _probe(self, info: bool = False):
        """
        Is Redis reachable? Uses a one-off connection without retries: the normal
        client retries a refused connection for several seconds, which is right for
        modules' commands but too slow for a yes/no answer.
        """
        probe = self._new_client(retry=False)
        try:
            await probe.ping()
            if info:
                return await probe.info("server"), await probe.info("memory")
            return None
        finally:
            await probe.aclose()

    def mark_unreachable(self, error: str) -> None:
        """Record that Redis didn't answer, so the next get_client() reconnects."""
        self._connection_error = error
        self._retry_at = time.monotonic() + RECONNECT_INTERVAL_SECONDS

    async def _drop_client(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as e:  # noqa: BLE001 - a broken client is dropped anyway
                chacc_logger.debug(f"Closing the old Redis client failed: {e}")
            self._redis = None

    async def close(self):
        """Close Redis connection"""
        if self._redis is not None:
            try:
                await self._redis.aclose()
                chacc_logger.info("Redis connection closed.")
            except Exception as e:  # noqa: BLE001
                chacc_logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._redis = None
                self._connection_attempted = False
                self._connection_error = None
        else:
            chacc_logger.debug("Redis was not connected. No action taken on close.")
