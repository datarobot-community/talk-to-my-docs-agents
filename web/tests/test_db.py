# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.utils.rw_lock import MockReadWriteLock, ThreadReadWriteLock
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel, select

from app.db import DBCtx


class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str


@pytest.fixture
def in_memory_engine() -> AsyncEngine:
    return create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture
def file_engine(tmp_path: Path) -> AsyncEngine:
    db_path = tmp_path / "test.db"
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}")


@pytest.fixture
async def db_ctx(in_memory_engine: AsyncEngine) -> DBCtx:
    """DBCtx backed by an in-memory SQLite database with tables created."""
    ctx = DBCtx(in_memory_engine)
    async with ctx.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return ctx


class TestDBCtxLockAssignment:
    """Verify _rw_lock is set to the correct implementation based on persistence."""

    def test_mock_lock_without_persistence(self, in_memory_engine: AsyncEngine) -> None:
        """In-memory DB has no persistence, so _rw_lock should be a no-op mock."""
        ctx = DBCtx(in_memory_engine)
        assert isinstance(ctx._rw_lock, MockReadWriteLock)

    def test_real_lock_with_persistence(self, file_engine: AsyncEngine) -> None:
        """File-backed DB with DR env vars should get a real ThreadReadWriteLock."""
        with (
            patch("app.db.all_env_variables_present", return_value=True),
            patch("app.db.LegacyDRFileSystem"),
        ):
            ctx = DBCtx(file_engine)
            assert isinstance(ctx._rw_lock, ThreadReadWriteLock)

    def test_no_dangling_lock_attr(self, file_engine: AsyncEngine) -> None:
        """Regression: the old typo created a stale _lock attribute."""
        with (
            patch("app.db.all_env_variables_present", return_value=True),
            patch("app.db.LegacyDRFileSystem"),
        ):
            ctx = DBCtx(file_engine)
            assert not hasattr(ctx, "_lock")


class TestDBCtxSessions:
    """Verify read/write sessions acquire the correct lock and enforce access rules."""

    async def test_read_session_acquires_read_lock(self, db_ctx: DBCtx) -> None:
        """_read_session should enter the rw_lock's async_read_lock context."""
        db_ctx._rw_lock = MagicMock(spec=MockReadWriteLock)
        db_ctx._rw_lock.async_read_lock = MagicMock(return_value=AsyncMock())

        async with db_ctx.session(writable=False) as _session:
            pass

        db_ctx._rw_lock.async_read_lock.assert_called_once()

    async def test_write_session_acquires_write_lock(self, db_ctx: DBCtx) -> None:
        """_write_session should enter the rw_lock's async_write_lock context."""
        db_ctx._rw_lock = MagicMock(spec=MockReadWriteLock)
        db_ctx._rw_lock.async_write_lock = MagicMock(return_value=AsyncMock())

        async with db_ctx.session(writable=True) as _session:
            pass

        db_ctx._rw_lock.async_write_lock.assert_called_once()

    async def test_read_session_blocks_writes(self, db_ctx: DBCtx) -> None:
        """A read session should raise RuntimeError if code tries to modify data."""
        async with db_ctx.session(writable=False) as session:
            session.add(Item(name="should fail"))
            with pytest.raises(RuntimeError, match="read-only"):
                await session.flush()

    async def test_write_session_allows_writes(self, db_ctx: DBCtx) -> None:
        """A write session should allow normal inserts and commits."""
        async with db_ctx.session(writable=True) as session:
            session.add(Item(name="test"))
            await session.commit()


class TestDBCtxSessionScope:
    """Verify session_scope batches repository calls onto a single session."""

    async def test_session_scope_shares_one_session(self, db_ctx: DBCtx) -> None:
        """All session() calls within a session_scope should share the same session."""
        async with db_ctx.session_scope() as scoped_session:
            async with db_ctx.session(writable=True) as inner_session:
                assert inner_session is scoped_session

    async def test_session_scope_cannot_nest(self, db_ctx: DBCtx) -> None:
        """Nesting session_scope calls should raise RuntimeError."""
        async with db_ctx.session_scope():
            with pytest.raises(RuntimeError, match="cannot be nested"):
                async with db_ctx.session_scope():
                    pass

    async def test_commit_flushes_inside_scope(self, db_ctx: DBCtx) -> None:
        """db.commit() should flush (not commit) the shared session while scoped."""
        async with db_ctx.session_scope() as session:
            session.add(Item(name="scoped"))
            await db_ctx.commit(session)
            # Flushed but not yet committed: still visible within the same session.
            result = await session.exec(select(Item).where(Item.name == "scoped"))
            assert result.first() is not None

    async def test_commit_persists_after_scope_exit(self, db_ctx: DBCtx) -> None:
        """The batched writes should be durably committed once the scope exits."""
        async with db_ctx.session_scope() as session:
            session.add(Item(name="persisted"))
            await db_ctx.commit(session)

        async with db_ctx.session() as session:
            result = await session.exec(select(Item).where(Item.name == "persisted"))
            assert result.first() is not None
