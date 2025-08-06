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
import logging
import uuid as uuidpkg
from datetime import datetime, timezone

from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
)
from app.users.user import User

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

    files: list[KnowledgeBaseFileSchema] = Field(default_factory=list)

    @classmethod
    def from_knowledge_base(
        cls,
        knowledge_base: KnowledgeBase,
        owner_uuid: uuidpkg.UUID | None = None,
        files_with_content: dict[str, dict[int, str]] | None = None,
    ) -> "KnowledgeBaseSchema":
        # If owner_uuid is provided, use it; otherwise try to get it from the relationship
        if owner_uuid is None:
            try:
                owner_uuid = knowledge_base.owner.uuid
            except Exception:
                # If owner relationship is not available, we'll need to pass it explicitly
                raise ValueError(
                    "owner_uuid must be provided when base.owner is not accessible"
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
            files=file_schemas,
        )


class KnowledgeBaseListSchema(BaseModel):
    knowledge_bases: list[KnowledgeBaseSchema]


class BaseCreateRequestSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    path: str | None = Field(default=None, min_length=1, max_length=500)
    token_count: int = Field(default=0, ge=0)


knowledge_base_router = APIRouter(tags=["Knowledge Bases"])


async def get_knowledge_base_schema(
    knowledge_base_uuid: uuidpkg.UUID,
    knowledge_base_repo: KnowledgeBaseRepository,
    current_user: User,
    include_content: bool = False,
    file_repo: FileRepository | None = None,
) -> KnowledgeBaseSchema:
    knowledge_base = await knowledge_base_repo.get_knowledge_base(
        knowledge_base_uuid=knowledge_base_uuid
    )

    if not knowledge_base:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"Base with UUID {knowledge_base_uuid} not found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.model_dump()
        )

    # Verify ownership
    if knowledge_base.owner_id != current_user.id:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Access denied",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.model_dump()
        )

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
        knowledge_base,
        owner_uuid=current_user.uuid,
        files_with_content=files_with_content,
    )


@knowledge_base_router.get("/knowledge-bases/", responses={401: {"model": ErrorSchema}})
async def list_knowledge_bases(
    request: Request, auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> KnowledgeBaseListSchema:
    """
    List all knowledge bases owned by the current user.
    """
    knowledge_base_repo = request.app.state.deps.knowledge_base_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    knowledge_bases = await knowledge_base_repo.list_knowledge_bases_by_owner(
        owner_id=int(auth_ctx.user.id)
    )

    return KnowledgeBaseListSchema(
        knowledge_bases=[
            KnowledgeBaseSchema.from_knowledge_base(base, owner_uuid=current_user.uuid)
            for base in knowledge_bases
        ]
    )


@knowledge_base_router.post(
    "/knowledge-bases/", responses={401: {"model": ErrorSchema}}
)
async def create_knowledge_base(
    request: Request,
    payload: BaseCreateRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> KnowledgeBaseSchema:
    """
    Create a new base.
    """
    knowledge_base_repo = request.app.state.deps.knowledge_base_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    knowledge_base_data = KnowledgeBaseCreate(
        title=payload.title,
        description=payload.description,
        path=payload.path,
        token_count=payload.token_count,
    )

    knowledge_base = await knowledge_base_repo.create_knowledge_base(
        knowledge_base_data, owner_id=int(auth_ctx.user.id)
    )

    logger.info(
        "created new base",
        extra={"base_id": knowledge_base.id, "owner_id": auth_ctx.user.id},
    )

    return KnowledgeBaseSchema.from_knowledge_base(
        knowledge_base, owner_uuid=current_user.uuid
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
    knowledge_base_repo = request.app.state.deps.knowledge_base_repo
    user_repo = request.app.state.deps.user_repo
    file_repo = request.app.state.deps.file_repo

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

    # First get the base to find the ID
    knowledge_base = await knowledge_base_repo.get_knowledge_base(
        knowledge_base_uuid=knowledge_base_uuid
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

    logger.info(
        "deleted knowledge base",
        extra={"base_id": knowledge_base.id, "owner_id": auth_ctx.user.id},
    )

    return {"message": "Knowledge base deleted successfully"}
