"""
Test settings: every run gets its own throwaway SQLite database and data folders.

ChaCC reads its settings once, when ``src.constants`` is imported, and
environment variables win over ``.env``. Setting them here, before any test
module imports ChaCC, means the tests never use the developer's ``.env``
database or installed modules, and pass the same way in CI (which has no
``.env``) as on a developer machine.
"""

import os
import secrets
import shutil
import tempfile

import pytest

_DATA = tempfile.mkdtemp(prefix="chacc-tests-")

os.environ.update(
    {
        "CHACC_DEV_MODE": "false",
        "SECRET_KEY": secrets.token_urlsafe(48),  # the validator rejects weak keys
        "DATABASE_ENGINE": "sqlite",
        "SQLITE_DATABASE_PATH": _DATA,
        "SQLITE_DATABASE_NAME": "chacc-test.db",
        "MODULES_INSTALLED_DIR": os.path.join(_DATA, "modules_installed"),
        "MODULES_LOADED_DIR": os.path.join(_DATA, "modules_loaded"),
        "MODULES_UPLOAD_DIR": os.path.join(_DATA, "modules_upload"),
        "DEPENDENCY_CACHE_DIR": os.path.join(_DATA, "cache"),
        "MODULE_PACKAGES_DIR": os.path.join(_DATA, "packages"),
        "MIGRATION_BACKUP_DIR": os.path.join(_DATA, "backups"),
        "REDIS_ENABLED": "false",
        "RATE_LIMIT_STORAGE_URI": "memory://",
        # Tests that need a web console key set it themselves.
        "CHACC_CONSOLE_KEY": "",
        "CHACC_DEPLOY_KEY": "",
    }
)


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Create the core tables, which the app otherwise creates at startup."""
    from src.database import engine, metadata_obj

    metadata_obj.create_all(engine)
    yield
    engine.dispose()
    shutil.rmtree(_DATA, ignore_errors=True)
