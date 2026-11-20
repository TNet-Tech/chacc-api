"""
The migration lock: one process migrates at a time, a crashed holder doesn't
block the others, and several processes migrating the same database at once
apply each change exactly once.

Runs on SQLite, and on PostgreSQL when CHACC_TEST_POSTGRES_URL is set (see
test_renames.py).
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from src.migration.lock import MigrationLockTimeout, migration_lock
from src.migration.tracker import TRACKER_TABLE

HELPER = os.path.join(os.path.dirname(__file__), "concurrent_migrate.py")
POSTGRES_URL = os.environ.get("CHACC_TEST_POSTGRES_URL")
WORKERS = 6


class _Log:
    def __init__(self):
        self.lines = []

    def info(self, message):
        self.lines.append(message)


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'app.db'}"
        return

    if not POSTGRES_URL:
        pytest.skip("CHACC_TEST_POSTGRES_URL is not set")
    name = f"chacc_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    yield admin.url.set(database=name).render_as_string(hide_password=False)
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.dispose()


@pytest.fixture
def engine(database_url):
    eng = create_engine(database_url)
    yield eng
    eng.dispose()


def test_a_second_holder_waits_and_times_out(engine):
    async def scenario():
        async with migration_lock(engine, _Log(), timeout=5):
            with pytest.raises(MigrationLockTimeout, match="MIGRATION_LOCK_TIMEOUT"):
                async with migration_lock(engine, _Log(), timeout=1):
                    pass

    asyncio.run(scenario())


def test_the_lock_is_free_again_after_release(engine):
    async def scenario():
        async with migration_lock(engine, _Log(), timeout=5):
            pass
        async with migration_lock(engine, _Log(), timeout=1):
            pass

    asyncio.run(scenario())


def test_waiting_is_logged(engine):
    log = _Log()

    async def scenario():
        async with migration_lock(engine, _Log(), timeout=5):
            with pytest.raises(MigrationLockTimeout):
                async with migration_lock(engine, log, timeout=1):
                    pass

    asyncio.run(scenario())
    assert any("Waiting for another ChaCC process" in line for line in log.lines)


def test_a_crashed_holder_does_not_block_others(engine, database_url):
    holder = subprocess.Popen(
        [sys.executable, HELPER, database_url, "hold"], stdout=subprocess.PIPE, text=True
    )
    try:
        assert json.loads(holder.stdout.readline())["status"] == "holding"

        async def blocked():
            async with migration_lock(engine, _Log(), timeout=1):
                pass

        with pytest.raises(MigrationLockTimeout):
            asyncio.run(blocked())

        holder.send_signal(signal.SIGKILL)  # no cleanup code runs
        holder.wait(timeout=10)

        async def free():
            async with migration_lock(engine, _Log(), timeout=5):
                pass

        asyncio.run(free())
    finally:
        holder.kill()
        holder.wait(timeout=10)


def run_workers(database_url: str, version: int) -> list[dict]:
    start_at = time.time() + 1.5  # all start migrating at the same moment
    workers = [
        subprocess.Popen(
            [sys.executable, HELPER, database_url, str(start_at), str(version)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for _ in range(WORKERS)
    ]
    results = []
    for worker in workers:
        out, _ = worker.communicate(timeout=120)
        results.append(json.loads(out.strip().splitlines()[-1]))
    return results


def test_concurrent_workers_apply_each_change_once(engine, database_url):
    first = run_workers(database_url, version=1)
    assert [r["status"] for r in first].count("success") == 1, first
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO shelves (id) VALUES (1)"))
        conn.execute(text("INSERT INTO books (id, shelf_id, name) VALUES (1, 1, 'Dune')"))

    upgrade = run_workers(database_url, version=2)

    assert all(r["status"] in ("success", "up_to_date") for r in upgrade), upgrade
    assert [r["status"] for r in upgrade].count("success") == 1, upgrade
    inspector = inspect(engine)
    assert {c["name"] for c in inspector.get_columns("books")} == {
        "id",
        "shelf_id",
        "title",
        "isbn",
    }
    assert [fk["referred_table"] for fk in inspector.get_foreign_keys("books")] == ["shelves"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM books")).scalar() == "Dune"
        log = [r[0] for r in conn.execute(text(f"SELECT description FROM {TRACKER_TABLE}"))]
    for change in ("rename_column on books", "add_column on books", "create_foreign_key on books"):
        assert log.count(change) == 1, log
