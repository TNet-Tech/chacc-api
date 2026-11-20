"""
ChaCC Migration Runner.

Safe migration execution with tracking, backup, and preview capabilities.
"""

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import MetaData
from sqlalchemy.engine import Engine

from src.constants import (
    MIGRATION_BACKUP,
    MIGRATION_BACKUP_DIR,
    MIGRATION_LOCK_TIMEOUT,
    MIGRATION_MODE,
)
from src.database import engine as default_engine
from src.database import metadata_obj
from src.logger import configure_logging, get_default_log_level
from src.migration.backup import create_backup
from src.migration.dependencies import MigrationDependencyResolver
from src.migration.diff import flatten, operation_type, without_unmanaged_tables
from src.migration.lock import migration_lock
from src.migration.operations import MigrationOperationExecutor
from src.migration.renames import (
    describe_rename,
    guard_renamed_columns,
    plan_column_renames,
    plan_table_renames,
    resolved_by_renames,
)
from src.migration.tracker import TRACKER_TABLE, create_tracker

chacc_logger = configure_logging(log_level=get_default_log_level())

try:
    import alembic_postgresql_enum

    chacc_logger.info(f"{alembic_postgresql_enum.__name__} loaded - enhanced enum support enabled")
except ImportError:
    pass


class MigrationMode:
    PREVIEW = "preview"
    AUTO = "auto"
    FULL = "full"


def additive_mode(mode: str | None = None) -> str:
    """
    The mode for a pass that runs before every model is known (at startup,
    before modules are loaded): it may add, never remove. ``preview`` stays
    ``preview``; anything else becomes ``auto``.
    """
    mode = mode or MIGRATION_MODE
    return MigrationMode.PREVIEW if mode == MigrationMode.PREVIEW else MigrationMode.AUTO


