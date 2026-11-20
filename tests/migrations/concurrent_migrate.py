"""
Helper for test_migration_lock.py: one process that migrates a database, as a
worker or replica does at startup. Not a test module.

    python concurrent_migrate.py <database url> <start at (time.time())> <version>
    python concurrent_migrate.py <database url> hold        # take the lock, then wait

Prints one JSON line with the result.
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def models(version: int) -> MetaData:
    """v1: two tables, no foreign key. v2: a foreign key, a rename, a new column."""
    md = MetaData(naming_convention=CONVENTION)
    Table("shelves", md, Column("id", Integer, primary_key=True))
    if version == 1:
        Table(
            "books",
            md,
            Column("id", Integer, primary_key=True),
            Column("shelf_id", Integer),
            Column("name", String(50)),
        )
    else:
        Table(
            "books",
            md,
            Column("id", Integer, primary_key=True),
            Column("shelf_id", Integer, ForeignKey("shelves.id")),
            Column("title", String(50), info={"renamed_from": "name"}),
            Column("isbn", String(20)),
        )
    return md


async def migrate(url: str, version: int) -> dict:
    from src.migration.runner import MigrationMode, MigrationRunner

    engine = create_engine(url)
    try:
        runner = MigrationRunner(engine=engine, mode=MigrationMode.FULL, create_backup_before=False)
        result = await runner.run(models(version))
        return {"status": result["status"], "applied": result.get("applied_count", 0)}
    finally:
        engine.dispose()


async def hold(url: str) -> None:
    from src.migration.lock import migration_lock

    engine = create_engine(url)
    async with migration_lock(engine, _Quiet(), timeout=5):
        print(json.dumps({"status": "holding"}), flush=True)
        await asyncio.sleep(3600)


class _Quiet:
    def info(self, *_):
        pass


if __name__ == "__main__":
    url = sys.argv[1]
    if sys.argv[2] == "hold":
        asyncio.run(hold(url))
    else:
        time.sleep(max(0.0, float(sys.argv[2]) - time.time()))  # start together
        try:
            print(json.dumps(asyncio.run(migrate(url, int(sys.argv[3])))))
        except Exception as e:
            print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}))
