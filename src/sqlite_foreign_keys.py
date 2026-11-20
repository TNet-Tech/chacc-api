"""
Foreign key enforcement on SQLite.

SQLite ignores foreign keys unless ``PRAGMA foreign_keys=ON`` is sent on every
new connection. With ``SQLITE_FOREIGN_KEYS=true`` ChaCC sends it, and:

- suspends enforcement while migrations run, because SQLite rebuilds a table to
  change it, and rebuilding a parent table with enforcement on would delete or
  reject its child rows;
- reports rows that point at missing parents at startup, since enforcement
  only stops new ones.
"""

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine

from src.constants import SQLITE_FOREIGN_KEYS


def is_enforced(bind: Engine | Connection) -> bool:
    return SQLITE_FOREIGN_KEYS and bind.dialect.name == "sqlite"


def enforce_on(engine: Engine) -> None:
    """Turn enforcement on for every new connection of ``engine`` (sync engine)."""
    if is_enforced(engine):
        event.listen(engine, "connect", _enable_on_connect)


def _enable_on_connect(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@contextmanager
def suspended(conn: Connection) -> Iterator[None]:
    """
    Run the block with enforcement off on ``conn``. Use it outside any
    transaction: SQLite ignores this PRAGMA inside one.
    """
    if not is_enforced(conn):
        yield
        return

    _set(conn, enabled=False)
    try:
        yield
    finally:
        try:
            _set(conn, enabled=True)
        except Exception:
            # Never hand a connection without enforcement back to the pool.
            conn.invalidate()
            raise


def _set(conn: Connection, *, enabled: bool) -> None:
    conn.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")
    conn.commit()


def orphan_rows(engine: Engine) -> Counter[tuple[str, str]]:
    """Rows whose foreign key points at a missing row, counted by (table, parent table)."""
    if not is_enforced(engine):
        return Counter()
    with engine.connect() as conn:
        result = conn.exec_driver_sql("PRAGMA foreign_key_check")
        return Counter((row[0], row[2]) for row in result)


def warn_about_orphan_rows(engine: Engine, logger) -> None:
    for (table, parent), count in sorted(orphan_rows(engine).items()):
        logger.warning(
            f"{count} row(s) in '{table}' point at rows missing from '{parent}'. "
            "Changing those rows will fail until they are fixed or removed "
            "(SQLITE_FOREIGN_KEYS is on)."
        )
