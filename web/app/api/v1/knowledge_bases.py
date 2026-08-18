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
import asyncio
import logging
import uuid as uuidpkg
from datetime import datetime, timezone

from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.v1.schema import ErrorCodes, ErrorSchema
from app.auth.ctx import must_get_auth_ctx
from app.files import File as DBFile
from app.files import FileRepository
from app.files.contents import get_or_create_encoded_content
from app.knowledge_bases import (
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseRepository,
    KnowledgeBaseUpdate,
    RetrievalMode,
    is_semantic_ready,
)
from app.users.user import User, UserRepository

logger = logging.getLogger(name=__name__)


class KnowledgeBaseFileSchema(BaseModel):
    uuid: uuidpkg.UUID
    filename: str
    file_path: str
    size_tokens: int = Field(default=0, ge=0)
    source: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_uuid: uuidpkg.UUID
    encoded_content: dict[int, str] | None = None  # Page number to text mapping

    @classmethod
    def from_file(
        cls,
        file: DBFile,
        owner_uuid: uuidpkg.UUID | None = None,
        encoded_content: dict[int, str] | None = None,
    ) -> "KnowledgeBaseFileSchema":
        # If owner_uuid is provided, use it; otherwise try to get it from the relationship
        if owner_uuid is None:
            try:
                owner_uuid = file.owner.uuid
            except Exception:
                # If owner relationship is not available, we'll need to pass it explicitly
                raise ValueError(
                    "owner_uuid must be provided when file.owner is not accessible"
                )

        return cls(
            uuid=file.uuid,
            filename=file.filename,
            file_path=file.file_path or "",
            size_tokens=file.size_tokens,
            source=file.source,
            created_at=file.added,
            owner_uuid=owner_uuid,
            encoded_content=encoded_content,
        )


class KnowledgeBaseSchema(BaseModel):
    uuid: uuidpkg.UUID
    title: str
    description: str
    token_count: int
    path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_uuid: uuidpkg.UUID
    is_public: bool
    can_edit: bool
    retrieval_mode: str = "keyword"
    index_status: str = "not_indexed"
    last_error: str | None = None

    files: list[KnowledgeBaseFileSchema] = Field(default_factory=list)

    @classmethod
    def from_knowledge_base(
        cls,
        current_user: User,
        knowledge_base: KnowledgeBase,
        owner_uuid: uuidpkg.UUID | None = None,
        files_with_content: dict[str, dict[int, str]] | None = None,
    ) -> "KnowledgeBaseSchema":
        # If owner_uuid is provided, use it; otherwise try to get it from the relationship
        if owner_uuid is None:
            try:
                owner_uuid = knowledge_base.owner.uuid
            except Exception:
                logger.exception("No owner found for knowledge base")
                raise ValueError(
                    "owner_uuid must be provided when knowledge_base.owner is not accessible"
                )

        # Create file schemas with optional encoded content
        file_schemas = []
        for file in knowledge_base.files:
            encoded_content = None
            if files_with_content and str(file.uuid) in files_with_content:
                encoded_content = files_with_content[str(file.uuid)]

            file_schemas.append(
                KnowledgeBaseFileSchema.from_file(
                    file, owner_uuid=owner_uuid, encoded_content=encoded_content
                )
            )

        return cls(
            uuid=knowledge_base.uuid,
            title=knowledge_base.title,
            description=knowledge_base.description,
            token_count=knowledge_base.token_count,
            path=knowledge_base.path,
            created_at=knowledge_base.created_at,
            updated_at=knowledge_base.updated_at,
            owner_uuid=owner_uuid,
            is_public=knowledge_base.is_public,
            can_edit=owner_uuid == current_user.uuid,
            retrieval_mode=knowledge_base.retrieval_mode,
            index_status=knowledge_base.index_status,
            last_error=knowledge_base.last_error,
            files=file_schemas,
        )


class KnowledgeBaseListSchema(BaseModel):
    knowledge_bases: list[KnowledgeBaseSchema]


class KnowledgeBaseCreateRequestSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    token_count: int = Field(default=0, ge=0)
    is_public: bool = Field(default=False)
    # None => resolve to the configured default (semantic when the feature is on,
    # else keyword). Explicit "semantic"/"keyword" is honored.
    retrieval_mode: str | None = Field(default=None)


