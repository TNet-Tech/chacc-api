"""
Migrations against a real SQLite database: foreign keys, tables no loaded
model defines, what gets recorded, backups and foreign key enforcement.

Each test uses its own database file, never the shared test database.
"""

import asyncio
import os
import sqlite3
import stat
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError

import src.migration.backup as backup_module
import src.migration.runner as runner_module
import src.sqlite_foreign_keys as sqlite_fks
from src.migration.dependencies import MigrationDependencyResolver
from src.migration.diff import operation_type, without_unmanaged_tables
from src.migration.operations import MigrationOperationExecutor
from src.migration.runner import MigrationMode, MigrationRunner, additive_mode
from src.migration.tracker import TRACKER_TABLE, create_tracker

CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def models(*, with_other_table=True, child_note=True, parent_extra=False) -> MetaData:
    md = MetaData(naming_convention=CONVENTION)
    parent_columns = [Column("id", Integer, primary_key=True), Column("name", String)]
    if parent_extra:
        parent_columns.append(Column("extra", String))
    Table("parents", md, *parent_columns)
    child_columns = [
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parents.id", ondelete="CASCADE")),
    ]
    if child_note:
        child_columns.append(Column("note", String))
    Table("children", md, *child_columns)
    if with_other_table:
        Table("other_module_items", md, Column("id", Integer, primary_key=True))
    return md


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "app.db")


@pytest.fixture
def engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}")
    yield eng
    eng.dispose()


def migrate(engine, metadata, mode=MigrationMode.FULL, backup=False):
    runner = MigrationRunner(engine=engine, mode=mode, create_backup_before=backup)
    return asyncio.run(runner.run(metadata))


def logged(engine) -> list[str]:
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(text(f"SELECT description FROM {TRACKER_TABLE}"))]


def foreign_keys(engine, table) -> list[dict]:
    return inspect(engine).get_foreign_keys(table)


# ---------------------------------------------------------------- the diff


def test_alembic_names_map_to_executor_names():
    assert operation_type(("remove_table", None)) == "drop_table"
    assert operation_type(("remove_index", None)) == "drop_index"
    assert operation_type(("add_fk", None)) == "create_foreign_key"
    assert operation_type(("remove_fk", None)) == "drop_foreign_key"
    assert operation_type(("remove_column", None, "t", None)) == "drop_column"
    assert operation_type(("add_table", None)) == "add_table"


def test_operations_on_tables_no_model_defines_are_left_out():
    loaded = models(with_other_table=False)
    unknown = Table("other_module_items", MetaData(), Column("id", Integer))
    index = MagicMock(table=unknown)
    managed_index = MagicMock(table=loaded.tables["children"])

    kept, unmanaged = without_unmanaged_tables(
        [("remove_index", index), ("remove_table", unknown), ("remove_index", managed_index)],
        loaded,
    )

    assert kept == [("remove_index", managed_index)]
    assert unmanaged == ["other_module_items"]


def test_additive_mode_never_removes():
    assert additive_mode("full") == MigrationMode.AUTO
    assert additive_mode("auto") == MigrationMode.AUTO
    assert additive_mode("preview") == MigrationMode.PREVIEW


# ---------------------------------------------------------------- issue 1: foreign keys


def test_new_tables_keep_their_foreign_keys(engine):
    migrate(engine, models())

    [fk] = foreign_keys(engine, "children")
    assert fk["referred_table"] == "parents"
    assert fk["options"].get("ondelete") == "CASCADE"


def test_missing_foreign_key_is_added_to_an_existing_table(engine):
    # A table created by an earlier ChaCC version, without its foreign key.
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE parents (id INTEGER PRIMARY KEY, name VARCHAR)")
        conn.exec_driver_sql(
            "CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER, note VARCHAR)"
        )
        conn.exec_driver_sql("INSERT INTO children (id, parent_id) VALUES (1, 999)")

    migrate(engine, models(with_other_table=False), mode=MigrationMode.AUTO)

    assert [fk["referred_table"] for fk in foreign_keys(engine, "children")] == ["parents"]
    assert "create_foreign_key on children" in logged(engine)
    with engine.connect() as conn:  # existing rows survive the table rebuild
        assert conn.execute(text("SELECT parent_id FROM children")).scalar() == 999
    second = migrate(engine, models(with_other_table=False), mode=MigrationMode.AUTO)
    assert second["status"] == "up_to_date"


# ---------------------------------------------------------------- issue 3: tables and the log


def test_full_mode_keeps_tables_no_loaded_model_defines(engine):
    migrate(engine, models())
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO other_module_items (id) VALUES (1)")

    # The module that owns other_module_items is disabled: its models aren't loaded.
    migrate(engine, models(with_other_table=False))

    assert "other_module_items" in inspect(engine).get_table_names()
    assert not [entry for entry in logged(engine) if "drop" in entry or "remove" in entry]


def test_full_mode_still_removes_columns_from_tables_models_define(engine):
    migrate(engine, models())

    migrate(engine, models(child_note=False))

    assert "note" not in {c["name"] for c in inspect(engine).get_columns("children")}
    assert "drop_column on children" in logged(engine)


