import uuid
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Integer,
    String,
    create_engine,
    ForeignKey,
    DateTime,
    func,
    MetaData,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import as_declarative, declared_attr

from .constants import DATABASE_ENGINE, DATABASE_URL
from .logger import LogLevels, configure_logging
from .core_services import BackboneContext

chacc_logger = configure_logging(log_level=LogLevels.INFO)

if DATABASE_ENGINE == "postgresql":
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_model_registry = set()
_core_system_models = set()

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
    ChaccBaseModel:

    """

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)


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


def initialize_database_models(backbone_context: BackboneContext):
    enable_audit_fields = backbone_context.get_service("enable_audit_fields")

    for model_cls in _model_registry:
        if model_cls in _core_system_models:
            continue

        if enable_audit_fields and enable_audit_fields():
            if not hasattr(model_cls, "created_at"):
                backbone_context.logger.info(f"Adding audit fields to {model_cls.__name__}.")
                created_at_col = Column(DateTime, server_default=func.now(), nullable=False)
                updated_at_col = Column(
                    DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
                )
                deleted_at_col = Column(DateTime, nullable=True, index=True)
                created_by_id_col = Column(
                    Integer, ForeignKey("users.id"), nullable=True, index=True
                )
                updated_by_id_col = Column(
                    Integer, ForeignKey("users.id"), nullable=True, index=True
                )
                deleted_by_id_col = Column(
                    Integer, ForeignKey("users.id"), nullable=True, index=True
                )
                setattr(model_cls, "created_at", created_at_col)
                setattr(model_cls, "updated_at", updated_at_col)
                setattr(model_cls, "deleted_at", deleted_at_col)
                setattr(model_cls, "created_by_id", created_by_id_col)
                setattr(model_cls, "updated_by_id", updated_by_id_col)
                setattr(model_cls, "deleted_by_id", deleted_by_id_col)
                table = model_cls.__table__
                table.append_column(created_at_col)
                table.append_column(updated_at_col)
                table.append_column(deleted_at_col)
                table.append_column(created_by_id_col)
                table.append_column(updated_by_id_col)
                table.append_column(deleted_by_id_col)


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
