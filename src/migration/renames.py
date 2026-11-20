"""
Renames declared on models.

Comparing models with the database, a renamed column looks like one column
removed and another added, and nothing can tell the two apart. So a model
states it, and ChaCC renames in the database *before* comparing; the
comparison then finds nothing to do and the data stays where it was::

    class Item(ChaCCBaseModel):
        __tablename__ = "shop_items"
        __table_args__ = {"info": {"renamed_from": "shop_products"}}

        title = Column(String, info={"renamed_from": "name"})

A list gives several earlier names, newest first, for databases that skipped
versions: ``info={"renamed_from": ["name", "label"]}``.

Safety rules:

- Rename only when the new name is missing and exactly one earlier name exists.
- When the new and an earlier name both exist, change nothing and warn.
- A column named in ``renamed_from`` is never dropped automatically, in any
  mode, so a missed or wrong rename can't delete its data.
- A marker that can't be resolved (no earlier name exists, or several do)
  holds the table: the marked column isn't added and no column of that table
  is dropped until the marker is fixed. A typo can't cost data.
- Indexes and unique constraints on the column are renamed to the names the
  model expects, so no duplicate is created next to them.
"""

from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import MetaData, Table, UniqueConstraint
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.engine import Engine, Inspector

from src.migration.diff import operation_type

RENAMED_FROM = "renamed_from"

# Each planned rename is an operation tuple, like Alembic's:
#   ("rename_table", schema, old_table, new_table)
#   ("rename_column", schema, table, old_column, new_column)
#   ("rename_index", schema, table, old_name, new_name, unique, column)
#   ("rename_unique_constraint", schema, table, old_name, new_name, column)
RENAME_OPERATIONS = ("rename_table", "rename_column", "rename_index", "rename_unique_constraint")


def earlier_names(item: Any, logger) -> tuple[str, ...]:
    """The names a table or column had before, from ``info["renamed_from"]``."""
    value = getattr(item, "info", {}).get(RENAMED_FROM)
    if value is None:
        return ()
    names = (value,) if isinstance(value, str) else value
    if not isinstance(names, (list, tuple)) or not all(
        isinstance(name, str) and name for name in names
    ):
        logger.warning(
            f"Ignoring {RENAMED_FROM}={value!r} on '{_label(item)}': use a name or a list of names."
        )
        return ()
    return tuple(name for name in names if name != item.name)


def _label(item: Any) -> str:
    table = getattr(item, "table", None)
    return f"{table.name}.{item.name}" if table is not None else item.name


def _table_key(schema: str | None, name: str) -> str:
    return f"{schema}.{name}" if schema else name


def protected_columns(metadata: MetaData, logger) -> set[tuple[str, str]]:
    """(table key, column name) of every earlier column name: never dropped."""
    return {
        (table.key, old)
        for table in metadata.tables.values()
        for column in table.columns
        for old in earlier_names(column, logger)
    }


def guard_renamed_columns(
    diff: Iterable[Any],
    metadata: MetaData,
    logger,
    held: set[tuple[str, str]] = frozenset(),
) -> list[Any]:
    """
    Leave out removals of columns that a model says were renamed, and, for
    tables with a marker that couldn't be resolved (``held``), the marked
    column's creation and every column removal.
    """
    protected = protected_columns(metadata, logger)
    held_tables = {table for table, _ in held}
    if not protected and not held:
        return list(diff)

    kept = []
    for op in diff:
        op_type = operation_type(op)
        if op_type in ("add_column", "drop_column"):
            _, schema, table_name, column = op[:4]
            key, name = _table_key(schema, table_name), getattr(column, "name", column)
            if op_type == "add_column" and (key, name) in held:
                continue
            if op_type == "drop_column" and ((key, name) in protected or key in held_tables):
                logger.debug(f"Keeping {table_name}.{name}: a rename marker protects it")
                continue
        kept.append(op)
    return kept


# ---------------------------------------------------------------- planning


def _present(names: Iterable[str], existing: set[str]) -> list[str]:
    return [name for name in names if name in existing]


def plan_table_renames(metadata: MetaData, engine: Engine, logger) -> list[tuple]:
    inspector = sqlalchemy_inspect(engine)
    existing: dict[str | None, set[str]] = {}

    def tables_in(schema: str | None) -> set[str]:
        if schema not in existing:
            existing[schema] = set(inspector.get_table_names(schema=schema))
        return existing[schema]

    plans = []
    for table in metadata.tables.values():
        olds = earlier_names(table, logger)
        if not olds:
            continue
        present = _present(olds, tables_in(table.schema))
        if table.name in tables_in(table.schema):
            if present:
                logger.warning(
                    f"Tables '{table.name}' and '{present[0]}' both exist, and "
                    f"'{table.name}' is marked as renamed from it. Nothing was renamed; "
                    f"move the data and drop '{present[0]}' yourself."
                )
        elif len(present) > 1:
            logger.warning(
                f"Table '{table.name}' is marked as renamed from {', '.join(present)}, "
                "which all exist. Nothing was renamed; keep only one of them."
            )
        elif present:
            plans.append(("rename_table", table.schema, present[0], table.name))
    return plans


