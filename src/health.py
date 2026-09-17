"""
ChaCC Health Check Endpoint.

Provides health and readiness checks for container orchestration:
- /api/health - Basic liveness check
- /api/health/ready - Readiness check (includes database)
"""

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import BASE_DIR, DEVELOPMENT_MODE
from src.database import get_async_db
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

health_router = APIRouter(tags=["Health"])

RESOLUTION_STATUS_FILE = os.path.join(BASE_DIR, ".dependency_resolution_status")


def _read_resolution_status() -> dict:
    """Read the dependency resolution status file written by the entrypoint."""
    try:
        if os.path.exists(RESOLUTION_STATUS_FILE):
            with open(RESOLUTION_STATUS_FILE, "r") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return {"state": "done", "message": ""}


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    mode: str
    checks: dict


class VersionResponse(BaseModel):
    """Version endpoint response model."""

    version: str
    name: str
    python_version: str


def _get_version() -> str:
    """Read the installed package version from metadata, falling back to a static string."""
    try:
        from importlib.metadata import version

        return version("chacc-api")
    except Exception:  # noqa: BLE001
        return "unknown"


@health_router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Basic liveness check.

    Returns 200 when the service is running.
    Used by Kubernetes for pod lifecycle management.
    """
    resolution = _read_resolution_status()
    resolution_state = resolution.get("state", "done")
    checks = {"api": "ok", "dependency_resolution": resolution_state}

    if resolution_state in ("running", "pending"):
        status = "starting"
    elif resolution_state == "failed":
        status = "unhealthy"
    else:
        status = "healthy"

    return HealthResponse(
        status=status,
        mode="development" if DEVELOPMENT_MODE else "production",
        checks=checks,
    )


@health_router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(db: AsyncSession = Depends(get_async_db)):
    """
    Readiness check with database connectivity.

    Returns 200 when the service is ready to accept traffic.
    Includes database connectivity check.
    """
    checks = {"api": "ok", "database": "unknown"}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError as e:
        chacc_logger.error(f"Database health check failed: {e}")
        checks["database"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    overall_status = "healthy" if all_ok else "unhealthy"

    return HealthResponse(
        status=overall_status,
        mode="development" if DEVELOPMENT_MODE else "production",
        checks=checks,
    )


@health_router.get("/health/live", response_model=HealthResponse)
async def liveness_check():
    """
    Liveness check - simplified version.

    Returns 200 if the process is running.
    No dependency checks (those are in /api/health/ready).
    """
    return HealthResponse(
        status="alive",
        mode="development" if DEVELOPMENT_MODE else "production",
        checks={"process": "running"},
    )


@health_router.get("/version", response_model=VersionResponse)
async def version_check():
    """
    Service version endpoint.

    Returns the installed package version, name, and Python version.
    UI components fetch this instead of hardcoding the version string.
    """
    import sys

    return VersionResponse(
        version=_get_version(),
        name="ChaCC API",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
