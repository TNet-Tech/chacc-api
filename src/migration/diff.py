"""
Reading Alembic's autogenerate diff.

``compare_metadata`` names some operations differently from ChaCC's executor
(``remove_table`` vs ``drop_table``) and nests column changes in lists. The
helpers here give every operation one name and keep the runner away from
tables that no loaded model defines.
"""

from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import MetaData, Table

# Alembic's name -> the executor's name.
OPERATION_ALIASES = {
    "remove_table": "drop_table",
    "remove_column": "drop_column",
    "remove_index": "drop_index",
    "remove_constraint": "drop_constraint",
    "add_fk": "create_foreign_key",
    "remove_fk": "drop_foreign_key",
}

# alembic-postgresql-enum emits objects, not tuples.
_ENUM_OPERATIONS = {
    "SyncEnumValuesOp": "sync_enum_values",
    "CreateEnumOp": "create_enum",
    "DropEnumOp": "drop_enum",
}

# Operations whose second item is an Index or a constraint, which knows its table.
_TABLE_ITEM_OPERATIONS = frozenset(
    {
        "add_index",
        "add_constraint",
        "create_foreign_key",
        "drop_index",
        "drop_constraint",
        "drop_foreign_key",
    }
)


def operation_type(op: Any) -> str:
    """The executor's name for one diff operation."""
    class_name = type(op).__name__
    for marker, name in _ENUM_OPERATIONS.items():
        if marker in class_name:
            return name
    return OPERATION_ALIASES.get(op[0], op[0])


def flatten(diff: Iterable[Any]) -> Iterator[Any]:
    """Operations one by one; Alembic groups column changes in lists."""
    for op in diff:
        if isinstance(op, list):
            yield from op
        else:
            yield op


def _table_of(op_type: str, op: Any) -> Table | None:
    if op_type == "drop_table":
        return op[1]
    if op_type in _TABLE_ITEM_OPERATIONS:
        return getattr(op[1], "table", None)
    return None


def without_unmanaged_tables(
    diff: Iterable[Any], metadata: MetaData
) -> tuple[list[Any], list[str]]:
    """
    Drop every operation on a table that the loaded models don't define.

    Such a table may belong to a disabled module, a module that failed to load,
    a module installed outside dev mode, or a pass that runs before modules
    are discovered. ChaCC can't tell these apart from leftovers, so it never
    drops them. Returns the remaining operations and the skipped tables' names.
    """
    kept, unmanaged = [], set()
    for op in diff:
        op_type = operation_type(op)
        table = _table_of(op_type, op)
        if op_type == "drop_table" or (table is not None and table.key not in metadata.tables):
            if table is not None:
                unmanaged.add(table.key)
            continue
        kept.append(op)
    return kept, sorted(unmanaged)