def test_skipped_and_unknown_operations_are_not_recorded(engine):
    create_tracker(engine)._ensure_table()
    executor = MigrationOperationExecutor(engine, False, MigrationDependencyResolver(engine))

    executor.apply_single_migration("v1", ("not_an_operation",), "not_an_operation")()
    stale_index = MagicMock(table=None)
    executor.apply_single_migration("v2", ("add_index", stale_index), "add_index")()

    assert logged(engine) == []


# ---------------------------------------------------------------- issue 2: backups


@pytest.fixture
def backups(tmp_path, db_path, monkeypatch):
    monkeypatch.setattr(backup_module, "SQLITE_DB_PATH", db_path)
    directory = tmp_path / "backups"
    monkeypatch.setattr(backup_module, "DEFAULT_BACKUP_DIR", str(directory))
    return directory


def backup_files(directory) -> list[str]:
    return sorted(
        name
        for name in os.listdir(directory)
        if name.startswith("chacc_backup_") and "latest" not in name
    )


def test_migration_backup_setting_turns_backups_on(engine, monkeypatch):
    monkeypatch.setattr(runner_module, "MIGRATION_BACKUP", True)
    assert MigrationRunner(engine=engine).create_backup is True
    assert MigrationRunner(engine=engine, create_backup_before=False).create_backup is False


@pytest.mark.parametrize("mode", [MigrationMode.AUTO, MigrationMode.FULL])
def test_backup_is_taken_before_changes_in_every_applying_mode(engine, backups, mode):
    migrate(engine, models())

    result = migrate(engine, models(parent_extra=True), mode=mode, backup=True)

    assert result["backup"] and os.path.exists(result["backup"])
    assert stat.S_IMODE(os.stat(result["backup"]).st_mode) == 0o600
    with sqlite3.connect(result["backup"]) as copy:  # taken before the new column
        columns = [row[1] for row in copy.execute("PRAGMA table_info(parents)")]
    assert "extra" not in columns


def test_no_backup_when_nothing_changes(engine, backups):
    migrate(engine, models())
    migrate(engine, models(), backup=True)
    assert not backups.exists() or backup_files(backups) == []


def test_backups_never_overwrite_each_other(engine, backups):
    migrate(engine, models())
    store = backup_module.DatabaseBackup(str(backups))

    first = asyncio.run(store.create_backup())
    second = asyncio.run(store.create_backup())

    assert first != second
    assert backup_files(backups) == sorted(os.path.basename(p) for p in (first, second))


def test_sqlite_is_restored_when_a_migration_fails(engine, backups):
    migrate(engine, models())
    runner = MigrationRunner(engine=engine, mode=MigrationMode.AUTO, create_backup_before=True)

    async def fail_halfway(migrations, metadata):
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE half_done (id INTEGER)")
        raise RuntimeError("boom")

    runner._apply_migrations = fail_halfway
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(runner.run(models(parent_extra=True)))

    assert "half_done" not in inspect(engine).get_table_names()


def test_postgres_is_never_restored_automatically(engine):
    runner = MigrationRunner(engine=engine, mode=MigrationMode.FULL)
    runner._backup = MagicMock(is_sqlite=False, restore=AsyncMock())

    asyncio.run(runner._recover_from("/backups/chacc_backup_x.sql"))

    runner._backup.restore.assert_not_called()


# ---------------------------------------------------------------- SQLITE_FOREIGN_KEYS


@pytest.fixture
def enforcing_engine(db_path, monkeypatch):
    monkeypatch.setattr(sqlite_fks, "SQLITE_FOREIGN_KEYS", True)
    eng = create_engine(f"sqlite:///{db_path}")
    sqlite_fks.enforce_on(eng)
    yield eng
    eng.dispose()


def test_foreign_keys_are_off_unless_the_setting_is_on(engine):
    sqlite_fks.enforce_on(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0


def test_setting_enforces_foreign_keys(enforcing_engine):
    migrate(enforcing_engine, models())

    with pytest.raises(IntegrityError), enforcing_engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO children (id, parent_id) VALUES (1, 999)")


def test_rebuilding_a_parent_table_keeps_its_children(enforcing_engine):
    migrate(enforcing_engine, models(parent_extra=True))
    with enforcing_engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO parents (id, name) VALUES (1, 'p')")
        conn.exec_driver_sql("INSERT INTO children (id, parent_id) VALUES (1, 1)")

    # Dropping a column rebuilds 'parents'; with enforcement on during the
    # rebuild, ON DELETE CASCADE would empty 'children'.
    migrate(enforcing_engine, models(parent_extra=False))

    with enforcing_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM children").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_orphan_rows_are_reported(enforcing_engine):
    migrate(enforcing_engine, models())
    with enforcing_engine.connect() as conn, sqlite_fks.suspended(conn):
        conn.exec_driver_sql("INSERT INTO children (id, parent_id) VALUES (1, 999)")
        conn.commit()

    assert sqlite_fks.orphan_rows(enforcing_engine) == {("children", "parents"): 1}
