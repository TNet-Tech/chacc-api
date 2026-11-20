"""
Renames declared with ``info={"renamed_from": ...}``.

Every test runs on SQLite. It also runs on PostgreSQL when
CHACC_TEST_POSTGRES_URL points at a server where the user may create
databases (each test gets its own, dropped afterwards), for example:

    CHACC_TEST_POSTGRES_URL=postgresql+psycopg://user:pass@localhost:5432/postgres
"""

import asyncio
import logging
import os
import uuid

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from src.migration.runner import MigrationMode, MigrationRunner
from src.migration.tracker import TRACKER_TABLE

CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
POSTGRES_URL = os.environ.get("CHACC_TEST_POSTGRES_URL")


@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path):
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
        yield eng
        eng.dispose()
        return

    if not POSTGRES_URL:
        pytest.skip("CHACC_TEST_POSTGRES_URL is not set")
    name = f"chacc_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    eng = create_engine(admin.url.set(database=name))
    yield eng
    eng.dispose()
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE "{name}"')
    admin.dispose()


@pytest.fixture
def warnings(monkeypatch):
    """Warnings the migration code logs (the ChaCC logger doesn't reach caplog)."""
    import src.migration.runner as runner_module

    lines: list[str] = []
    handler = logging.Handler(level=logging.WARNING)
    handler.emit = lambda record: lines.append(record.getMessage())
    runner_module.chacc_logger.addHandler(handler)
    yield lines
    runner_module.chacc_logger.removeHandler(handler)


def items_v1() -> MetaData:
    md = MetaData(naming_convention=CONVENTION)
    Table(
        "shop_products",
        md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), index=True),
        Column("code", String(20), unique=True),
    )
    return md


def items_v2(*, title_from="name", code_from="code", table_from="shop_products") -> MetaData:
    """Version 2: table shop_products -> shop_items, name -> title, code -> sku."""
    md = MetaData(naming_convention=CONVENTION)
    Table(
        "shop_items",
        md,
        Column("id", Integer, primary_key=True),
        Column("title", String(50), index=True, info={"renamed_from": title_from}),
        Column("sku", String(20), unique=True, info={"renamed_from": code_from}),
        info={"renamed_from": table_from} if table_from else {},
    )
    return md


def migrate(engine, metadata, mode=MigrationMode.FULL):
    runner = MigrationRunner(engine=engine, mode=mode, create_backup_before=False)
    return asyncio.run(runner.run(metadata))


def install_v1_with_data(engine):
    migrate(engine, items_v1())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO shop_products (id, name, code) VALUES (1, 'Tea', 'T-1')"))


def columns(engine, table) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def logged(engine) -> list[str]:
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(text(f"SELECT description FROM {TRACKER_TABLE}"))]


@pytest.mark.parametrize("mode", [MigrationMode.AUTO, MigrationMode.FULL])
def test_renames_keep_the_data(engine, mode):
    install_v1_with_data(engine)

    migrate(engine, items_v2(), mode=mode)

    tables = inspect(engine).get_table_names()
    assert "shop_items" in tables and "shop_products" not in tables
    assert columns(engine, "shop_items") == {"id", "title", "sku"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title, sku FROM shop_items")).one() == ("Tea", "T-1")
    log = logged(engine)
    assert "rename_table on shop_items" in log
    assert log.count("rename_column on shop_items") == 2


def test_indexes_and_unique_constraints_get_the_new_names(engine):
    install_v1_with_data(engine)

    migrate(engine, items_v2())

    inspector = inspect(engine)
    assert {i["name"] for i in inspector.get_indexes("shop_items")} >= {"ix_shop_items_title"}
    assert "ix_shop_products_name" not in {i["name"] for i in inspector.get_indexes("shop_items")}
    uniques = {u["name"] for u in inspector.get_unique_constraints("shop_items")}
    assert "uq_shop_items_sku" in uniques and "uq_shop_items_code" not in uniques
    with engine.begin() as conn, pytest.raises(Exception, match="(?i)unique"):
        conn.execute(text("INSERT INTO shop_items (id, title, sku) VALUES (2, 'x', 'T-1')"))


def test_renames_run_once(engine):
    install_v1_with_data(engine)
    migrate(engine, items_v2())

    assert migrate(engine, items_v2())["status"] == "up_to_date"


def test_new_installs_create_the_new_names(engine):
    migrate(engine, items_v2())

    assert columns(engine, "shop_items") == {"id", "title", "sku"}
    assert not [entry for entry in logged(engine) if entry.startswith("rename")]


def test_earlier_names_cover_skipped_versions(engine):
    """v1 named the column 'name', v2 'label', v3 'title'; this database is still on v1."""
    install_v1_with_data(engine)

    migrate(engine, items_v2(title_from=["label", "name"]))

    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM shop_items")).scalar() == "Tea"


def test_both_columns_existing_keeps_both(engine, warnings):
    install_v1_with_data(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE shop_products ADD COLUMN title VARCHAR(50)")
    md = MetaData(naming_convention=CONVENTION)
    Table(
        "shop_products",
        md,
        Column("id", Integer, primary_key=True),
        Column("title", String(50), info={"renamed_from": "name"}),
        Column("code", String(20), unique=True),
    )

    migrate(engine, md)  # full mode: would drop 'name' without the marker

    assert {"name", "title"} <= columns(engine, "shop_products")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM shop_products")).scalar() == "Tea"
    assert any("both exist" in line for line in warnings)


def test_a_misspelled_marker_holds_the_table(engine, warnings):
    install_v1_with_data(engine)
    md = MetaData(naming_convention=CONVENTION)
    Table(
        "shop_products",
        md,
        Column("id", Integer, primary_key=True),
        Column("title", String(50), info={"renamed_from": "nmae"}),  # typo
        Column("code", String(20), unique=True),
    )

    migrate(engine, md)
    migrate(engine, md)  # and on the next start

    assert columns(engine, "shop_products") == {"id", "name", "code"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM shop_products")).scalar() == "Tea"
    assert any("no such column" in line for line in warnings)


def test_invalid_marker_is_ignored_with_a_warning(engine, warnings):
    md = MetaData(naming_convention=CONVENTION)
    Table(
        "shop_products",
        md,
        Column("id", Integer, primary_key=True),
        Column("title", String(50), info={"renamed_from": 42}),
    )

    migrate(engine, md)

    assert columns(engine, "shop_products") == {"id", "title"}
    assert any("Ignoring renamed_from=42" in line for line in warnings)


def test_preview_lists_renames_and_changes_nothing(engine):
    install_v1_with_data(engine)

    result = migrate(engine, items_v2(), mode=MigrationMode.PREVIEW)

    assert [r[0] for r in result["renames"]] == ["rename_table"]
    assert not [m for m in result["migrations"] if m["table"] == "shop_items"]
    assert "shop_products" in inspect(engine).get_table_names()
