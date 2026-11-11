import os
from builtins import Exception
from functools import lru_cache
from html import escape
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from chacc_api.server.docs.redoc import get_themed_redoc_html
from chacc_api.server.docs.swagger import get_themed_swagger_ui_html, patch_binary_file_schema
from src.constants import (
    API_PREFIX,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ALLOWED_ORIGINS,
    DEVELOPMENT_MODE,
    MODULES_LOADED_DIR,
    PLUGINS_DIR,
)
from src.core_services import BackboneContext
from src.csv_utils import parse_csv
from src.database import get_async_db, get_db
from src.env_validator import ValidationError, validate_environment
from src.health import get_version, health_router
from src.logger import configure_logging, get_default_log_level
from src.migration.runner import run_migration
from src.modules import ModuleUploadSizeLimitMiddleware, modules_router
from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.redis_service import RedisService
from src.system import server_info, system_router


def copy_sample_env():
    """Copy .env.sample from package to current working directory if .env.sample doesn't exist."""
    if not os.path.exists(".env.sample"):
        try:
            sample_env = files("chacc_api").joinpath(".env.sample")
            if sample_env.is_file():
                env_content = sample_env.read_text(encoding="utf-8")
                with open(".env.sample", "w", encoding="utf-8") as f:
                    f.write(env_content)
                chacc_logger.info("Created .env.sample from .env.sample for reference")
            else:
                chacc_logger.warning("Could not find .env.sample in package")
        except (OSError, KeyError) as e:
            chacc_logger.warning(f"Failed to copy .env.sample: {e}")


chacc_logger = configure_logging(log_level=get_default_log_level())


@asynccontextmanager
async def onStartupLifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    """
    chacc_logger.info("Application startup initiated...")

    redis_service = RedisService()

    try:
        validate_environment()
    except ValidationError as e:
        chacc_logger.critical(f"Environment validation failed: {e}")
        raise RuntimeError(f"Cannot start application: {e}")

    backbone_context = BackboneContext(
        app=app,
        limiter=app.state.limiter,
        logger=chacc_logger,
        db_session_factory=get_db,
        async_db_session_factory=get_async_db,
    )

    try:
        redis_client = await redis_service.get_client()
        if redis_client:
            backbone_context.register_service("redis", redis_service)
            chacc_logger.info("Redis service registered in backbone context.")
        elif redis_service.connection_error:
            chacc_logger.warning(
                f"Redis connection failed: {redis_service.connection_error}. Continuing without Redis."
            )
        else:
            chacc_logger.info("Redis is disabled. Continuing without Redis.")
    except Exception as e:  # noqa: BLE001
        chacc_logger.warning(f"Failed to initialize Redis service: {e}. Continuing without Redis.")

    app.state.backbone_context = backbone_context

    await run_migration()

    chacc_logger.info("Loading modules...")

    if DEVELOPMENT_MODE:
        chacc_logger.info("=" * 65)
        chacc_logger.info(f"DEVELOPMENT MODE: Loading plugins from {PLUGINS_DIR} directory")
        chacc_logger.info("=" * 65)
        from src.plugin_loader import load_dev_modules

        await load_dev_modules(app, backbone_context)
    else:
        from src.module_loader.loader import load_modules

        chacc_logger.info("=" * 65)
        chacc_logger.info(f"PRODUCTION MODE: Loading modules from {MODULES_LOADED_DIR} directory")
        chacc_logger.info("=" * 65)
        await load_modules(app, backbone_context)

    # Copy .env.sample to .env if .env doesn't exist
    copy_sample_env()

    yield

    try:
        redis_service = backbone_context.get_service("redis")
        if redis_service and redis_service.is_connected:
            await redis_service.close()
            chacc_logger.info("Redis connection closed gracefully.")
        else:
            chacc_logger.debug("Redis service not available or not connected. Skipping cleanup.")
    except Exception as e:  # noqa: BLE001
        chacc_logger.warning(f"Error during Redis shutdown: {e}")

    chacc_logger.info("Application shutting down.")


app = FastAPI(
    title="ChaCC API Backbone",
    description="Plug and Play Modular Application for extensible APIs with FastAPI.",
    version=get_version(),
    docs_url=None,
    redoc_url=None,
    lifespan=onStartupLifespan,
)
patch_binary_file_schema(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_csv(CORS_ALLOWED_ORIGINS),
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=parse_csv(CORS_ALLOW_METHODS),
    allow_headers=parse_csv(CORS_ALLOW_HEADERS),
)

app.add_middleware(ModuleUploadSizeLimitMiddleware, path_prefix=API_PREFIX)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.state.loaded_modules = {}
app.state.mounted_routers = {}

app.state.backbone_context = None

static_dir = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get(
    "/",
    summary="Root Endpoint",
    description="Welcome endpoint for the ChaCC API Backbone",
    response_description="Welcome page with links to interactive API documentation",
    tags=["Core"],
)
async def read_root():
    """
    Root endpoint of the ChaCC API backbone.
    Returns a welcome page with links to interactive API documentation.
    """
    return HTMLResponse(
        _render_index(),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/console", include_in_schema=False)
async def module_console():
    """Web console: manage modules, view the dependency graph, restart the server."""
    return HTMLResponse(
        _render_template("console.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


def _render_index() -> str:
    return _render_template("index.html")


def _render_template(name: str) -> str:
    # In dev mode, read the template on every request so edits show up without
    # a restart (uvicorn only reloads on .py changes).
    if DEVELOPMENT_MODE:
        return _read_template(name)
    return _cached_template(name)


def _read_template(name: str) -> str:
    html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    return html.replace("{{API_PREFIX}}", escape(API_PREFIX, quote=True))


_cached_template = lru_cache(maxsize=4)(_read_template)


def _login_paths(app_: FastAPI) -> list[str]:
    """
    POST ``.../login`` paths of the loaded modules.

    Read from the OpenAPI schema: newer FastAPI versions keep included routers
    nested, so module routes do not show up in ``app.routes``.
    """
    try:
        paths = app_.openapi().get("paths", {})
    except Exception:  # noqa: BLE001 - a broken schema must not break discovery
        chacc_logger.warning("Could not build the OpenAPI schema to find the login route.")
        return []
    return [path for path, ops in paths.items() if path.endswith("/login") and "post" in ops]


def _auth_info(request: Request) -> dict:
    """Whether core routes need a login, and where to log in."""
    context = getattr(request.app.state, "backbone_context", None)
    enabled = bool(context and context.get_service("get_current_user"))
    login_path = None
    if enabled:
        logins = _login_paths(request.app)
        preferred = f"{API_PREFIX}/authentication/login"
        login_path = preferred if preferred in logins else (logins[0] if logins else None)
    return {"required": enabled, "login_path": login_path}


@app.get("/.well-known/chacc", include_in_schema=False)
async def chacc_discovery(request: Request):
    """
    Unprefixed discovery endpoint so clients (e.g. ``chacc deploy``) can learn
    the API prefix this server uses without guessing.
    """
    return {
        "api_prefix": API_PREFIX,
        "version": get_version(),
        "mode": "development" if DEVELOPMENT_MODE else "production",
        "auth": _auth_info(request),
        **server_info(),
    }


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    return get_themed_swagger_ui_html(request, app_title="ChaCC API Backbone")


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html(request: Request):
    return get_themed_redoc_html(request, app_title="ChaCC API Backbone")


app.include_router(health_router, prefix=API_PREFIX)
app.include_router(modules_router, prefix=API_PREFIX)
app.include_router(system_router, prefix=API_PREFIX)