class MigrationRunner:
    """
    Safe migration runner with tracking, backup, and preview capabilities.

    Features:
    - Migration tracking (prevents re-running)
    - Safe mode (blocks destructive operations)
    - Backup before migration
    - Preview/dry-run mode
    - Transaction safety
    - Idempotent operations (skips already-existing resources)
    """

    def __init__(
        self,
        engine: Engine | None = None,
        mode: str | None = None,
        create_backup_before: bool | None = None,
        backup_dir: str | None = None,
    ):
        self.engine = engine or default_engine
        self.mode = mode or MIGRATION_MODE
        # The engine, not the setting: tests and tools may pass another database.
        self._is_postgres = self.engine.dialect.name == "postgresql"

        self.create_backup = (
            MIGRATION_BACKUP if create_backup_before is None else create_backup_before
        )

        self.backup_dir = backup_dir or MIGRATION_BACKUP_DIR

        self._dependency_resolver = MigrationDependencyResolver(self.engine, chacc_logger)
        self._operation_executor = MigrationOperationExecutor(
            self.engine,
            self._is_postgres,
            self._dependency_resolver,
            chacc_logger,
        )

        self._tracker = None
        self._backup = None

        self._pending_migrations: list[dict] = []
        self._applied_migrations: list[dict] = []
        self._backup_attempted = False
        self._backup_path: str | None = None
        # Columns whose rename marker can't be resolved; see renames.py.
        self._held_renames: set[tuple[str, str]] = set()

    @property
    def tracker(self):
        if self._tracker is None:
            self._tracker = create_tracker(self.engine)
        return self._tracker

    @property
    def backup(self):
        if self._backup is None:
            self._backup = create_backup(self.backup_dir)
        return self._backup

    _version_counter = 0

    def _generate_version(self, operation_type: str, table_name: str) -> str:
        """Generate a version string for a migration."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        MigrationRunner._version_counter += 1
        return f"{timestamp}_{MigrationRunner._version_counter}_{operation_type}_{table_name}"

    def _generate_checksum(self, diff: list[Any]) -> str:
        return self._dependency_resolver.generate_checksum(diff)

    def _filter_safe_operations(self, diff: list[Any]) -> list[Any]:
        safe_operations = [
            "add_table",
            "add_column",
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "modify_type",
            "modify_nullable",
            "modify_default",
            "create_enum",
            "sync_enum_values",
        ]

        safe_diff = []
        dropped_count = 0

        for op in flatten(diff):
            op_type = operation_type(op)
            if op_type in safe_operations:
                safe_diff.append(op)
            else:
                dropped_count += 1
                chacc_logger.info(f"Skipping destructive operation in safe mode: {op_type}")

        if dropped_count > 0:
            # Only worth a warning when 'auto' is what the user chose; in an
            # additive pass of a 'full' start, the last pass applies them.
            log = chacc_logger.warning if MIGRATION_MODE == self.mode else chacc_logger.info
            log(f"Safe mode: Skipped {dropped_count} destructive operations")

        return safe_diff

    def _extract_table_name(self, op_type: str, op: Any) -> str:
        if hasattr(op, "__class__") and "SyncEnumValuesOp" in op.__class__.__name__:
            aff_cols = getattr(op, "affected_columns", [])
            return getattr(aff_cols[0], "table_name", str(aff_cols[0])) if aff_cols else "unknown"

        if hasattr(op, "__class__") and "CreateEnumOp" in op.__class__.__name__:
            return "unknown"

        if hasattr(op, "__class__") and "DropEnumOp" in op.__class__.__name__:
            return "unknown"

        if op_type in ("modify_type", "modify_nullable", "modify_default"):
            return op[2] if op[2] else "unknown"

        if op_type in ("drop_table", "remove_table"):
            return op[1].name if hasattr(op[1], "name") else str(op[1])

        if op_type == "add_table":
            return op[1].name if hasattr(op[1], "name") else str(op[1])

        if op_type in ("add_column", "drop_column"):
            if op[1] is None and len(op) > 2:
                return op[2]
            if hasattr(op[1], "name") and hasattr(op[1], "table"):
                return op[1].table.name
            return op[1] or "unknown"

        if op_type in (
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
        ):
            if len(op) > 1 and getattr(op[1], "table", None) is not None:
                return op[1].table.name
            return "unknown"

        if op_type == "sync_enum_values" and len(op) > 4 and op[4]:
            aff_cols = op[4]
            return getattr(aff_cols[0], "table_name", str(aff_cols[0])) if aff_cols else "unknown"

        return "unknown"

    def _extract_schema_name(self, op_type: str, op: Any) -> str | None:
        if hasattr(op, "__class__") and "SyncEnumValuesOp" in op.__class__.__name__:
            return getattr(op, "schema", None)

        if hasattr(op, "__class__") and "CreateEnumOp" in op.__class__.__name__:
            return getattr(op, "schema", None)

        if hasattr(op, "__class__") and "DropEnumOp" in op.__class__.__name__:
            return getattr(op, "schema", None)

        if not isinstance(op, tuple) or len(op) <= 1:
            return None

        if op_type == "add_table":
            return getattr(op[1], "schema", None)

        if op_type in (
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
        ):
            table = getattr(op[1], "table", None)
            return getattr(table, "schema", None) if table is not None else None

        if op_type == "add_column" and len(op) >= 4:
            column = op[3] if op[1] is None else op[2]
            table = getattr(column, "table", None)
            return getattr(table, "schema", None) if table is not None else None

        if op_type in ("modify_type", "modify_nullable", "modify_default", "drop_column"):
            column = op[2] if len(op) > 2 else None
            table = getattr(column, "table", None)
            return getattr(table, "schema", None) if table is not None else None

        if op_type == "drop_table":
            return getattr(op[1], "schema", None)

        return None

    def _build_dependency_graph(self, migrations: list[dict]) -> list[dict]:
        return self._dependency_resolver.build_dependency_graph(migrations)

    def _validate_migration_dependencies(self, migrations: list[dict]) -> None:
        self._dependency_resolver.validate_migration_dependencies(migrations)

    def _table_identity(self, migration: dict) -> str:
        return self._dependency_resolver.table_identity(migration.get("schema"), migration["table"])

    def _has_pending_dependent_for_table(
        self, migration: dict, migrations: list[dict], applied_versions: set
    ) -> bool:
        table_identity = self._table_identity(migration)
        dependent_operations = {
            "add_column",
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "modify_type",
            "modify_nullable",
            "modify_default",
            "drop_column",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
            "drop_table",
        }
        return any(
            other["version"] not in applied_versions
            and self._table_identity(other) == table_identity
            and other["operation"] in dependent_operations
            for other in migrations
        )

    def _table_object_from_details(self, op_type: str, details: tuple):
        if op_type in (
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
        ):
            return getattr(details[1], "table", None) if len(details) > 1 else None

        if op_type == "add_column":
            column = details[3] if len(details) >= 4 and details[1] is None else details[2]
            return getattr(column, "table", None)

        if op_type in ("modify_type", "modify_nullable", "modify_default", "drop_column"):
            column = details[2] if len(details) > 2 else None
            return getattr(column, "table", None)

        return None

    def _ensure_missing_table_creators(self, migrations: list[dict]) -> list[dict]:
        pending_tables = {
            self._table_identity(m) for m in migrations if m["operation"] == "add_table"
        }
        emitted_synthetic_tables = set()
        ordered = []

        for migration in migrations:
            table_identity = self._table_identity(migration)
            requires_existing_table = (
                migration["operation"] in self._dependency_resolver.TABLE_REQUIRED_OPERATIONS
            )
            table_missing = (
                table_identity not in pending_tables
                and not self._dependency_resolver.table_exists(
                    migration.get("schema"), migration["table"]
                )
            )

            if (
                requires_existing_table
                and table_missing
                and table_identity not in emitted_synthetic_tables
            ):
                table_object = self._table_object_from_details(
                    migration["operation"], migration["details"]
                )
                if table_object is not None:
                    table_name = table_object.name
                    schema = getattr(table_object, "schema", None)
                    synthetic_details = ("add_table", table_object)
                    synthetic = {
                        "version": self._generate_version("add_table", table_name),
                        "operation": "add_table",
                        "table": table_name,
                        "schema": schema,
                        "details": synthetic_details,
                        "checksum": self._generate_checksum([synthetic_details]),
                    }
                    ordered.append(synthetic)
                    emitted_synthetic_tables.add(table_identity)
                    ordered.append(migration)
                else:
                    chacc_logger.warning(
                        f"Skipping migration {migration['operation']} on '{table_identity}': "
                        "cannot determine table structure, table may have been removed or metadata is stale"
                    )
            else:
                ordered.append(migration)

        return ordered

    def _should_apply_migration(
        self,
        migration: dict,
        migrations: list[dict],
        applied_versions: set,
        applied_checksums: set,
    ) -> bool:

        if migration["version"] in applied_versions:
            return False

        if migration["checksum"] in applied_checksums:
            if migration["operation"] == "add_table":
                table_exists = self._dependency_resolver.table_exists(
                    migration.get("schema"), migration["table"]
                )

                if not table_exists or self._has_pending_dependent_for_table(
                    migration, migrations, applied_versions
                ):
                    return True
            return False

        return True

    def _diff_to_migrations(self, diff: list[Any]) -> list[dict]:
        migrations = []
        for op in flatten(diff):
            migrations.extend(self._process_diff_op(op))
        return self._build_dependency_graph(migrations)

    def _process_diff_op(self, op: Any) -> list[dict]:
        op_type = operation_type(op)
        if op_type == "sync_enum_values":
            aff_cols = getattr(op, "affected_columns", [])
            details = (
                op_type,
                getattr(op, "schema", None),
                getattr(op, "name", ""),
                getattr(op, "new_values", []),
                aff_cols,
                getattr(op, "enum_values_to_rename", []),
            )
        elif op_type in ("create_enum", "drop_enum"):
            details = (
                op_type,
                getattr(op, "name", ""),
                getattr(op, "schema", None),
                getattr(op, "enum_values", []),
            )
        else:
            details = op

        table_name = self._extract_table_name(op_type, op)
        schema = self._extract_schema_name(op_type, op)

        if (
            table_name == "unknown"
            and op_type in self._dependency_resolver.TABLE_REQUIRED_OPERATIONS
        ):
            raise ValueError(f"Cannot determine table for {op_type} operation: {op}")

        version = self._generate_version(op_type, table_name)
        checksum = self._generate_checksum([details])

        return [
            {
                "version": version,
                "operation": op_type,
                "table": table_name,
                "schema": schema,
                "details": details,
                "checksum": checksum,
            }
        ]

    async def preview(self, model_metadata: MetaData = None) -> dict[str, Any]:
        """
        Preview what migrations would be applied without making changes.

        Args:
            model_metadata: SQLAlchemy metadata to compare

        Returns:
            Dict with preview information
        """
        metadata = model_metadata or metadata_obj

        if metadata.tables:
            for table in metadata.tables.values():
                table.bind = self.engine

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.tracker._ensure_table)
        with ThreadPoolExecutor(max_workers=1) as executor:
            diff = await loop.run_in_executor(executor, self._get_diff, metadata)

        if self.mode == MigrationMode.AUTO:
            diff = self._filter_safe_operations(diff)

        migrations = self._diff_to_migrations(diff)

        return {
            "mode": self.mode,
            "pending_count": len(migrations),
            "migrations": migrations,
            "would_backup": self.create_backup,
            "checksum": self._generate_checksum(diff),
        }

    def _get_diff(self, metadata: MetaData) -> list[tuple]:
        """Get database schema diff."""
        with self.engine.connect() as conn:
            context = MigrationContext.configure(conn)

            for table in metadata.tables.values():
                table.bind = self.engine

            diff = list(flatten(compare_metadata(context, metadata) or []))

        diff, unmanaged = without_unmanaged_tables(diff, metadata)
        diff = guard_renamed_columns(diff, metadata, chacc_logger, self._held_renames)
        unmanaged = [name for name in unmanaged if name != TRACKER_TABLE]
        if unmanaged:
            # Only news in the last pass of a 'full' start: earlier passes run
            # before module models are known, and 'auto' never drops tables.
            log = chacc_logger.info if self.mode == MigrationMode.FULL else chacc_logger.debug
            log(
                f"Keeping {len(unmanaged)} table(s) that no loaded model defines "
                f"(tables are never dropped automatically): {', '.join(unmanaged)}"
            )
        return diff

    async def run(self, model_metadata: MetaData = None) -> dict[str, Any]:
        """
        Run pending migrations, one process at a time (see src/migration/lock.py):
        others wait, then find nothing left to do.

        Raises:
            MigrationLockTimeout: another process kept migrating past MIGRATION_LOCK_TIMEOUT
            RuntimeError: If migration fails and can't be recovered
        """
        async with migration_lock(self.engine, chacc_logger, MIGRATION_LOCK_TIMEOUT):
            return await self._run(model_metadata)

    async def _run(self, model_metadata: MetaData = None) -> dict[str, Any]:
        """
        Run pending migrations.

        Args:
            model_metadata: SQLAlchemy metadata to compare

        Returns:
            Dict with migration results

        Raises:
            RuntimeError: If migration fails and can't be recovered
        """
        metadata = model_metadata or metadata_obj

        chacc_logger.info(f"Migration: discovered {len(metadata.tables)} tables in metadata")
        for table_name in sorted(metadata.tables.keys()):
            chacc_logger.debug(f"  - {table_name}")

        if self.mode == MigrationMode.PREVIEW:
            return await self._preview_run(metadata)

        try:
            # Renames first, so the comparison finds the data where the models
            # expect it. Tables before columns: columns are looked up under the
            # table's new name.
            for plan in self._rename_planners():
                renames = await asyncio.to_thread(plan, metadata, self.engine, chacc_logger)
                if renames:
                    await self._backup_once()
                    await self._apply_renames(renames)

            preview_result = await self.preview(metadata)
            if preview_result["pending_count"]:
                await self._backup_once()
                await self._apply_migrations(preview_result["migrations"], metadata)
            elif not self._applied_migrations:
                chacc_logger.info("Database schema is up to date")
                return {"status": "up_to_date", "message": "No migrations to apply"}

            return {
                "status": "success",
                "applied_count": len(self._applied_migrations),
                "applied": self._applied_migrations,
                "backup": self._backup_path,
            }

        except Exception as e:
            chacc_logger.error(f"Migration failed: {e}")
            if self._backup_path and os.path.exists(self._backup_path):
                await self._recover_from(self._backup_path)
            raise RuntimeError(f"Migration failed: {e}") from e

    async def _preview_run(self, metadata: MetaData) -> dict[str, Any]:
        renames = []
        for plan in self._rename_planners():
            renames += await asyncio.to_thread(plan, metadata, self.engine, chacc_logger)
        for details in renames:
            chacc_logger.info(f"Would rename {describe_rename(details)}")

        preview_result = await self.preview(metadata)
        # What the renames take care of isn't pending.
        resolved = resolved_by_renames(renames)
        preview_result["migrations"] = [m for m in preview_result["migrations"] if not resolved(m)]
        preview_result["pending_count"] = len(preview_result["migrations"]) + len(renames)
        preview_result["renames"] = renames

        chacc_logger.info("Preview mode - no changes will be made")
        return {
            "status": "preview",
            "message": "Run with AUTO or FULL mode to apply changes",
            **preview_result,
        }

    def _rename_planners(self):
        """Tables first: columns are then looked up under the table's new name."""
        return (
            plan_table_renames,
            functools.partial(plan_column_renames, held=self._held_renames),
        )

    async def _apply_renames(self, renames: list[tuple]) -> None:
        for details in renames:
            op_type = details[0]
            table_name = self._dependency_resolver.get_table_name_from_details(op_type, details)
            await self._apply_single_migration(
                self._generate_version(op_type, table_name),
                details,
                op_type,
                self._generate_checksum([details]),
            )

    async def _backup_once(self) -> None:
        """One backup per pass, before its first change, when backups are on."""
        if self.create_backup and not self._backup_attempted:
            self._backup_attempted = True
            self._backup_path = await self._backup_before_changes()

    async def _backup_before_changes(self) -> str | None:
        """
        Back up the database before applying anything. If that fails, 'auto'
        (additions only) carries on; 'full' stops rather than drop data with
        no way back.
        """
        try:
            backup_path = await self.backup.create_backup()
        except Exception as e:
            if self.mode == MigrationMode.AUTO:
                chacc_logger.warning(f"Backup failed, continuing anyway: {e}")
                return None
            raise RuntimeError(f"Backup failed, aborting migration: {e}") from e
        chacc_logger.info(f"Backup created: {backup_path}")
        return backup_path

    async def _recover_from(self, backup_path: str) -> None:
        """
        SQLite: put the backup back. PostgreSQL: each change ran in its own
        transaction, so the failed one was rolled back and earlier ones are
        kept; replacing a database the server is connected to isn't safe, so
        say where the backup is instead.
        """
        if not self.backup.is_sqlite:
            chacc_logger.error(
                f"Changes applied before the failure were kept. To go back to the "
                f"state before this migration, stop the server and restore {backup_path} "
                "(see 'Backup and Restore' in the database migration docs)."
            )
            return

        chacc_logger.warning("Restoring the database from the backup...")
        try:
            await self.backup.restore(backup_path)
        except Exception as restore_error:
            chacc_logger.critical(f"CRITICAL: Migration failed AND restore failed: {restore_error}")
            raise RuntimeError(
                f"Migration failed and could not restore from backup. "
                f"Manual intervention required. Backup at: {backup_path}"
            ) from restore_error
        chacc_logger.info("Database restored from backup")

    async def _apply_migrations(self, migrations: list[dict], metadata: MetaData):
        """Apply migrations to database."""
        loop = asyncio.get_event_loop()
        applied_versions = await loop.run_in_executor(None, self.tracker.get_applied)
        applied_checksums = await loop.run_in_executor(None, self.tracker.get_applied_checksums)

        pending = [
            m
            for m in migrations
            if self._should_apply_migration(m, migrations, applied_versions, applied_checksums)
        ]
        pending = self._ensure_missing_table_creators(pending)
        pending = self._build_dependency_graph(pending)

        self._validate_migration_dependencies(pending)

        if not pending:
            chacc_logger.info("No pending migrations to apply")
            return

        for migration in pending:
            version = migration["version"]
            details = migration["details"]
            op_type = migration["operation"]
            checksum = migration["checksum"]

            try:
                await asyncio.wait_for(
                    self._apply_single_migration(version, details, op_type, checksum),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                chacc_logger.error(f"Migration timed out: {version}")
                raise

        chacc_logger.info(f"Migration completed: {len(self._applied_migrations)} changes applied")

    async def _apply_single_migration(
        self, version: str, details: tuple, op_type: str, checksum: str | None = None
    ):
        """Apply a single migration in its own transaction."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._operation_executor.apply_single_migration(
                version,
                details,
                op_type,
                checksum,
                self._applied_migrations,
            ),
        )


def create_migration_runner(
    engine: Engine | None = None,
    mode: str | None = None,
    create_backup_before: bool | None = None,
    backup_dir: str | None = None,
) -> MigrationRunner:
    """Factory function to create a MigrationRunner."""
    return MigrationRunner(
        engine=engine, mode=mode, create_backup_before=create_backup_before, backup_dir=backup_dir
    )


async def run_migration(
    mode: str | None = None, create_backup: bool | None = None
) -> dict[str, Any]:
    """
    Run migrations with sensible defaults.

    Usage:
        from src.migration.runner import run_migration
        result = await run_migration()
    """
    runner = create_migration_runner(mode=mode, create_backup_before=create_backup)

    if runner.mode is None:
        runner.mode = MigrationMode.AUTO

    return await runner.run()