def plan_column_renames(
    metadata: MetaData, engine: Engine, logger, held: set[tuple[str, str]] | None = None
) -> list[tuple]:
    """
    Renames of marked columns. Markers that can't be resolved are added to
    ``held`` as (table key, column name); see guard_renamed_columns.
    """
    inspector = sqlalchemy_inspect(engine)
    plans = []
    for table in metadata.tables.values():
        renamed = [(column, earlier_names(column, logger)) for column in table.columns]
        renamed = [(column, olds) for column, olds in renamed if olds]
        if not renamed or not inspector.has_table(table.name, schema=table.schema):
            continue  # a new table is created with the new names

        columns = {c["name"] for c in inspector.get_columns(table.name, schema=table.schema)}
        for column, olds in renamed:
            plan = _plan_column(table, column.name, olds, columns, logger)
            if plan is _HOLD:
                if held is not None:
                    held.add((table.key, column.name))
            elif plan:
                plans.append(plan)
                plans.extend(_plan_index_renames(inspector, table, plan[3], column.name))
    return plans


_HOLD = ("hold",)


def _plan_column(
    table: Table, new: str, olds: tuple[str, ...], columns: set[str], logger
) -> tuple | None:
    """A rename, None when there is nothing to do, or _HOLD when the marker is wrong."""
    present = _present(olds, columns)
    where = f"'{table.name}'"
    if new in columns:
        if present:
            logger.warning(
                f"Columns {new} and {present[0]} both exist in {where}, and {new} is marked "
                f"as renamed from {present[0]}. Nothing was renamed and {present[0]} is kept; "
                f"move its data into {new} and drop it yourself."
            )
        return None
    if len(present) > 1:
        logger.warning(
            f"Column {new} in {where} is marked as renamed from {', '.join(present)}, which "
            f"all exist. Nothing was renamed, and no column of {where} is added or dropped "
            "until only one of them is left."
        )
        return _HOLD
    if not present:
        logger.warning(
            f"Column {new} in {where} is marked as renamed from {', '.join(olds)}, but the "
            f"table has no such column. Nothing was renamed, and no column of {where} is "
            "added or dropped until the marker is fixed."
        )
        return _HOLD
    return ("rename_column", table.schema, table.name, present[0], new)


def _plan_index_renames(inspector: Inspector, table: Table, old: str, new: str) -> Iterator[tuple]:
    """
    Indexes and unique constraints on the old column keep their old names when
    it is renamed. Give them the names the model expects for the new one.
    """
    schema = table.schema
    model_indexes = [i for i in table.indexes if i.name and [c.name for c in i.columns] == [new]]
    db_indexes = [
        i
        for i in inspector.get_indexes(table.name, schema=schema)
        if i["column_names"] == [old] and not i.get("duplicates_constraint")
    ]
    taken = {i["name"] for i in inspector.get_indexes(table.name, schema=schema)}
    for index in model_indexes:
        match = next((i for i in db_indexes if bool(i["unique"]) == bool(index.unique)), None)
        if match and str(index.name) not in taken and match["name"] != str(index.name):
            db_indexes.remove(match)
            yield (
                "rename_index",
                schema,
                table.name,
                match["name"],
                str(index.name),
                bool(index.unique),
                new,
            )

    model_uniques = [
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name and [col.name for col in c.columns] == [new]
    ]
    db_uniques = [
        u
        for u in inspector.get_unique_constraints(table.name, schema=schema)
        if u["column_names"] == [old] and u.get("name")
    ]
    taken = {u["name"] for u in inspector.get_unique_constraints(table.name, schema=schema)}
    for constraint, match in zip(model_uniques, db_uniques, strict=False):
        if str(constraint.name) not in taken and match["name"] != str(constraint.name):
            yield (
                "rename_unique_constraint",
                schema,
                table.name,
                match["name"],
                str(constraint.name),
                new,
            )


# ---------------------------------------------------------------- preview


def describe_rename(details: tuple) -> str:
    op_type, schema = details[0], details[1]
    if op_type == "rename_table":
        return f"table {_table_key(schema, details[2])} to {details[3]}"
    kind = {
        "rename_column": "column",
        "rename_index": "index",
        "rename_unique_constraint": "unique constraint",
    }[op_type]
    return f"{kind} {_table_key(schema, details[2])}.{details[3]} to {details[4]}"


def resolved_by_renames(renames: list[tuple]):
    """
    For preview: a predicate telling which pending migrations the renames take
    care of (creating the new table, column, index or constraint).
    """
    tables = {_table_key(d[1], d[3]) for d in renames if d[0] == "rename_table"}
    columns = {(_table_key(d[1], d[2]), d[4]) for d in renames if d[0] == "rename_column"}
    names = {d[4] for d in renames if d[0] in ("rename_index", "rename_unique_constraint")}

    def resolved(migration: dict) -> bool:
        table = _table_key(migration.get("schema"), migration["table"])
        if table in tables:
            return True
        details = migration["details"]
        if migration["operation"] == "add_column" and len(details) >= 4:
            return (table, getattr(details[3], "name", None)) in columns
        if migration["operation"] in ("add_index", "add_constraint") and len(details) > 1:
            return str(getattr(details[1], "name", "")) in names
        return False

    return resolved
