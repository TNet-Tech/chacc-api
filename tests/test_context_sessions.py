"""Session helpers in chacc_api.database close what they open, and the old context
properties still work but are deprecated."""

import asyncio
import gc
import logging

import pytest
from sqlalchemy import text

from chacc_api.database import (
    async_session,
    get_async_db,
    get_db,
    session,
    with_async_session,
    with_session,
)
from src import database
from src.core_services import BackboneContext


@pytest.fixture
def tracked(monkeypatch):
    """Record every session the helpers open."""
    opened = []

    def track(factory):
        def make():
            s = factory()
            opened.append(s)
            return s

        return make

    monkeypatch.setattr(database, "AsyncSessionLocal", track(database.AsyncSessionLocal))
    monkeypatch.setattr(database, "SessionLocal", track(database.SessionLocal))
    return opened


def is_closed(s):
    # A closed session holds no connection and no transaction.
    sync = getattr(s, "sync_session", s)
    return sync.get_transaction() is None


def test_async_session_open_inside_closed_after(tracked):
    async def run():
        async with async_session() as db:
            gc.collect()
            assert (await db.execute(text("select 1"))).scalar() == 1
            assert not is_closed(db)
        assert is_closed(db)

    asyncio.run(run())
    assert len(tracked) == 1


def test_async_session_closes_on_error(tracked):
    async def run():
        with pytest.raises(ValueError):
            async with async_session() as db:
                await db.execute(text("select 1"))
                raise ValueError("boom")

    asyncio.run(run())
    assert is_closed(tracked[0])


def test_sync_session(tracked):
    with session() as db:
        assert db.execute(text("select 1")).scalar() == 1
    assert is_closed(db)


class ItemService:
    @with_async_session
    async def read(self, value, *, db):
        assert (await db.execute(text("select 1"))).scalar() == 1
        return db, value

    @with_async_session
    async def two_steps(self, *, db):
        inner, _ = await self.read(1, db=db)  # same session, same transaction
        return db, inner

    @with_session
    def read_sync(self, *, db):
        db.execute(text("select 1"))
        return db

    @with_session
    async def read_sync_from_async(self, *, db):
        return db


def test_decorators_open_and_close_per_call(tracked):
    service = ItemService()

    async def run():
        db1, value = await service.read(7)
        db2, _ = await service.read(8)
        assert value == 7 and db1 is not db2
        assert is_closed(db1) and is_closed(db2)
        assert is_closed(await service.read_sync_from_async())

    asyncio.run(run())
    assert is_closed(service.read_sync())
    assert len(tracked) == 4


def test_decorator_reuses_given_session(tracked):
    service = ItemService()

    async def run():
        async with async_session() as db:
            await db.execute(text("select 1"))
            used, _ = await service.read(1, db=db)
            assert used is db and not is_closed(db)
        outer, inner = await service.two_steps()
        assert outer is inner

    asyncio.run(run())
    assert len(tracked) == 2


def test_decorator_on_plain_function_and_error(tracked):
    @with_async_session
    async def fail(*, db):
        await db.execute(text("select 1"))
        raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(fail())
    assert is_closed(tracked[0])


def test_with_async_session_rejects_sync_function():
    with pytest.raises(TypeError, match="with_session"):

        @with_async_session
        def nope(*, db):
            return db


def test_route_dependencies_close(tracked):
    async def run():
        gen = get_async_db()
        db = await anext(gen)
        await db.execute(text("select 1"))
        await gen.aclose()
        assert is_closed(db)

        gen = get_db()
        sync_db = await anext(gen)
        await gen.aclose()
        assert is_closed(sync_db)

    asyncio.run(run())


def test_context_properties_still_work_but_are_deprecated(caplog):
    ctx = BackboneContext(None, None, logging.getLogger("t"), get_db, get_async_db)
    with pytest.warns(DeprecationWarning, match="chacc_api.database.get_async_db"):
        assert ctx.get_db_async is get_async_db
    with pytest.warns(DeprecationWarning, match="chacc_api.database.get_db"):
        assert ctx.get_db is get_db
