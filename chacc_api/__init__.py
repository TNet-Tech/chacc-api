"""
ChaCC API - Python SDK for ChaCC API development.

This package provides the core APIs that developers should import from
when building modules for the ChaCC API backbone.

Usage:
    from chacc_api import BackboneContext, ChaCCBaseModel, RedisService
    from chacc_api.database import get_db
"""

__all__ = [
    "BackboneContext",
    "ChaCCBaseModel",
    "ModuleRecord",
    "RedisService",
    "apply_deferred_schema_changes",
    "engine",
    "get_db",
    "initialize_database_models",
    "metadata_obj",
    "register_model",
]


_DATABASE_EXPORTS = {
    "ChaCCBaseModel",
    "ModuleRecord",
    "apply_deferred_schema_changes",
    "engine",
    "get_db",
    "initialize_database_models",
    "metadata_obj",
    "register_model",
}


def __getattr__(name: str):
    """
    Lazily load exports to keep ``import chacc_api`` lightweight.

    Database-backed exports are only imported when explicitly accessed, so
    CLI tools and other lightweight consumers can import this package without
    creating a database engine or requiring database drivers.
    """
    if name == "BackboneContext":
        from src.core_services import BackboneContext

        return BackboneContext
    if name == "RedisService":
        from src.redis_service import RedisService

        return RedisService
    if name in _DATABASE_EXPORTS:
        from src import database

        return getattr(database, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
