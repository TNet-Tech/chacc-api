"""
ChaCC API - Python SDK for ChaCC API development.

This package provides the core APIs that developers should import from
when building modules for the ChaCC API backbone.

Usage:
    from chacc_api import BackboneContext, ChaCCBaseModel, RedisService
    from chacc_api.database import register_model, get_db
"""

from src.core_services import BackboneContext

from src.database import (
    ChaCCBaseModel,
    register_model,
    get_db,
    ModuleRecord,
    initialize_database_models,
    metadata_obj,
    engine,
)
from src.redis_service import RedisService

__all__ = [
    # Core
    "BackboneContext",
    # Database
    "ChaCCBaseModel",
    "register_model",
    "get_db",
    "ModuleRecord",
    "initialize_database_models",
    "metadata_obj",
    "engine",
    # Services
    "RedisService",
]
