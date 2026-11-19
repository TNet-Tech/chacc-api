"""
Status of the services the server depends on, for the console's Services tab.

Each check runs concurrently with a time limit, so one slow service can't hold up
the others. Statuses:

- ``ok``: working.
- ``degraded``: working with a fallback (e.g. rate limits counted in memory
  because Redis is down).
- ``down``: not working.
- ``disabled``: not set up; that's fine.

Texts are written for people: what the service is for, what is happening and what
to do. The raw error is kept in ``error`` for whoever needs it. Nothing secret is
returned: addresses are shown without passwords.
"""

import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from sqlalchemy import text

from src import database
from src.constants import (
    API_PREFIX,
    DATABASE_ENGINE,
    DATABASE_HOST,
    DATABASE_NAME,
    DATABASE_PORT,
    DEVELOPMENT_MODE,
    SQLITE_DB_PATH,
)
from src.health import get_version
from src.lifecycle import restart_supported
from src.logger import configure_logging, get_default_log_level
from src.rate_limiter import storage_status
from src.redis_service import RedisService

chacc_logger = configure_logging(log_level=get_default_log_level())

CHECK_TIMEOUT_SECONDS = 2.0
_SEVERITY = {"ok": 0, "disabled": 0, "degraded": 1, "down": 2}

DESCRIPTIONS = {
    "database": "Stores modules, users and everything else the server saves.",
    "redis": "Optional. A fast shared store: lets several servers share rate-limit "
    "counts, and modules can use it.",
    "rate_limit": "Stops clients from calling limited routes too often.",
    "server": "The ChaCC API itself.",
}


def _service(
    sid,
    name,
    status,
    details=(),
    *,
    message=None,
    hint=None,
    error=None,
    latency_ms=None,
):
    shown = list(details)
    if latency_ms is not None:
        shown.append(("Response", f"{latency_ms} ms"))
    return {
        "id": sid,
        "name": name,
        "status": status,
        "description": DESCRIPTIONS.get(sid, ""),
        "message": message,
        "hint": hint,
        "error": error,
        "details": [{"label": label, "value": value} for label, value in shown if value],
        "latency_ms": latency_ms,
    }


async def _timed(check: Callable[[], Awaitable], timeout: float = CHECK_TIMEOUT_SECONDS):
    """Run ``check()`` with a time limit; returns (result, milliseconds)."""
    started = time.perf_counter()
    result = await asyncio.wait_for(check(), timeout)
    return result, round((time.perf_counter() - started) * 1000)


def _first_line(error: object) -> str:
    return (str(error) or type(error).__name__).strip().split("\n")[0]


def explain_error(error: str, where: str) -> str:
    """A plain-language reason for a connection error."""
    low = error.lower()
    if "refused" in low or "error 111" in low or "connect call failed" in low:
        return f"Nothing is answering at {where}."
    if "no answer within" in low or "timed out" in low or "timeout" in low:
        return f"{where} didn't answer in time."
    if (
        "name or service not known" in low
        or "nodename nor servname" in low
        or "temporary failure in name resolution" in low
        or "could not translate host name" in low
    ):
        return f"The address {where} can't be found."
    if (
        "password" in low
        or "noauth" in low
        or "wrongpass" in low
        or "authentication" in low
        or "access denied" in low
    ):
        return "Wrong user name or password."
    if "does not exist" in low and "database" in low:
        return "The database doesn't exist."
    if "unable to open database file" in low or "permission denied" in low:
        return "The database file can't be opened."
    return f"Can't connect to {where}."


def _host_port(host: str, port: object) -> str:
    return f"{host}:{port}"


# ---------- database ----------


def _is_postgres() -> bool:
    return "postgres" in DATABASE_ENGINE


def _database_where() -> str:
    return f"{DATABASE_HOST}:{DATABASE_PORT}" if _is_postgres() else SQLITE_DB_PATH


def _database_location_details() -> list:
    if _is_postgres():
        return [("Server", _host_port(DATABASE_HOST, DATABASE_PORT)), ("Database", DATABASE_NAME)]
    return [("File", SQLITE_DB_PATH)]


async def _database_version() -> str:
    async with database.async_session() as db:
        if database.async_engine.dialect.name == "postgresql":
            version = (await db.execute(text("SHOW server_version"))).scalar()
            return f"PostgreSQL {str(version).split()[0]}"
        version = (await db.execute(text("SELECT sqlite_version()"))).scalar()
        return f"SQLite {version}"


