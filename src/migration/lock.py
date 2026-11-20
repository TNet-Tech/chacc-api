"""
One migrating process at a time.

Every ChaCC process (uvicorn workers, containers, replicas) migrates at
startup. Two processes changing the schema at once could both try the same
change, or rebuild the same SQLite table. The lock makes them take turns:
the first one migrates; the others wait, then compare again and find the
work done, since migrations only apply what still differs.

- PostgreSQL: a session advisory lock. Held by the connection, so it is
  released when the process exits, even if it crashes.
- SQLite: an OS lock on ``<database>.migration.lock`` next to the database.
  Every process using a SQLite file is on the same machine; the OS releases
  the lock when the process exits.
- Other databases, and in-memory SQLite: no lock (nothing to share).

Waiting doesn't block the event loop, and gives up after
``MIGRATION_LOCK_TIMEOUT`` seconds.
"""

import asyncio
import contextlib
import os
import sys
import time
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

if sys.platform == "win32":
    import msvcrt

    def _try_lock_file(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock_file(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock_file(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock_file(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


_ADVISORY_LOCK_KEY = 0x63686163635F6D67
_POLL_SECONDS = 0.5
_WAIT_LOG_SECONDS = 10


class MigrationLockTimeout(RuntimeError):
    pass


@contextlib.asynccontextmanager
async def migration_lock(engine: Engine, logger, timeout: float) -> AsyncGenerator[None]:
    """Hold ChaCC's migration lock for the block. Raises MigrationLockTimeout."""
    lock = _lock_for(engine)
    if lock is None:
        yield
        return

    await _acquire(lock, logger, timeout)
    try:
        yield
    finally:
        await asyncio.to_thread(lock.release)


async def _acquire(lock, logger, timeout: float) -> None:
    started = time.monotonic()
    next_log = started
    while not await asyncio.to_thread(lock.try_acquire):
        waited = time.monotonic() - started
        if waited >= timeout:
            raise MigrationLockTimeout(
                f"Another ChaCC process has been migrating the database for over "
                f"{timeout:.0f} s ({lock.description}). Not migrating; restart once it is "
                "done, or raise MIGRATION_LOCK_TIMEOUT."
            )
        if time.monotonic() >= next_log:
            logger.info(f"Waiting for another ChaCC process to finish migrating ({waited:.0f} s)")
            next_log += _WAIT_LOG_SECONDS
        await asyncio.sleep(_POLL_SECONDS)


def _lock_for(engine: Engine):
    if engine.dialect.name == "postgresql":
        return _AdvisoryLock(engine)
    if engine.dialect.name == "sqlite":
        database = engine.url.database
        if database and database != ":memory:" and not database.startswith("file::memory:"):
            return _FileLock(f"{os.path.abspath(database)}.migration.lock")
    return None


class _AdvisoryLock:
    description = "PostgreSQL advisory lock"

    def __init__(self, engine: Engine):
        self._engine = engine
        self._conn: Connection | None = None

    def try_acquire(self) -> bool:
        conn = self._engine.connect()
        try:
            acquired = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
            ).scalar()
            conn.commit()
        except Exception:
            conn.close()
            raise
        if acquired:
            self._conn = conn
        else:
            conn.close()
        return bool(acquired)

    def release(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            conn.commit()
            conn.close()
        except Exception:
            conn.invalidate()
            raise


class _FileLock:
    def __init__(self, path: str):
        self.path = path
        self.description = f"lock file {path}"
        self._fd: int | None = None

    def try_acquire(self) -> bool:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        if _try_lock_file(fd):
            self._fd = fd
            return True
        os.close(fd)
        return False

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock_file(fd)
        finally:
            os.close(fd)
