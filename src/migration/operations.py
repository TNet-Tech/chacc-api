"""
Migration operation execution.

Each operation has a handler that returns True when the schema now matches the
models, and False when the operation was skipped. Only the first kind is
written to the migration log, so the log shows what really happened.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.schema import CreateTable
from sqlalchemy.types import Enum as SAEnum

from src import sqlite_foreign_keys
from src.logger import configure_logging, get_default_log_level
from src.migration.dependencies import MigrationDependencyResolver
from src.migration.tracker import TRACKER_TABLE

chacc_logger = configure_logging(log_level=get_default_log_level())

Handler = Callable[[Operations, tuple], bool]


class MigrationOperationExecutor:
    def __init__(
        self,
        engine,
        is_postgres: bool,
        dependency_resolver: MigrationDependencyResolver,
        logger=None,
    ):
        self.engine = engine
        self.is_postgres = is_postgres
        self.dependency_resolver = dependency_resolver
        self.logger = logger or chacc_logger
        self._handlers: dict[str, Handler] = {
            "add_table": self._add_table,
            "drop_table": self._drop_table,
            "add_column": self._add_column,
            "drop_column": self._drop_column,
            "modify_type": self._modify_type,
            "modify_nullable": self._modify_nullable,
            "modify_default": self._modify_default,
            "add_index": self._add_index,
            "drop_index": self._drop_index,
            "add_constraint": self._add_constraint,
            "drop_constraint": self._drop_constraint,
            "create_foreign_key": self._create_foreign_key,
            "drop_foreign_key": self._drop_foreign_key,
            "create_enum": self._create_enum,
            "drop_enum": self._drop_enum,
            "sync_enum_values": self._sync_enum_values,
        }

    # ------------------------------------------------------------------ running

    def apply_single_migration(
        self,
        version: str,
        details: tuple,
        op_type: str,
        checksum: str | None = None,
        applied_migrations: list[dict] | None = None,
    ):
        checksum = checksum or self.dependency_resolver.generate_checksum([details])

        def sync_apply():
            # SQLite rebuilds tables to change them; foreign key enforcement
            # would delete or reject child rows while a parent is rebuilt.
            with (
                self.engine.connect() as conn,
                sqlite_foreign_keys.suspended(conn),
                conn.begin(),
            ):
                op = Operations(MigrationContext.configure(conn))
                try:
                    applied = self.apply_operation(op, op_type, details)
                except (ProgrammingError, OperationalError) as e:
                    if self._resolved_enum_conflict(op_type, details, e):
                        self._record(conn, version, op_type, details, checksum)
                        return
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg:
                        self.logger.debug(f"Skipping {op_type}: resource already exists")
                        return
                    self.logger.error(f"Failed to apply {op_type}: {e}")
                    raise RuntimeError(f"Migration failed while applying {op_type}: {e}") from e

                if not applied:
                    self.logger.info(f"Not applied, not recorded: {version}")
                    return

                description = self._record(conn, version, op_type, details, checksum)

            if applied_migrations is not None:
                applied_migrations.append(
                    {"version": version, "operation": op_type, "details": details}
                )
            self.logger.info(f"Applied migration: {version} - {description}")

        return sync_apply

    def apply_operation(self, op: Operations, op_type: str, details: tuple) -> bool:
        """Apply one operation. True if the schema now matches, False if skipped."""
        handler = self._handlers.get(op_type)
        if handler is None:
            self.logger.warning(f"Unknown operation type: {op_type}")
            return False
        return handler(op, details)

    def _resolved_enum_conflict(self, op_type: str, details: tuple, error: Exception) -> bool:
        """On PostgreSQL, a table can exist although creating its enum type failed."""
        if not (
            self.is_postgres and op_type == "add_table" and "duplicateobject" in str(error).lower()
        ):
            return False
        table = details[1] if len(details) > 1 else None
        if table is None or not self.dependency_resolver.table_exists(
            getattr(table, "schema", None), table.name
        ):
            return False
        self.logger.info(f"Table '{table.name}' already exists (enum type conflict resolved)")
        return True

    def _record(self, conn, version: str, op_type: str, details: tuple, checksum: str) -> str:
        table_name = self.dependency_resolver.get_table_name_from_details(op_type, details)
        description = self.generate_migration_description(op_type, table_name)
        conn.execute(
            text(f"""
            INSERT INTO {TRACKER_TABLE}
            (version_num, description, checksum, applied_at, rollback_available)
            VALUES (:version, :desc, :checksum, :applied_at, :rollback)
        """),
            {
                "version": version,
                "desc": description[:200],
                "checksum": checksum,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "rollback": 0,
            },
        )
        return description

    # ------------------------------------------------------------------ helpers

    def generate_migration_description(self, op_type: str, table_name: str) -> str:
        if table_name and table_name != "unknown":
            return f"{op_type} on {table_name}"
        return op_type

    def qualified_table_name(self, table_name: str, schema: str | None = None) -> str:
        if schema:
            return f"{schema}.{table_name}"
        return table_name

    def create_enum_type(self, column_type: SAEnum, bind, schema: str | None = None):
        previous_schema = getattr(column_type, "schema", None)
        if schema and previous_schema is None:
            column_type.schema = schema
        try:
            column_type.create(bind, checkfirst=True)
        finally:
            if previous_schema is None:
                column_type.schema = None

    def _skip_without_table(self, op_type: str, item) -> bool:
        """Warn and return True when an index or constraint has lost its table."""
        if getattr(item, "table", None) is not None:
            return False
        self.logger.warning(
            f"Skipping {op_type} '{getattr(item, 'name', item)}': it has no associated "
            "table (metadata may be stale)"
        )
        return True

    def _skip_unnamed(self, op_type: str, constraint) -> bool:
        """Constraints can only be dropped by name; unnamed ones are left alone."""
        if constraint.name:
            return False
        self.logger.warning(
            f"Skipping {op_type} on '{constraint.table.name}': the constraint has no name"
        )
        return True

    # ------------------------------------------------------------------ tables

    def _add_table(self, op: Operations, details: tuple) -> bool:
        table = details[1]
        schema = getattr(table, "schema", None)
        bind = op.get_bind()
        if not self.is_postgres:
            # CreateTable keeps foreign keys and other table constraints;
            # op.create_table(name, *table.columns) would silently drop them.
            op.execute(CreateTable(table))
            return True

        # Pre-create enum types to avoid conflicts
        for column in table.columns:
            if isinstance(column.type, SAEnum):
                try:
                    self.create_enum_type(column.type, bind, schema)
                except (ProgrammingError, OperationalError):
                    pass  # Enum already exists, which is fine

        if self.dependency_resolver.table_exists(schema, table.name):
            return True

        # Raw SQL, since SQLAlchemy would create the enum types again
        # (checkfirst=False) and fail because they exist.
        op.execute(str(CreateTable(table).compile(bind=bind)))
        return True

    def _drop_table(self, op: Operations, details: tuple) -> bool:
        table = details[1]
        op.drop_table(table.name, schema=getattr(table, "schema", None))
        return True

    # ------------------------------------------------------------------ columns

    def _add_column(self, op: Operations, details: tuple) -> bool:
        if details[1] is None and len(details) >= 4:
            table_name = details[2]
            column = details[3]
        else:
            table_name = details[1]
            column = details[2]

        schema = self.dependency_resolver.get_schema_from_details("add_column", details)
        qualified_table_name = self.qualified_table_name(table_name, schema)

        if self.is_postgres:
            if isinstance(column.type, SAEnum):
                self.create_enum_type(column.type, op.get_bind(), schema)
            op.add_column(qualified_table_name, column)
        else:
            with op.batch_alter_table(qualified_table_name) as batch_op:
                batch_op.add_column(column)
        return True

    def _drop_column(self, op: Operations, details: tuple) -> bool:
        # Alembic: ("remove_column", schema, table_name, Column)
        schema = details[1] if len(details) > 1 else None
        table_name = details[2] if len(details) > 2 else "unknown"
        column = details[3] if len(details) > 3 else "unknown"
        column_name = getattr(column, "name", column)
        qualified_table_name = self.qualified_table_name(table_name, schema)
        if self.is_postgres:
            op.drop_column(qualified_table_name, column_name)
        else:
            with op.batch_alter_table(qualified_table_name) as batch_op:
                batch_op.drop_column(column_name)
        return True

    def _modify_type(self, op: Operations, details: tuple) -> bool:
        schema = details[1] if len(details) > 1 else None
        table_name = details[2] if len(details) > 2 else "unknown"
        column_name = details[3] if len(details) > 3 else "unknown"
        existing_type = details[5] if len(details) > 5 else None
        new_type = details[6] if len(details) > 6 else None
        qualified_table_name = self.qualified_table_name(table_name, schema)

        if not (self.is_postgres and new_type is not None):
            with op.batch_alter_table(qualified_table_name) as batch_op:
                batch_op.alter_column(column_name, type_=new_type)
            return True

        if isinstance(new_type, SAEnum):
            try:
                self.create_enum_type(new_type, op.get_bind(), schema)
            except (ProgrammingError, OperationalError):
                pass

            enum_name = getattr(new_type, "name", None)
            if enum_name is None and hasattr(new_type, "enum_class"):
                enum_name = new_type.enum_class.__name__.lower()
            if enum_name:
                if existing_type is None or isinstance(existing_type, SAEnum):
                    using = f'"{column_name}"::text::{enum_name}'
                else:
                    using = f'"{column_name}"::{enum_name}'
                op.execute(
                    f'ALTER TABLE "{qualified_table_name}" ALTER COLUMN "{column_name}" '
                    f"TYPE {enum_name} USING {using}"
                )
                return True

        type_str = str(new_type).upper()
        if "JSON" in type_str and existing_type is not None:
            existing_str = str(existing_type).upper()
            using_type = "JSONB" if "JSONB" in type_str else "JSON"
            if "STRING" in existing_str or "TEXT" in existing_str or "VARCHAR" in existing_str:
                op.execute(
                    f'ALTER TABLE "{qualified_table_name}" ALTER COLUMN "{column_name}" '
                    f'TYPE {using_type} USING "{column_name}"::{using_type.lower()}'
                )
                return True
        op.alter_column(qualified_table_name, column_name, type_=new_type)
        return True

    def _alter_column(self, op: Operations, details: tuple, **changes) -> bool:
        schema = details[1] if len(details) > 1 else None
        table_name = details[2] if len(details) > 2 else "unknown"
        column_name = details[3] if len(details) > 3 else "unknown"
        qualified_table_name = self.qualified_table_name(table_name, schema)
        if self.is_postgres:
            op.alter_column(qualified_table_name, column_name, **changes)
        else:
            with op.batch_alter_table(qualified_table_name) as batch_op:
                batch_op.alter_column(column_name, **changes)
        return True

    def _modify_nullable(self, op: Operations, details: tuple) -> bool:
        return self._alter_column(op, details, nullable=details[6] if len(details) > 6 else None)

    def _modify_default(self, op: Operations, details: tuple) -> bool:
        return self._alter_column(
            op, details, server_default=details[6] if len(details) > 6 else None
        )

    # ------------------------------------------------------------------ indexes

    def _add_index(self, op: Operations, details: tuple) -> bool:
        index = details[1]
        if self._skip_without_table("add_index", index):
            return False
        columns = [c.name for c in index.columns]
        if self.is_postgres:
            op.create_index(
                index.name,
                index.table.name,
                columns,
                unique=index.unique,
                schema=getattr(index.table, "schema", None),
            )
        else:
            with op.batch_alter_table(index.table.name) as batch_op:
                batch_op.create_index(index.name, columns, unique=index.unique)
        return True

    def _drop_index(self, op: Operations, details: tuple) -> bool:
        index = details[1]
        if self._skip_without_table("drop_index", index):
            return False
        if self.is_postgres:
            op.drop_index(index.name, index.table.name, schema=getattr(index.table, "schema", None))
        else:
            with op.batch_alter_table(index.table.name) as batch_op:
                batch_op.drop_index(index.name)
        return True

    # ------------------------------------------------------------------ constraints

    def _add_constraint(self, op: Operations, details: tuple) -> bool:
        constraint = details[1] if len(details) > 1 else None
        if not (hasattr(constraint, "table") and hasattr(constraint, "name")):
            return False
        if self._skip_without_table("add_constraint", constraint):
            return False

        if hasattr(constraint, "columns"):
            columns = [c.name for c in constraint.columns]
        elif hasattr(constraint, "c"):
            columns = [c.name for c in constraint.c]
        else:
            columns = []

        try:
            if self.is_postgres:
                op.create_unique_constraint(
                    constraint.name,
                    constraint.table.name,
                    columns,
                    schema=getattr(constraint.table, "schema", None),
                )
            else:
                with op.batch_alter_table(constraint.table.name) as batch_op:
                    batch_op.create_unique_constraint(constraint.name, columns)
        except (ProgrammingError, OperationalError) as e:
            self.logger.warning(f"Failed to create constraint {constraint.name}: {e}")
            return False
        return True

    def _drop_constraint(self, op: Operations, details: tuple) -> bool:
        constraint = details[1]
        if self._skip_without_table("drop_constraint", constraint):
            return False
        if self._skip_unnamed("drop_constraint", constraint):
            return False
        if self.is_postgres:
            op.drop_constraint(
                constraint.name,
                constraint.table.name,
                type_="unique",
                schema=getattr(constraint.table, "schema", None),
            )
        else:
            with op.batch_alter_table(constraint.table.name) as batch_op:
                batch_op.drop_constraint(constraint.name, type_="unique")
        return True

    def _create_foreign_key(self, op: Operations, details: tuple) -> bool:
        fk = details[1]
        if self._skip_without_table("create_foreign_key", fk):
            return False

        source, target = fk.table, fk.referred_table
        local_columns = [column.name for column in fk.columns]
        remote_columns = [element.column.name for element in fk.elements]
        options = {
            "ondelete": fk.ondelete,
            "onupdate": fk.onupdate,
            "deferrable": fk.deferrable,
            "initially": fk.initially,
            "referent_schema": target.schema,
        }

        if not self.is_postgres:
            # SQLite can't add a constraint to a table: batch mode rebuilds it.
            with op.batch_alter_table(source.name, schema=source.schema) as batch_op:
                batch_op.create_foreign_key(
                    fk.name, target.name, local_columns, remote_columns, **options
                )
            return True

        try:
            # A savepoint, so a refused constraint doesn't abort the transaction.
            with op.get_bind().begin_nested():
                op.create_foreign_key(
                    fk.name,
                    source.name,
                    target.name,
                    local_columns,
                    remote_columns,
                    source_schema=source.schema,
                    **options,
                )
        except IntegrityError as e:
            self.logger.warning(
                f"Couldn't add foreign key {fk.name}: some rows in '{source.name}' point at "
                f"rows missing from '{target.name}'. Fix or remove them; it is tried again "
                f"at the next start. ({e.orig})"
            )
            return False
        return True

    def _drop_foreign_key(self, op: Operations, details: tuple) -> bool:
        fk = details[1]
        if self._skip_without_table("drop_foreign_key", fk):
            return False
        if self._skip_unnamed("drop_foreign_key", fk):
            return False
        if self.is_postgres:
            op.drop_constraint(fk.name, fk.table.name, type_="foreignkey", schema=fk.table.schema)
        else:
            with op.batch_alter_table(fk.table.name, schema=fk.table.schema) as batch_op:
                batch_op.drop_constraint(fk.name, type_="foreignkey")
        return True

    # ------------------------------------------------------------------ enums

    def _create_enum(self, op: Operations, details: tuple) -> bool:
        name, schema, enum_values = details[1], details[2], details[3]
        SAEnum(*enum_values, name=name, schema=schema).create(op.get_bind(), checkfirst=True)
        return True

    def _drop_enum(self, op: Operations, details: tuple) -> bool:
        name = details[1]
        try:
            op.execute(f"DROP TYPE {name}")
        except (ProgrammingError, OperationalError) as e:
            self.logger.warning(f"Could not drop enum type {name}: {e}")
            return False
        return True

    def _sync_enum_values(self, op: Operations, details: tuple) -> bool:
        if not hasattr(op, "sync_enum_values"):
            self.logger.warning(
                "sync_enum_values skipped because alembic-postgresql-enum is not loaded."
            )
            return False
        schema, name, new_values, affected_columns = details[1:5]
        enum_values_to_rename = details[5] if len(details) > 5 else []
        op.sync_enum_values(
            schema,
            name,
            new_values,
            affected_columns,
            enum_values_to_rename=enum_values_to_rename,
        )
        return True
