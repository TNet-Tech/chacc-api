"""
Database models and session helpers for ChaCC modules.

    from chacc_api.database import get_async_db, async_session, with_async_session

- In routes: ``db: AsyncSession = Depends(get_async_db)`` (or ``get_db``).
- In a block: ``async with async_session() as db:`` (or ``with session() as db:``).
- In functions and methods: ``@with_async_session`` (or ``@with_session``), which
  pass a fresh session as ``db=`` and close it afterwards.
"""

from src.database import (
    ChaCCBaseModel,
    ModuleRecord,
    apply_deferred_schema_changes,
    async_session,
    engine,
    get_async_db,
    get_db,
    initialize_database_models,
    metadata_obj,
    register_model,
    session,
    with_async_session,
    with_session,
)

__all__ = [
    "ChaCCBaseModel",
    "ModuleRecord",
    "apply_deferred_schema_changes",
    "async_session",
    "engine",
    "get_async_db",
    "get_db",
    "initialize_database_models",
    "metadata_obj",
    "register_model",
    "session",
    "with_async_session",
    "with_session",
]
