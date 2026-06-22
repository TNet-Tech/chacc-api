import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from src.migration.runner import MigrationRunner


class FakeColumn:
    def __init__(self, name):
        self.name = name


class FakeIndex:
    def __init__(self, name, table_name, columns):
        self.name = name
        self.table = type("FakeTable", (), {"name": table_name})()
        self.columns = [FakeColumn(column) for column in columns]
        self.unique = False


def test_dependency_graph_orders_add_table_before_add_index():
    runner = MigrationRunner(mode="preview")
    migrations = [
        {
            "version": "index",
            "operation": "add_index",
            "table": "menu_orders",
            "details": (
                "add_index",
                FakeIndex("ix_menu_orders_customer_id", "menu_orders", ["customer_id"]),
            ),
            "checksum": "index-checksum",
        },
        {
            "version": "table",
            "operation": "add_table",
            "table": "menu_orders",
            "details": (
                "add_table",
                type("FakeTable", (), {"name": "menu_orders"})(),
            ),
            "checksum": "table-checksum",
        },
    ]

    ordered = runner._build_dependency_graph(migrations)

    assert [migration["operation"] for migration in ordered] == ["add_table", "add_index"]


def test_dependency_graph_orders_add_index_after_add_column():
    runner = MigrationRunner(mode="preview")
    migrations = [
        {
            "version": "index",
            "operation": "add_index",
            "table": "menu_orders",
            "details": (
                "add_index",
                FakeIndex("ix_menu_orders_customer_id", "menu_orders", ["customer_id"]),
            ),
            "checksum": "index-checksum",
        },
        {
            "version": "column",
            "operation": "add_column",
            "table": "menu_orders",
            "details": ("add_column", None, "menu_orders", FakeColumn("customer_id")),
            "checksum": "column-checksum",
        },
        {
            "version": "table",
            "operation": "add_table",
            "table": "menu_orders",
            "details": (
                "add_table",
                type("FakeTable", (), {"name": "menu_orders"})(),
            ),
            "checksum": "table-checksum",
        },
    ]

    ordered = runner._build_dependency_graph(migrations)

    assert [migration["operation"] for migration in ordered] == [
        "add_table",
        "add_column",
        "add_index",
    ]


def test_diff_to_migrations_rejects_index_without_table():
    runner = MigrationRunner(mode="preview")
    index = FakeIndex("ix_menu_orders_customer_id", None, ["customer_id"])
    index.table = None

    with pytest.raises(ValueError, match="Cannot determine table for add_index"):
        runner._diff_to_migrations([("add_index", index)])
