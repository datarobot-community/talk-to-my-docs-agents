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
import enum
import logging
import uuid as uuidpkg
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, Relationship, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import DBCtx

if TYPE_CHECKING:
    from app.files import File
    from app.users.user import User

logger = logging.getLogger(__name__)


class IndexStatus(str, enum.Enum):
    NOT_INDEXED = "not_indexed"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class RetrievalMode(str, enum.Enum):
    # "keyword" reproduces the ORIGINAL behavior (full document content passed to
    # the agent / keyword scan). "semantic" uses the DataRobot Memory API search.
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


def is_semantic_ready(kb: "KnowledgeBase") -> bool:
    """True when a KB is in semantic mode and its index is READY.

    Both chat retrieval and the /search endpoint gate on this so neither serves a
    partially populated store during a rebuild (the full-replace deletes then
    re-adds, so the index is incomplete until it lands READY).
    """
    return (
        kb.retrieval_mode == RetrievalMode.SEMANTIC
        and kb.index_status == IndexStatus.READY
    )


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
    is_public: bool = Field(default=False, nullable=False)
    index_status: str = Field(default=IndexStatus.NOT_INDEXED, max_length=20)
    # Per-KB retrieval mode. Defaults to KEYWORD so existing KBs (and any KB when
    # the feature is off) behave exactly as the app did originally.
    retrieval_mode: str = Field(default=RetrievalMode.KEYWORD, max_length=16)
    indexed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    # Last indexing error (surfaced to ops/UI when index_status == failed).
    # Vectors live in the DataRobot Memory API keyed by this KB's id, so no
    # per-KB vector-store resource ids are stored on the row.
    last_error: str | None = Field(default=None, max_length=2000)
    # sha256 over the KB's current document set. When a rebuild computes the same
    # fingerprint and the KB is already READY, re-embedding is skipped (no-op
    # rebuild). None until first indexed.
    index_fingerprint: str | None = Field(default=None, max_length=64)
    # Per-document content SHA map {doc_id: sha}, tracked locally because the
    # Memory API cannot be enumerated (50-result cap). Drives incremental
    # indexing: only docs whose sha changed (or were removed) are touched.
    index_doc_shas: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )

    # Relationships
    owner_id: int = Field(foreign_key="user.id")

    owner: "User" = Relationship(sa_relationship_kwargs={"lazy": "joined"})
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
    is_public: bool = Field(default=False)
    retrieval_mode: str = Field(default=RetrievalMode.KEYWORD, max_length=16)


class KnowledgeBaseUpdate(SQLModel):
    """Schema for updating an existing knowledge base. All fields optional."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    token_count: int | None = Field(default=None, ge=0)
    is_public: bool | None = Field(default=None)
    retrieval_mode: str | None = Field(default=None, max_length=16)


class KnowledgeBaseRepository:
    """Repository class to handle knowledge base-related database operations."""

    def __init__(self, db: DBCtx):
        self._db = db

    async def get_knowledge_base(
        self,
        user: "User",
        knowledge_base_id: int | None = None,
        knowledge_base_uuid: uuidpkg.UUID | None = None,
    ) -> KnowledgeBase | None:
        """Retrieve a knowledge base by its ID or UUID.

        Args:
            user: Current user for authorization/sharing checks
            knowledge_base_id: Numeric DB id of the knowledge base
            knowledge_base_uuid: UUID of the knowledge base
        """
        if knowledge_base_id is None and knowledge_base_uuid is None:
            raise ValueError(
                "Either knowledge_base_id or knowledge_base_uuid must be provided."
            )
        conditions = [
            KnowledgeBase.is_public.is_(True) | (KnowledgeBase.owner_id == user.id),  # type: ignore[attr-defined]
        ]
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
                select(KnowledgeBase).where(
                    (KnowledgeBase.owner_id == owner_id)
                    | KnowledgeBase.is_public.is_(True)  # type: ignore[attr-defined]
                )
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
            is_public=knowledge_base_data.is_public,
            retrieval_mode=knowledge_base_data.retrieval_mode,
        )

        async with self._db.session(writable=True) as session:
            session.add(knowledge_base)
            await session.flush()  # Flush to get the generated UUID and ID

            # Set the path if not provided
            if not knowledge_base_data.path:
                knowledge_base.path = f"{owner_id}/{knowledge_base.uuid}"

            await self._db.commit(session)
            await session.refresh(knowledge_base)

        return knowledge_base

    async def delete_knowledge_base(
        self, knowledge_base_id: int, owner_id: int
    ) -> bool:
        """Delete a knowledge base and all its files (must be owned by the user)."""
        async with self._db.session(writable=True) as session:
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
            await self._db.commit(session)
            return True

    async def update_knowledge_base(
        self,
        knowledge_base_id: int,
        owner_id: int,
        update: "KnowledgeBaseUpdate",
    ) -> KnowledgeBase | None:
        """Update a knowledge base (must be owned by the user)."""
        async with self._db.session(writable=True) as session:
            query = await session.exec(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.owner_id == owner_id,
                )
            )
            kb = query.first()
            if not kb:
                return None

            for field, value in update.model_dump(exclude_unset=True).items():
                if value is not None:
                    setattr(kb, field, value)
            kb.updated_at = datetime.now(timezone.utc)
            await self._db.commit(session)
            await session.refresh(kb)
            return kb

    async def update_knowledge_base_token_count(
        self, knowledge_base: KnowledgeBase, token_count: int
    ) -> KnowledgeBase | None:
        """Update the token count for a knowledge base.

        Args:
            knowledge_base: The knowledge base to update
            token_count: The new token count to set
        """
        logging.debug(
            "Updating token count (kb_id=%d, token_count=%c).",
            knowledge_base and knowledge_base.id,
            token_count,
        )
        async with self._db.session(writable=True) as session:
            kb_in_session = await self._update_knowledge_base_token_count_in_session(
                knowledge_base, token_count, session
            )

            logging.debug(
                "Committing update to knowledge base (kb_id=%d).",
                kb_in_session and kb_in_session.id,
            )
            await self._db.commit(session)
            await session.refresh(kb_in_session)
            return kb_in_session

    async def _update_knowledge_base_token_count_in_session(
        self, knowledge_base: KnowledgeBase, token_count: int, session: AsyncSession
    ) -> KnowledgeBase | None:
        # Early return if token count hasn't changed
        if knowledge_base.token_count == token_count:
            return knowledge_base

        if not knowledge_base or not knowledge_base.id:
            return None

        # Requery the knowledge base in the current session to avoid detached instance issues
        query = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base.id)
        )
        kb_in_session: KnowledgeBase | None = query.first()

        if not kb_in_session:
            return None

        kb_in_session.token_count = token_count
        kb_in_session.updated_at = datetime.now(timezone.utc)

        return kb_in_session