class KnowledgeBaseUpdateRequestSchema(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    token_count: int | None = Field(default=None, ge=0)
    is_public: bool | None = Field(default=None)
    retrieval_mode: str | None = Field(default=None)


knowledge_base_router = APIRouter(tags=["Knowledge Bases"])

# Strong references to fire-and-forget vector-cleanup tasks (asyncio keeps only
# weak refs; without this a pending cleanup could be garbage-collected).
_VECTOR_CLEANUP_TASKS: set[asyncio.Task[None]] = set()


def _resolve_retrieval_mode(
    requested: str | None, *, feature_on: bool, config_default: str
) -> str:
    """Resolve a knowledge base's retrieval mode.

    - ``None`` (unset): resolve to the configured default when the feature is on,
      else keyword. The config default is normalized against the enum so a
      misconfigured ``VDB_DEFAULT_RETRIEVAL_MODE`` (e.g. a typo like "sematic")
      cannot create a KB with an invalid mode.
    - explicit value: must be a valid enum member, else ``ValueError`` (the caller
      returns 422); forced to keyword when the feature is unavailable.
    """
    if requested is None:
        if feature_on and config_default == RetrievalMode.SEMANTIC:
            return RetrievalMode.SEMANTIC
        return RetrievalMode.KEYWORD
    if requested not in (RetrievalMode.SEMANTIC, RetrievalMode.KEYWORD):
        raise ValueError(requested)
    return requested if feature_on else RetrievalMode.KEYWORD


async def get_knowledge_base_schema(
    knowledge_base_uuid: uuidpkg.UUID,
    knowledge_base_repo: KnowledgeBaseRepository,
    current_user: User,
    include_content: bool = False,
    file_repo: FileRepository | None = None,
) -> KnowledgeBaseSchema:
    knowledge_base = await knowledge_base_repo.get_knowledge_base(
        current_user,
        knowledge_base_uuid=knowledge_base_uuid,
    )
    if not knowledge_base:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"Base with UUID {knowledge_base_uuid} not found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.model_dump()
        )

    # Rely on repository-level visibility filtering (owner or public).
    # If the repo returns None, we return 404 above; no separate API-level 403.

    # Get encoded content for files if requested
    files_with_content = None
    if include_content and file_repo:
        files_with_content = {}
        for file in knowledge_base.files:
            if file.file_path:
                encoded_content = await get_or_create_encoded_content(
                    file=file,
                    file_repo=file_repo,
                    knowledge_base=knowledge_base,
                    knowledge_base_repo=knowledge_base_repo,
                )
                if encoded_content:
                    files_with_content[str(file.uuid)] = encoded_content

    return KnowledgeBaseSchema.from_knowledge_base(
        current_user,
        knowledge_base,
        owner_uuid=current_user.uuid,
        files_with_content=files_with_content,
    )


