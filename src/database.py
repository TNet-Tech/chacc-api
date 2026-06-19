import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Integer,
    String,
    create_engine,
    DateTime,
    ForeignKey,
    func,
    MetaData,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.types import TypeDecorator

from .constants import DATABASE_ENGINE, DATABASE_URL
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
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_model_registry: set = set()
_core_system_models: set = set()

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata_obj = MetaData(naming_convention=convention)


def register_model(cls):
    if cls not in _model_registry:
        _model_registry.add(cls)
    return cls


@as_declarative(metadata=metadata_obj)
class ChaCCBaseModel:
    """
    ChaCCBaseModel: Base model for ChaCC API with UUID, timestamps and soft delete support.
    """

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    id = Column(Integer, primary_key=True)
    uuid = Column(GUID, default=uuid7, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True, index=True)


@event.listens_for(ChaCCBaseModel, "before_insert", propagate=True)
@event.listens_for(ChaCCBaseModel, "before_update", propagate=True)
def _set_timestamps(mapper, connection, target):
    now = datetime.now()
    if not getattr(target, "created_at", None):
        target.created_at = now
    target.updated_at = now


@register_model
class ModuleRecord(ChaCCBaseModel):
    __tablename__ = "modules"
    name = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    version = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    base_path_prefix = Column(String, unique=True, nullable=True)
    meta_data = Column(JSON, nullable=True)


_core_system_models.add(ModuleRecord)


def initialize_database_models(backbone_context):
    enable_audit_fields = backbone_context.get_service("enable_audit_fields")

    for model_cls in _model_registry:
        if model_cls in _core_system_models:
            continue

        if enable_audit_fields and enable_audit_fields():
            if not hasattr(model_cls, "created_by_id"):
                backbone_context.logger.info(f"Adding audit user fields to {model_cls.__name__}.")
                created_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
                updated_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
                deleted_by_col = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
                setattr(model_cls, "created_by_id", created_by_col)
                setattr(model_cls, "updated_by_id", updated_by_col)
                setattr(model_cls, "deleted_by_id", deleted_by_col)
                table = model_cls.__table__
                table.append_column(created_by_col)
                table.append_column(updated_by_col)
                table.append_column(deleted_by_col)


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
