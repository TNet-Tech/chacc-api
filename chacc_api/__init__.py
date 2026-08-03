"""
ChaCC API - Python SDK for ChaCC API development.

This package provides the core APIs that developers should import from
when building modules for the ChaCC API backbone.

Usage:
    from chacc_api import BackboneContext, ChaCCBaseModel, RedisService
    from chacc_api.database import get_db
"""

from src.core_services import BackboneContext
from src.database import (
    ChaCCBaseModel,
    ModuleRecord,
    apply_deferred_schema_changes,
    engine,
    get_db,
    initialize_database_models,
    metadata_obj,
    register_model,
)
from src.redis_service import RedisService

__all__ = [
    # Core
    "BackboneContext",
    # Database
    "ChaCCBaseModel",
    "get_db",
    "ModuleRecord",
    "initialize_database_models",
    "apply_deferred_schema_changes",
    "metadata_obj",
    "engine",
    "register_model",
    # Services
    "RedisService",
]