@knowledge_base_router.get("/knowledge-bases/", responses={401: {"model": ErrorSchema}})
async def list_knowledge_bases(
    request: Request, auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> KnowledgeBaseListSchema:
    """
    List all knowledge bases accessible to the current user (owned by them or public).
    """
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    user_repo: UserRepository = request.app.state.deps.user_repo
    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    knowledge_bases = await knowledge_base_repo.list_knowledge_bases_by_owner(
        owner_id=int(auth_ctx.user.id)
    )

    # Get all unique owner IDs from the knowledge bases
    owner_ids = {kb.owner_id for kb in knowledge_bases}

    # Fetch all owners at once
    owners = {}
    for owner_id in owner_ids:
        if owner_id:  # owner_id could be None in some edge cases
            owner = await user_repo.get_user(user_id=owner_id)
            if owner:
                owners[owner_id] = owner

    return KnowledgeBaseListSchema(
        knowledge_bases=[
            KnowledgeBaseSchema.from_knowledge_base(
                current_user=current_user,
                knowledge_base=knowledge_base,
                owner_uuid=owners[knowledge_base.owner_id].uuid
                if knowledge_base.owner_id and knowledge_base.owner_id in owners
                else None,
            )
            for knowledge_base in knowledge_bases
        ]
    )


@knowledge_base_router.post(
    "/knowledge-bases/",
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorSchema}},
)
async def create_knowledge_base(
    request: Request,
    payload: KnowledgeBaseCreateRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> KnowledgeBaseSchema:
    """
    Create a new base.
    """
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    user_repo: UserRepository = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    # Resolve the retrieval mode. None means "unset" -> use the default. An
    # explicit invalid value is rejected (mirroring the update endpoint) rather
    # than silently coerced, which could enable semantic mode and billable
    # indexing the user never requested.
    deps = request.app.state.deps
    feature_on = bool(deps.config.vdb_enabled and deps.vector_store is not None)
    try:
        resolved_mode = _resolve_retrieval_mode(
            payload.retrieval_mode,
            feature_on=feature_on,
            config_default=deps.config.vdb_default_retrieval_mode,
        )
    except ValueError:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=(
                f"Invalid retrieval_mode {payload.retrieval_mode!r}; "
                "expected 'semantic' or 'keyword'."
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err.model_dump(),
        )

    knowledge_base_data = KnowledgeBaseCreate(
        title=payload.title,
        description=payload.description,
        path=payload.path,
        token_count=payload.token_count,
        is_public=payload.is_public,
        retrieval_mode=resolved_mode,
    )

    knowledge_base = await knowledge_base_repo.create_knowledge_base(
        knowledge_base_data, owner_id=int(auth_ctx.user.id)
    )

    logger.info(
        "created new base",
        extra={"base_id": knowledge_base.id, "owner_id": auth_ctx.user.id},
    )

    return KnowledgeBaseSchema.from_knowledge_base(
        current_user=current_user,
        knowledge_base=knowledge_base,
        owner_uuid=current_user.uuid,
    )


@knowledge_base_router.get(
    "/knowledge-bases/{knowledge_base_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def get_knowledge_base(
    request: Request,
    knowledge_base_uuid: uuidpkg.UUID,
    include_content: bool = False,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> KnowledgeBaseSchema:
    """
      Get a specific knowledge base by UUID.

    Args:
          knowledge_base_uuid: UUID of the base to retrieve
          include_content: Whether to include encoded document content for files in the response
    """
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    user_repo: UserRepository = request.app.state.deps.user_repo
    file_repo: FileRepository = request.app.state.deps.file_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")
    return await get_knowledge_base_schema(
        knowledge_base_uuid=knowledge_base_uuid,
        knowledge_base_repo=knowledge_base_repo,
        current_user=current_user,
        include_content=include_content,
        file_repo=file_repo,
    )


@knowledge_base_router.put(
    "/knowledge-bases/{knowledge_base_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def update_knowledge_base(
    request: Request,
    knowledge_base_uuid: uuidpkg.UUID,
    payload: KnowledgeBaseUpdateRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> KnowledgeBaseSchema:
    """Update a knowledge base's editable properties."""
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    user_repo: UserRepository = request.app.state.deps.user_repo

    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    knowledge_base = await knowledge_base_repo.get_knowledge_base(
        current_user,
        knowledge_base_uuid=knowledge_base_uuid,
    )
    if not knowledge_base:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"Knowledge base with UUID {knowledge_base_uuid} not found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.model_dump()
        )

    if knowledge_base.owner_id != int(auth_ctx.user.id):
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Access denied",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.model_dump()
        )

    # Validate retrieval_mode like create does: reject unknown values, and force
    # keyword when the semantic feature is unavailable (no flag / no store).
    deps = request.app.state.deps
    if payload.retrieval_mode is not None:
        if payload.retrieval_mode not in (
            RetrievalMode.SEMANTIC,
            RetrievalMode.KEYWORD,
        ):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message=(
                    f"Invalid retrieval_mode {payload.retrieval_mode!r}; "
                    "expected 'semantic' or 'keyword'."
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.model_dump(),
            )
        feature_on = bool(deps.config.vdb_enabled and deps.vector_store is not None)
        if not feature_on:
            payload.retrieval_mode = RetrievalMode.KEYWORD

    # Capture the mode BEFORE the update so we only rebuild on a real
    # keyword -> semantic transition (not on every save of a semantic KB).
    previous_mode = knowledge_base.retrieval_mode

    update_model = KnowledgeBaseUpdate(**payload.model_dump(exclude_unset=True))
    updated = await knowledge_base_repo.update_knowledge_base(
        knowledge_base_id=knowledge_base.id if knowledge_base.id is not None else 0,
        owner_id=int(auth_ctx.user.id),
        update=update_model,
    )
    if not updated:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Failed to update knowledge base or access denied",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.model_dump()
        )

    # If the user just switched this KB to semantic mode, kick off a one-time
    # index build so its documents become searchable. Compare against the mode
    # BEFORE the update: re-saving an already-semantic KB (e.g. a title edit)
    # must not trigger a full billable rebuild. (Switching to keyword needs no
    # work — existing vectors are simply left unused.)
    switched_to_semantic = (
        previous_mode != RetrievalMode.SEMANTIC
        and updated.retrieval_mode == RetrievalMode.SEMANTIC
    )
    if switched_to_semantic:
        from app.api.v1.files import _schedule_kb_reindex

        await _schedule_kb_reindex(request, knowledge_base_uuid, current_user)

    return KnowledgeBaseSchema.from_knowledge_base(
        current_user=current_user, knowledge_base=updated
    )


