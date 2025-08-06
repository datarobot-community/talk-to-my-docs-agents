# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from core.persistent_fs.dr_file_system import DRFileSystem, calculate_checksum


def _prepare_persistence_storage(
    engine: AsyncEngine,
) -> tuple[DRFileSystem, str] | tuple[None, None]:
    # echeck if all env variables are present
    expected_envs = ["DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN", "APPLICATION_ID"]
    if any(not os.environ.get(env_name) for env_name in expected_envs):
        return None, None

    if "sqlite" not in engine.url.drivername:
        return None, None
    if not engine.url.database or ":memory:" == engine.url.database:
        return None, None

    file_path = engine.url.database
    persistent_fs = DRFileSystem()
    return persistent_fs, file_path


class DBCtx:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

        self._session = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            class_=AsyncSession,
            bind=engine,
            expire_on_commit=False,
        )

        self._persistence_fs: DRFileSystem | None
        self._db_path: str | None
        self._persistence_fs, self._db_path = _prepare_persistence_storage(engine)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        checksum: bytes | None = None
        if self._persistence_fs and self._persistence_fs.exists(self._db_path):
            self._persistence_fs.get(self._db_path, self._db_path)
            checksum = calculate_checksum(cast(str, self._db_path))

        async with self._session() as session:
            yield session

        if self._persistence_fs:
            new_checksum = calculate_checksum(cast(str, self._db_path))
            if new_checksum != checksum:
                self._persistence_fs.put(self._db_path, self._db_path)

    async def shutdown(self) -> None:
        """
        Dispose of the engine and close all pooled connections.
        Call this on application shutdown.
        """
        await self.engine.dispose()


async def create_db_ctx(db_url: str, log_sql_stmts: bool = False) -> DBCtx:
    async_engine = create_async_engine(
        db_url,
        echo=log_sql_stmts,
    )

    async with async_engine.begin() as conn:
        # testing DB credentials...
        await conn.execute(text("select '1'"))

        await conn.run_sync(
            SQLModel.metadata.create_all
        )  # create_all is a blocking method

    return DBCtx(async_engine)
