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
import uuid as uuidpkg
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel, select

from app.db import DBCtx

if TYPE_CHECKING:
    from app.knowledge_bases import KnowledgeBase
from app.knowledge_bases import KnowledgeBaseRepository
from app.users.user import User


class File(SQLModel, table=True):
    """Files uploaded or imported from various sources."""

    id: int | None = Field(default=None, primary_key=True, unique=True)
    uuid: uuidpkg.UUID = Field(default_factory=uuidpkg.uuid4, index=True, unique=True)

    # File information
    filename: str = Field(..., min_length=1, max_length=255)
    source: str = Field(
        ..., min_length=1, max_length=100
    )  # OAuth provider type or 'local'
    file_path: str | None = Field(
        default=None, max_length=500
    )  # Local file path if uploaded
    external_id: str | None = Field(
        default=None, max_length=255
    )  # External file ID (Google Drive, Box, etc.)
    mime_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0)
    size_tokens: int = Field(default=0, ge=0)
    added: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Optional attachment to a knowledge base
    knowledge_base_id: int | None = Field(default=None, foreign_key="knowledgebase.id")

    # Relationships
    owner_id: int = Field(foreign_key="user.id")

    knowledgebase: "KnowledgeBase" = Relationship(back_populates="files")
    owner: "User" = Relationship()


class FileCreate(SQLModel):
    """Schema for creating a new file."""

    filename: str = Field(..., min_length=1, max_length=255)
    source: str = Field(..., min_length=1, max_length=100)
    file_path: str | None = Field(default=None, max_length=500)
    external_id: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0)
    size_tokens: int = Field(default=0, ge=0)
    knowledge_base_id: int | None = Field(
        default=None
    )  # Optional knowledge base attachment


class FileUpdate(SQLModel):
    """Schema for updating a file."""

    filename: str | None = Field(default=None, min_length=1, max_length=255)
    knowledge_base_id: int | None = Field(default=None)
    size_tokens: int | None = Field(default=None, ge=0)


class FileRepository:
    """Repository class to handle file-related database operations."""

    def __init__(self, db: DBCtx):
        self._db = db

    async def create_file(self, file_data: FileCreate, owner_id: int) -> File:
        """Create a new file in the database."""
        file = File(
            **file_data.model_dump(),
            owner_id=owner_id,
        )

        async with self._db.session() as session:
            session.add(file)
            await session.commit()
            await session.refresh(file)

        return file

    async def get_file(
        self,
        file_id: int | None = None,
        file_uuid: uuidpkg.UUID | None = None,
    ) -> File | None:
        """Retrieve a file by its ID or UUID."""
        if file_id is None and file_uuid is None:
            raise ValueError("Either file_id or file_uuid must be provided.")

        async with self._db.session() as session:
            if file_uuid:
                query = await session.exec(select(File).where(File.uuid == file_uuid))
                return query.first()
            else:
                query = await session.exec(select(File).where(File.id == file_id))
                return query.first()

    async def get_files(
        self,
        user: User,
        file_ids: list[uuidpkg.UUID] | None = None,
    ) -> list[File]:
        """Retrieve multiple files by their UUIDs."""
        async with self._db.session() as session:
            if file_ids:
                query = await session.exec(
                    select(File).where(
                        File.uuid.in_(file_ids),  # type: ignore[attr-defined]
                        File.owner_id == user.id,
                    )
                )
                return list(query.all())
            return []

    async def get_kb_files_by_owner(
        self, owner_id: int, knowledge_base_id: int | None = None
    ) -> list[File]:
        """Retrieve all files owned by a user, optionally filtered by base."""
        async with self._db.session() as session:
            if knowledge_base_id is not None:
                query = await session.exec(
                    select(File).where(
                        File.owner_id == owner_id,
                        File.knowledge_base_id == knowledge_base_id,
                    )
                )
            else:
                query = await session.exec(
                    select(File).where(File.owner_id == owner_id)
                )
            return list(query.all())

    async def update_file(
        self, file_id: int, file_data: FileUpdate, owner_id: int
    ) -> File | None:
        """Update a file (must be owned by the user)."""
        async with self._db.session() as session:
            query = await session.exec(
                select(File).where(File.id == file_id, File.owner_id == owner_id)
            )
            file = query.first()

            if not file:
                return None

            # Update only provided fields
            for field, value in file_data.model_dump(exclude_unset=True).items():
                setattr(file, field, value)

            await session.commit()
            await session.refresh(file)
            return file

    async def delete_file(self, file_id: int, owner_id: int) -> bool:
        """Delete a file (must be owned by the user)."""
        async with self._db.session() as session:
            query = await session.exec(
                select(File).where(File.id == file_id, File.owner_id == owner_id)
            )
            file = query.first()

            if not file:
                return False
            if file.knowledgebase:
                knowledge_base_repo = KnowledgeBaseRepository(self._db)
                new_token_count = max(
                    0, file.knowledgebase.token_count - file.size_tokens
                )
                await knowledge_base_repo.update_knowledge_base_token_count(
                    file.knowledgebase, new_token_count
                )

            await session.delete(file)
            await session.commit()
            return True