@knowledge_base_router.delete(
    "/knowledge-bases/{knowledge_base_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def delete_base(
    request: Request,
    knowledge_base_uuid: uuidpkg.UUID,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> dict[str, str]:
    """
    Delete a base by UUID.
    """
    knowledge_base_repo = request.app.state.deps.knowledge_base_repo
    user_repo: UserRepository = request.app.state.deps.user_repo

    # Get current user
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    # First get the base to find the ID
    knowledge_base = await knowledge_base_repo.get_knowledge_base(
        current_user,
        knowledge_base_uuid=knowledge_base_uuid,
    )

    if not knowledge_base:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"Knowledge base with UUID {knowledge_base_uuid} not found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.model_dump()
        )

    # Check ownership
    if knowledge_base.owner_id != int(auth_ctx.user.id):
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"Knowledge base with UUID {knowledge_base_uuid} does not belong to the user to delete",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.model_dump()
        )

    kb_pk = knowledge_base.id

    success = await knowledge_base_repo.delete_knowledge_base(
        knowledge_base.id, owner_id=int(auth_ctx.user.id)
    )

    if not success:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Failed to delete knowledge base or access denied",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.model_dump()
        )

    # Best-effort removal of this KB's vectors from the Memory API. Fired as a
    # background task so a slow/unavailable Memory API (the transport retries
    # with backoff) can never stall the user-facing delete.
    vector_store = request.app.state.deps.vector_store
    if vector_store is not None and kb_pk is not None:

        async def _cleanup_vectors(kb_uuid: uuidpkg.UUID) -> None:
            try:
                await vector_store.delete_kb(str(kb_uuid))
            except Exception:
                logger.warning(
                    "Failed to clean up vectors for deleted KB %s",
                    kb_uuid,
                    exc_info=True,
                )

        task = asyncio.create_task(_cleanup_vectors(knowledge_base_uuid))
        _VECTOR_CLEANUP_TASKS.add(task)
        task.add_done_callback(_VECTOR_CLEANUP_TASKS.discard)

    logger.info(
        "deleted knowledge base",
        extra={"base_id": knowledge_base.id, "owner_id": auth_ctx.user.id},
    )

    return {"message": "Knowledge base deleted successfully"}


class ChunkResult(BaseModel):
    text: str
    score: float | None = None
    source: str | None = None


class SearchResponse(BaseModel):
    results: list[ChunkResult]


@knowledge_base_router.get(
    "/knowledge-bases/{knowledge_base_uuid}/search",
    response_model=SearchResponse,
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def search_knowledge_base(
    request: Request,
    knowledge_base_uuid: uuidpkg.UUID,
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50),
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> SearchResponse:
    """
    Semantic search over a knowledge base's DataRobot Memory API store.
    Returns up to top_k chunks for the query (highest score first).
    Empty if the knowledge base has not been indexed yet.
    """
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    user_repo: UserRepository = request.app.state.deps.user_repo

    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    kb = await knowledge_base_repo.get_knowledge_base(
        current_user, knowledge_base_uuid=knowledge_base_uuid
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    vector_store = request.app.state.deps.vector_store
    # Gate on index_status == READY too (via is_semantic_ready): during a
    # full-replace rebuild the store is partially populated, and /search must
    # refuse to serve those partial results exactly like the chat path does.
    if vector_store is None or kb.id is None or not is_semantic_ready(kb):
        return SearchResponse(results=[])

    retrieved = await vector_store.retrieve(str(kb.uuid), q, top_k=top_k)
    return SearchResponse(
        results=[
            ChunkResult(text=c["text"], score=c["score"], source=c["source"])
            for c in retrieved
        ]
    )
