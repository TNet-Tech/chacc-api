import os

from decouple import config

BASE_DIR = os.getcwd()


def _normalize_prefix(value: str | None) -> str:
    """Return '' or '/segment[/segment]' (leading slash, no trailing slash)."""
    value = (value or "").strip().strip("/")
    return f"/{value}" if value else ""


# Prefix under which core and module routes are mounted. Empty string = no prefix.
API_PREFIX = _normalize_prefix(config("API_PREFIX", default="/api", cast=str))

MODULES_INSTALLED_DIR = os.path.join(
    BASE_DIR, config("MODULES_INSTALLED_DIR", default=".modules_installed", cast=str)
)
MODULES_LOADED_DIR = os.path.join(
    BASE_DIR, config("MODULES_LOADED_DIR", default=".modules_loaded", cast=str)
)
MODULES_UPLOAD_DIR = os.path.join(
    BASE_DIR, config("MODULES_UPLOAD_DIR", default=".modules_upload", cast=str)
)
# Maximum size (bytes) of an uploaded .chacc module package. Default: 10 MB.
MAX_MODULE_UPLOAD_SIZE = config("MAX_MODULE_UPLOAD_SIZE", default=10 * 1024 * 1024, cast=int)
# Maximum total uncompressed size (bytes) of a module archive (zip-bomb guard). Default: 100 MB.
MAX_MODULE_UNCOMPRESSED_SIZE = config(
    "MAX_MODULE_UNCOMPRESSED_SIZE", default=100 * 1024 * 1024, cast=int
)
# Chunk size (bytes) used when streaming uploads to disk.
MODULE_UPLOAD_CHUNK_SIZE = 1024 * 1024
PLUGINS_DIR = os.path.join(BASE_DIR, config("PLUGINS_DIR", default="plugins", cast=str))
DEPENDENCY_CACHE_DIR = os.path.join(
    BASE_DIR, config("DEPENDENCY_CACHE_DIR", default=".chacc_cache", cast=str)
)
BACKBONE_REQUIREMENTS_LOCK_FILE = f"{DEPENDENCY_CACHE_DIR}/compiled_requirements.lock"
DEPENDENCY_CACHE_FILE = f"{DEPENDENCY_CACHE_DIR}/dependency_cache.json"
# Production: Python packages that modules need are installed here (a volume in Docker),
# so they survive restarts and recreated containers. Core packages always take precedence.
MODULE_PACKAGES_DIR = os.path.join(
    BASE_DIR, config("MODULE_PACKAGES_DIR", default=".chacc_packages", cast=str)
)
# What boot may do about module packages that are missing:
#   "missing" - one quick attempt to resolve/install only what is missing (needs network)
#   "never"   - never call pip at boot; modules with missing packages are not loaded
CHACC_BOOT_INSTALL = config("CHACC_BOOT_INSTALL", default="missing", cast=str).strip().lower()
# Upper bound (seconds) for each boot-time resolve or install attempt.
CHACC_BOOT_INSTALL_TIMEOUT = config("CHACC_BOOT_INSTALL_TIMEOUT", default=120, cast=int)

MIGRATION_MODE = config("MIGRATION_MODE", default="auto", cast=str)
MIGRATION_BACKUP = config("MIGRATION_BACKUP", default=False, cast=bool)
MIGRATION_BACKUP_DIR = os.path.join(
    BASE_DIR, config("MIGRATION_BACKUP_DIR", default="backups", cast=str)
)
MIGRATION_AUTO_DROP = config("MIGRATION_AUTO_DROP", default=False, cast=bool)

DEVELOPMENT_MODE = config("CHACC_DEV_MODE", default=False, cast=bool)
ENABLE_PLUGIN_HOT_RELOAD = config("ENABLE_PLUGIN_HOT_RELOAD", default=False, cast=bool)
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION = config(
    "ENABLE_PLUGIN_DEPENDENCY_RESOLUTION", default=False, cast=bool
)
PLUGIN_AUTO_DISCOVERY = config("PLUGIN_AUTO_DISCOVERY", default=False, cast=bool)

REDIS_ENABLED = config("REDIS_ENABLED", default=False, cast=bool)
REDIS_HOST = config("REDIS_HOST", default="localhost", cast=str)
REDIS_PORT = config("REDIS_PORT", default=6379, cast=int)
REDIS_DB = config("REDIS_DB", default=0, cast=int)
REDIS_PASSWORD = config("REDIS_PASSWORD", default=None, cast=str)

RATE_LIMIT_ENABLED = config("RATE_LIMIT_ENABLED", default=True, cast=bool)
# Where request counts are kept: "memory://" (per process, reset on restart) or
# "redis://[:password@]host:port/db" (shared by all processes, survives restarts).
RATE_LIMIT_STORAGE_URI = config("RATE_LIMIT_STORAGE_URI", default="memory://", cast=str)

DATABASE_ENGINE = config("DATABASE_ENGINE", default="sqlite", cast=str)
DATABASE_NAME = config("DATABASE_NAME", default="chaccapidb")
DATABASE_USER = config("DATABASE_USER", default="chacc")
DATABASE_PASSWORD = config("DATABASE_PASSWORD", default="")
DATABASE_HOST = config("DATABASE_HOST", default="localhost")
DATABASE_PORT = config("DATABASE_PORT", default="5432", cast=int)

SQLITE_DATABASE_NAME = config("SQLITE_DATABASE_NAME", default="chaccapi.db", cast=str)
SQLITE_DATABASE_PATH = config("SQLITE_DATABASE_PATH", default=BASE_DIR, cast=str)
SQLITE_DB_PATH = os.path.abspath(os.path.join(SQLITE_DATABASE_PATH, SQLITE_DATABASE_NAME))

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="*", cast=str)
CORS_ALLOW_CREDENTIALS = config("CORS_ALLOW_CREDENTIALS", default=True, cast=bool)
CORS_ALLOW_METHODS = config("CORS_ALLOW_METHODS", default="*", cast=str)
CORS_ALLOW_HEADERS = config("CORS_ALLOW_HEADERS", default="*", cast=str)

SECRET_KEY = config("SECRET_KEY", default="", cast=str)

# Privilege for the web console and the core /modules and /system routes, when
# the authentication module is loaded. Checked and registered in src/admin_access.py.
ADMIN_PRIVILEGE_SETTING = config("CHACC_ADMIN_PRIVILEGE", default="", cast=str)

# Key for the web console and the core routes when the authentication module
# isn't loaded. Empty: they are open (with a warning). See src/admin_access.py.
CONSOLE_KEY = config("CHACC_CONSOLE_KEY", default="", cast=str)

if "postgres" in DATABASE_ENGINE.lower():
    DATABASE_URL = f"postgresql+psycopg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    ASYNC_DATABASE_URL = f"postgresql+psycopg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
else:
    normalized_path = SQLITE_DB_PATH.replace("\\", "/")
    DATABASE_URL = f"sqlite:///{normalized_path}"
    ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{normalized_path}"


LOGGER_NAME = "CHACC-API"

# The format strings are modified to wrap only `%(levelname)s` with color tags.
# This ensures that only the level name is colored, and the rest remains in the
# default terminal color.
LOG_FORMAT_DEFAULT = "%(log_color)s%(levelname)s%(reset)s:     %(asctime)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(log_color)s%(levelname)s%(reset)s %(asctime)s - %(name)s - %(message)s"


os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)
os.makedirs(DEPENDENCY_CACHE_DIR, exist_ok=True)
os.makedirs(MODULE_PACKAGES_DIR, exist_ok=True)
os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs(MIGRATION_BACKUP_DIR, exist_ok=True)
