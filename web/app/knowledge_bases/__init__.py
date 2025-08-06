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
    from app.files import File
    from app.users.user import User


class KnowledgeBase(SQLModel, table=True):
    """A knowledge base represents a collection of documents from various sources."""

    id: int | None = Field(default=None, primary_key=True, unique=True)
    uuid: uuidpkg.UUID = Field(default_factory=uuidpkg.uuid4, index=True, unique=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # Knowledge Base information
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    token_count: int = Field(default=0, ge=0)
    path: str = Field(..., min_length=1, max_length=500)

    # Relationships
    owner_id: int = Field(foreign_key="user.id")

    owner: "User" = Relationship()
    files: list["File"] = Relationship(
        back_populates="knowledgebase",
        cascade_delete=True,
        sa_relationship_kwargs={"lazy": "joined"},
    )


class KnowledgeBaseCreate(SQLModel):
    """Schema for creating a new knowledge base."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    token_count: int = Field(default=0, ge=0)


class KnowledgeBaseRepository:
    """Repository class to handle knowledge base-related database operations."""

    def __init__(self, db: DBCtx):
        self._db = db

    async def get_knowledge_base(
        self,
        knowledge_base_id: int | None = None,
        knowledge_base_uuid: uuidpkg.UUID | None = None,
    ) -> KnowledgeBase | None:
        """Retrieve a knowledge base by its ID or UUID."""
        if knowledge_base_id is None and knowledge_base_uuid is None:
            raise ValueError(
                "Either knowledge_base_id or knowledge_base_uuid must be provided."
            )
        conditions = []
        if knowledge_base_id is not None:
            conditions.append(KnowledgeBase.id == knowledge_base_id)
        if knowledge_base_uuid is not None:
            conditions.append(KnowledgeBase.uuid == knowledge_base_uuid)
        async with self._db.session() as sess:
            query = await sess.exec(select(KnowledgeBase).where(*conditions))
            return query.first()

    async def list_knowledge_bases_by_owner(self, owner_id: int) -> list[KnowledgeBase]:
        """List all knowledge bases owned by a specific user."""
        async with self._db.session() as sess:
            query = await sess.exec(
                select(KnowledgeBase).where(KnowledgeBase.owner_id == owner_id)
            )
            return list(query.unique().all())

    async def create_knowledge_base(
        self, knowledge_base_data: KnowledgeBaseCreate, owner_id: int
    ) -> KnowledgeBase:
        """Create a new knowledge base in the database."""
        # Create the knowledge base instance first to get the UUID
        knowledge_base = KnowledgeBase(
            title=knowledge_base_data.title,
            description=knowledge_base_data.description,
            token_count=knowledge_base_data.token_count,
            owner_id=owner_id,
            path=knowledge_base_data.path or "",  # Temporary placeholder
        )

        async with self._db.session() as session:
            session.add(knowledge_base)
            await session.flush()  # Flush to get the generated UUID and ID

            # Set the path if not provided
            if not knowledge_base_data.path:
                knowledge_base.path = f"{owner_id}/{knowledge_base.uuid}"

            await session.commit()
            await session.refresh(knowledge_base)

        return knowledge_base

    async def delete_knowledge_base(
        self, knowledge_base_id: int, owner_id: int
    ) -> bool:
        """Delete a knowledge base and all its files (must be owned by the user)."""
        async with self._db.session() as session:
            # First verify the knowledge base exists and is owned by the user
            query = await session.exec(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.owner_id == owner_id,
                )
            )
            knowledge_base = query.first()

            if not knowledge_base:
                return False

            await session.delete(knowledge_base)
            await session.commit()
            return True

    async def update_knowledge_base_token_count(
        self, knowledge_base: KnowledgeBase, token_count: int
    ) -> KnowledgeBase | None:
        """Update the token count for a knowledge base.

        Args:
            knowledge_base: The knowledge base to update
            token_count: The new token count to set
        """
        async with self._db.session() as session:
            if not knowledge_base or not knowledge_base.id:
                return None

            # Requery the knowledge base in the current session to avoid detached instance issues
            query = await session.exec(
                select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base.id)
            )
            kb_in_session = query.first()

            if not kb_in_session:
                return None

            kb_in_session.token_count = token_count
            kb_in_session.updated_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(kb_in_session)
            return kb_in_session
