import os
from pathlib import Path
from importlib.resources import files
import base64

from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from chacc_api.server.docs.swagger import get_themed_swagger_ui_html
from chacc_api.server.docs.redoc import get_themed_redoc_html
from slowapi.errors import RateLimitExceeded
from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.modules import modules_router
from src.health import health_router
from src.database import get_db
from src.logger import configure_logging, get_default_log_level
from src.core_services import BackboneContext
from src.constants import (
    DEVELOPMENT_MODE,
    MODULES_LOADED_DIR,
    PLUGINS_DIR,
    CORS_ALLOWED_ORIGINS,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_METHODS,
    CORS_ALLOW_HEADERS,
)
from src.env_validator import validate_environment, ValidationError
from src.redis_service import RedisService


def _get_logo_data_uri() -> str:
    logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "chacc-icon.ico"
    if logo_path.exists():
        return "data:image/x-icon;base64," + base64.b64encode(logo_path.read_bytes()).decode()
    return ""


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
        except Exception as e:
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
        app=app, limiter=app.state.limiter, logger=chacc_logger, db_session_factory=get_db
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
    except Exception as e:
        chacc_logger.warning(f"Failed to initialize Redis service: {e}. Continuing without Redis.")

    app.state.backbone_context = backbone_context

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
    except Exception as e:
        chacc_logger.warning(f"Error during Redis shutdown: {e}")

    chacc_logger.info("Application shutting down.")


app = FastAPI(
    title="ChaCC API Backbone",
    description="Plug and Play Modular Application for extensible APIs with FastAPI.",
    version="1.0.0-b4.2",
    docs_url=None,
    redoc_url=None,
    lifespan=onStartupLifespan,
)

allowed_origins = [CORS_ALLOWED_ORIGINS] if CORS_ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=([CORS_ALLOW_METHODS] if CORS_ALLOW_METHODS != "*" else ["*"]),
    allow_headers=([CORS_ALLOW_HEADERS] if CORS_ALLOW_HEADERS != "*" else ["*"]),
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.state.loaded_modules = {}
app.state.mounted_routers = {}

app.state.backbone_context = None


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
    logo_data_uri = _get_logo_data_uri()

    logo_img = f'<img src="{logo_data_uri}" alt="ChaCC Logo" class="logo">' if logo_data_uri else ""

    template_path = Path(__file__).resolve().parent / "templates" / "index.html"
    html_content = template_path.read_text(encoding="utf-8")
    html_content = html_content.replace("{{logo_img|safe}}", logo_img)
    html_content = html_content.replace("{{logo_data_uri}}", logo_data_uri)

    return HTMLResponse(
        content=html_content,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html(request: Request):
    logo_data_uri = _get_logo_data_uri()
    return get_themed_swagger_ui_html(
        request, app_title="ChaCC API Backbone", logo_data_uri=logo_data_uri
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html(request: Request):
    logo_data_uri = _get_logo_data_uri()
    return get_themed_redoc_html(
        request, app_title="ChaCC API Backbone", logo_data_uri=logo_data_uri
    )


app.include_router(health_router)
app.include_router(modules_router)
