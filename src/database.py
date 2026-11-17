import functools
import inspect
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    create_engine,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .constants import ASYNC_DATABASE_URL, DATABASE_ENGINE, DATABASE_URL
from .logger import configure_logging, get_default_log_level

try:
    from uuid import uuid7
except ImportError:
    from uuid_utils import uuid7

chacc_logger = configure_logging(log_level=get_default_log_level())


class GUID(TypeDecorator):
    """
    Cross-database compatible UUID type.

    Uses native UUID on PostgreSQL, String(36) on SQLite and other databases.
    This prevents Alembic from detecting false-positive type changes.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if "postgres" in dialect.name:
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


if "postgres" in DATABASE_ENGINE:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    async_engine = create_async_engine(ASYNC_DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True
    )
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata_obj = MetaData(naming_convention=convention)


@as_declarative(metadata=metadata_obj)
class ChaCCBaseModel:
    """
    ChaCCBaseModel: Base model for ChaCC API with UUID, timestamps and soft delete support.
    """

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    uuid = Column(GUID, default=uuid7, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True, index=True)


@event.listens_for(ChaCCBaseModel, "before_insert", propagate=True)
@event.listens_for(ChaCCBaseModel, "before_update", propagate=True)
def _set_timestamps(mapper, connection, target):
    now = datetime.now(timezone.utc)
    if not getattr(target, "created_at", None):
        target.created_at = now
    target.updated_at = now


class ModuleRecord(ChaCCBaseModel):
    _is_core = True
    __tablename__ = "modules"
    name = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    version = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    base_path_prefix = Column(String, unique=True, nullable=True)
    meta_data = Column(JSON, nullable=True)


def register_model(model_cls):
    """
    Idempotent metadata guard for model registration.

    Sole work: check ``metadata_obj.tables`` for the model's table key.
    - If present: return ``model_cls`` unchanged (skip duplicate registration).
    - If missing: return ``model_cls`` unchanged and let the declarative
      base handle registration.
    """
    table_key = getattr(model_cls, "__tablename__", None)
    if table_key and table_key in metadata_obj.tables:
        return model_cls
    return model_cls


def initialize_database_models(backbone_context):
    enable_audit_fields = backbone_context.get_service("enable_audit_fields")

    if not enable_audit_fields or not enable_audit_fields():
        backbone_context.logger.warning(
            "Audit fields not enabled or service unavailable; skipping audit schema pass."
        )
        return

    for model_cls in _all_declarative_subclasses(ChaCCBaseModel):
        if getattr(model_cls, "_is_core", False):
            continue

        if not hasattr(model_cls, "created_by_id"):
            backbone_context.logger.info(f"Adding audit user fields to {model_cls.__name__}.")
            created_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            updated_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            deleted_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            model_cls.created_by_id = created_by_col
            model_cls.updated_by_id = updated_by_col
            model_cls.deleted_by_id = deleted_by_col
            table = model_cls.__table__
            table.append_column(created_by_col)
            table.append_column(updated_by_col)
            table.append_column(deleted_by_col)


def apply_deferred_schema_changes(backbone_context):
    """
    Idempotent post-entrypoint schema pass.

    Returns True if metadata_obj was mutated and a targeted migration is required.
    """
    enable_audit_fields = backbone_context.get_service("enable_audit_fields")

    if not enable_audit_fields or not enable_audit_fields():
        backbone_context.logger.debug(
            "Deferred schema pass: audit fields not enabled; nothing to do."
        )
        return False

    mutated = False
    for model_cls in _all_declarative_subclasses(ChaCCBaseModel):
        if getattr(model_cls, "_is_core", False):
            continue

        if not hasattr(model_cls, "created_by_id"):
            backbone_context.logger.info(
                f"Deferred schema pass: adding audit fields to {model_cls.__name__}."
            )
            created_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            updated_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            deleted_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
            model_cls.created_by_id = created_by_col
            model_cls.updated_by_id = updated_by_col
            model_cls.deleted_by_id = deleted_by_col
            table = model_cls.__table__
            table.append_column(created_by_col)
            table.append_column(updated_by_col)
            table.append_column(deleted_by_col)
            mutated = True

    return mutated


def _all_declarative_subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _all_declarative_subclasses(subclass)


@asynccontextmanager
async def async_session() -> AsyncGenerator[AsyncSession]:
    """
    An async session, closed when the block ends (rolled back first on errors):

        async with async_session() as db:
            items = (await db.execute(select(Item))).scalars().all()

    Do all the work inside the block and don't return the session.
    """
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception:
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            chacc_logger.warning("Database Session rollback failed!")
        raise
    finally:
        try:
            await db.close()
        except Exception as e:  # noqa: BLE001
            chacc_logger.warning(f"CLOSE FAILED: {e}")


@contextmanager
def session() -> Generator[Session]:
    """
    A synchronous session, closed when the block ends (rolled back first on errors):

        with session() as db:
            items = db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def get_db():
    """Route dependency: ``db: Session = Depends(get_db)``. FastAPI closes it."""
    with session() as db:
        yield db


async def get_async_db():
    """Route dependency: ``db: AsyncSession = Depends(get_async_db)``. FastAPI closes it."""
    async with async_session() as db:
        yield db


def with_async_session(func):
    """
    Give an async function or method its own async session as ``db``, closed when
    it returns or raises. Callers don't pass a session:

        class ItemService:
            @with_async_session
            async def names(self, *, db):
                return [i.name for i in (await db.execute(select(Item))).scalars()]

        await ItemService().names()

    Pass ``db=`` to reuse a session you already have (for example to run several
    calls in one transaction); that session is then left open.
    """
    if not inspect.iscoroutinefunction(func):
        raise TypeError("@with_async_session needs an async function; use @with_session.")

    @functools.wraps(func)
    async def wrapper(*args, db=None, **kwargs):
        if db is not None:
            return await func(*args, db=db, **kwargs)
        async with async_session() as new_db:
            return await func(*args, db=new_db, **kwargs)

    return wrapper


def with_session(func):
    """
    Same as ``with_async_session`` for the synchronous session. Works on both
    sync and async functions.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, db=None, **kwargs):
            if db is not None:
                return await func(*args, db=db, **kwargs)
            with session() as new_db:
                return await func(*args, db=new_db, **kwargs)

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, db=None, **kwargs):
        if db is not None:
            return func(*args, db=db, **kwargs)
        with session() as new_db:
            return func(*args, db=new_db, **kwargs)

    return wrapper