async def database_status() -> dict:
    kind = "PostgreSQL" if _is_postgres() else "SQLite"
    try:
        version, ms = await _timed(_database_version)
    except Exception as e:  # noqa: BLE001 - includes TimeoutError
        error = (
            f"no answer within {CHECK_TIMEOUT_SECONDS:g} s"
            if isinstance(e, TimeoutError)
            else _first_line(e)
        )
        return _service(
            "database",
            "Database",
            "down",
            [("Type", kind), *_database_location_details()],
            message=explain_error(error, _database_where()),
            hint="Check the DATABASE_* settings in .env."
            if _is_postgres()
            else "Check that the folder exists and is writable.",
            error=error,
        )
    return _service(
        "database",
        "Database",
        "ok",
        [("Type", version), *_database_location_details()],
        latency_ms=ms,
    )


# ---------- redis ----------


def _memory(value: str | None) -> str | None:
    """'1.06M' -> '1.06 MB'."""
    if not value:
        return None
    units = {"B": "bytes", "K": "KB", "M": "MB", "G": "GB", "T": "TB"}
    number, unit = value[:-1], value[-1:].upper()
    return f"{number} {units[unit]}" if unit in units and number else value


async def redis_status(redis_service: RedisService | None) -> dict:
    service = redis_service or RedisService()
    server = _host_port(service._host, service._port)
    if not service.is_enabled:
        return _service(
            "redis",
            "Redis",
            "disabled",
            hint="Optional. Set REDIS_ENABLED=true in .env to use it.",
        )
    try:
        state, ms = await _timed(service.check)
    except TimeoutError:
        state = {"connected": False, "error": f"no answer within {CHECK_TIMEOUT_SECONDS:g} s"}
        service.mark_unreachable(state["error"])
        ms = None
    if not state["connected"]:
        error = _first_line(state.get("error") or "no connection")
        return _service(
            "redis",
            "Redis",
            "down",
            [("Server", server)],
            message=explain_error(error, server),
            hint="ChaCC keeps running and reconnects when Redis is back.",
            error=error,
        )
    return _service(
        "redis",
        "Redis",
        "ok",
        [
            ("Server", server),
            ("Version", state.get("version")),
            ("Memory", _memory(state.get("memory"))),
        ],
        latency_ms=ms,
    )


# ---------- rate limiting ----------


def _storage_server(uri: str) -> str:
    """'redis://:***@host:6379/0' -> 'host:6379' (no credentials)."""
    parts = urlsplit(uri)
    return _host_port(parts.hostname or "?", parts.port or 6379)


def _routes(count: int) -> str:
    return "None" if count == 0 else str(count)


async def rate_limit_status() -> dict:
    started = time.perf_counter()
    state = await storage_status(CHECK_TIMEOUT_SECONDS)
    ms = round((time.perf_counter() - started) * 1000)
    routes = ("Limited routes", _routes(state["limited_routes"]))
    if not state["enabled"]:
        return _service(
            "rate_limit",
            "Rate limiting",
            "disabled",
            [routes],
            hint="RATE_LIMIT_ENABLED=false: no route is limited.",
        )
    if state["storage"] == "memory":
        return _service(
            "rate_limit", "Rate limiting", "ok", [("Counted on", "This server"), routes]
        )
    where = _storage_server(state["uri"])
    if state["fallback"]:
        return _service(
            "rate_limit",
            "Rate limiting",
            "degraded",
            [("Counted on", "This server, for now"), routes],
            message=f"Redis ({where}) is unreachable, so requests are counted on this server.",
            error=state["error"],
        )
    return _service(
        "rate_limit",
        "Rate limiting",
        "ok",
        [("Counted on", f"Redis ({where})"), routes],
        latency_ms=ms,
    )


# ---------- server ----------


def server_status(started_at: float, login_required: bool) -> dict:
    if DEVELOPMENT_MODE:
        restart = "Off in development"
    elif restart_supported():
        restart = "Available"
    else:
        restart = "Unavailable"
    python = ".".join(str(v) for v in sys.version_info[:3])
    return _service(
        "server",
        "Server",
        "ok",
        [
            ("Version", f"{get_version()} · Python {python}"),
            ("API path", API_PREFIX),
            ("Login", "Required" if login_required else "Not required"),
            ("Console restart", restart),
        ],
    ) | {"started_at": started_at}


# ---------- all ----------


async def collect(redis_service, started_at: float, login_required: bool) -> dict:
    """Check every service at once."""
    results = await asyncio.gather(
        database_status(),
        redis_status(redis_service),
        rate_limit_status(),
        return_exceptions=True,
    )
    names = (("database", "Database"), ("redis", "Redis"), ("rate_limit", "Rate limiting"))
    services = []
    for (sid, name), result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            chacc_logger.warning(f"Service check '{sid}' failed: {result}")
            result = _service(
                sid,
                name,
                "down",
                message="The check failed. See the server log.",
                error=_first_line(result),
            )
        services.append(result)
    services.append(server_status(started_at, login_required))

    worst = max(services, key=lambda s: _SEVERITY[s["status"]])["status"]
    return {
        "status": "ok" if worst == "disabled" else worst,
        "checked_at": time.time(),
        "services": services,
    }
