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
import pathlib
import uuid as uuidpkg
from enum import Enum
from typing import Any

import aiohttp
import httpx
from aiogoogle.auth.creds import UserCreds
from aiogoogle.client import Aiogoogle
from aiogoogle.excs import AuthError as AiogoogleAuthError
from box_sdk_gen import BoxClient, BoxDeveloperTokenAuth
from box_sdk_gen.box.errors import BoxAPIError, BoxSDKError
from box_sdk_gen.schemas import Items as BoxItems
from core.persistent_fs.dr_file_system import get_file_system
from datarobot.auth.oauth import OAuthToken
from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.schema import ErrorCodes, ErrorSchema
from app.auth.ctx import get_access_token, must_get_auth_ctx
from app.files import File as DBFile
from app.files import FileCreate, FileUpdate, get_or_create_encoded_content
from app.files.models import FileRepository
from app.knowledge_bases import KnowledgeBaseRepository
from app.users.identity import IdentityRepository, IdentityUpdate, ProviderType
from app.users.user import UserRepository
from core import document_loader

logger = logging.getLogger(__name__)

files_router = APIRouter(tags=["Files"])

GDRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
BOX_ROOT_FOLDER_ID = "0"
GOOGLE_MAX_PAGES = 10
SHAREPOINT_MAX_ITEMS = 200

# Microsoft Graph API base URL
MICROSOFT_GRAPH_API = "https://graph.microsoft.com/v1.0"

# Google Apps MIME types that can be exported to supported formats
GOOGLE_APPS_EXPORTABLE = {
    "application/vnd.google-apps.document": "docx",  # Google Docs -> DOCX
    "application/vnd.google-apps.presentation": "pptx",  # Google Slides -> PPTX
    # Note: Google Sheets would export to xlsx, but we don't support xlsx yet
}

# Map of Google Apps MIME types to their exported file extensions
GOOGLE_APPS_EXPORT_FORMATS = {
    "application/vnd.google-apps.document": ".docx",
    "application/vnd.google-apps.presentation": ".pptx",
}
GDRIVE_MIME_TYPES = (
    "("
    + " or ".join(
        f"mimeType='{type}'"
        for type in (
            list(document_loader.SUPPORTED_MIME_TYPES)
            + [GDRIVE_FOLDER_MIME_TYPE]
            + list(GOOGLE_APPS_EXPORTABLE.keys())
        )
    )
    + ")"
)


class FileType(str, Enum):
    FOLDER = "folder"
    FILE = "file"
    WEB_LINK = "web_link"


class File(BaseModel):
    id: str
    type: FileType
    name: str
    mime_type: str | None = None


class FilesListSchema(BaseModel):
    files: list[File]
    # TODO: add pagination?


# TODO: Define a file manager abstraction to handler file operations across providers seamlessly


def _is_supported_file_type(filename: str, mime_type: str | None = None) -> bool:
    """
    Check if a file has a supported extension for document processing.

    Args:
        filename: The filename to check
        mime_type: Optional MIME type for special handling (e.g., Google Apps files)

    Returns:
        True if the file extension is supported, False otherwise
    """
    if not filename:
        return False

    # Check if it's a Google Apps file that can be exported to a supported format
    if mime_type and mime_type in GOOGLE_APPS_EXPORTABLE:
        return True

    file_extension = pathlib.Path(filename).suffix.lower().lstrip(".")
    return file_extension in document_loader.SUPPORTED_FILE_TYPES


async def _mark_identity_needs_reauth(
    request: Request, auth_ctx: AuthCtx[Metadata], provider_type: str
) -> None:
    """
    Mark the user's identity for the given provider as needing re-authorization.
    This is called when the OAuth token is rejected by the provider (e.g., user revoked access).
    """
    identity_repo: IdentityRepository = request.app.state.deps.identity_repo

    # Find the identity for this provider type
    identity = next(
        (
            ident
            for ident in auth_ctx.identities
            if ident.provider_type == provider_type
        ),
        None,
    )

    if identity and identity.id:
        logger.info(
            "Marking identity as needs_reauth",
            extra={"identity_id": identity.id, "provider_type": provider_type},
        )
        await identity_repo.update_identity(
            identity_id=int(identity.id),
            update=IdentityUpdate(needs_reauth=True),
        )


@files_router.get(
    "/docs/google/files/",
    responses={401: {"model": ErrorSchema}, 409: {"model": ErrorSchema}},
)
async def get_google_files(
    request: Request,
    folder_id: str | None = None,
    token_data: OAuthToken = Depends(get_access_token(ProviderType.GOOGLE)),
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FilesListSchema:
    files = []
    user_creds = UserCreds(
        access_token=token_data.access_token,
        expires_at=token_data.expires_at,
    )  # type: ignore[no-untyped-call]

    if not token_data.access_token:
        logger.error(
            "Invalid or missing Google access token", extra={"token_data": token_data}
        )
        raise HTTPException(
            status_code=401, detail="Invalid or expired Google access token"
        )

    try:
        async with Aiogoogle(user_creds=user_creds) as aiogoogle:
            drive_v3 = await aiogoogle.discover("drive", "v3")

            if folder_id:
                query = f"'{folder_id}' in parents and trashed=false and {GDRIVE_MIME_TYPES}"
            else:
                query = GDRIVE_MIME_TYPES

            req = drive_v3.files.list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
            )

            # full_res=True gives you an async iterator over pages
            page_count = 0
            async for page in await aiogoogle.as_user(req, full_res=True):  # type: ignore[no-untyped-call]
                if page_count >= GOOGLE_MAX_PAGES:
                    break
                page_count += 1

                logger.debug(
                    "fetched google drive files",
                    extra={"files": page, "folder_id": folder_id},
                )

                for file in page.get("files", []):
                    mime_type = file.get("mimeType")
                    filename = file.get("name", "")

                    # Skip folders (we always want to show them)
                    is_folder = mime_type == GDRIVE_FOLDER_MIME_TYPE

                    # For files, only include supported types (including exportable Google Apps files)
                    if not is_folder and not _is_supported_file_type(
                        filename, mime_type
                    ):
                        continue

                    files.append(
                        File(
                            id=file["id"],
                            type=FileType.FOLDER if is_folder else FileType.FILE,
                            name=filename,
                            mime_type=mime_type,
                        )
                    )

    except AiogoogleAuthError as e:
        # Access token was rejected by Google (likely revoked by user)
        logger.warning(
            "Google API auth error - token may have been revoked",
            extra={"error": str(e)},
        )
        # Mark the identity as needing re-authorization
        await _mark_identity_needs_reauth(request, auth_ctx, ProviderType.GOOGLE.value)
        err = ErrorSchema(
            code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
            message="Your Google connection has expired or been revoked. Please reconnect your account in Settings.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
        )

    return FilesListSchema(files=files)


@files_router.get(
    "/docs/box/files/",
    responses={401: {"model": ErrorSchema}, 409: {"model": ErrorSchema}},
)
async def get_box_files(
    request: Request,
    folder_id: str = BOX_ROOT_FOLDER_ID,
    token_data: OAuthToken = Depends(get_access_token(ProviderType.BOX)),
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FilesListSchema:
    box_client = BoxClient(
        auth=BoxDeveloperTokenAuth(token=token_data.access_token),
    )

    files = FilesListSchema(files=[])

    try:
        # Box SDK is synchronous only
        box_files: BoxItems = await asyncio.get_running_loop().run_in_executor(
            None, box_client.folders.get_folder_items, folder_id
        )
    except BoxSDKError as e:
        # BoxSDKError is raised when the developer token has expired/been revoked
        # This happens during the SDK's internal token refresh attempt
        logger.warning(
            "Box SDK error - token may have expired or been revoked",
            extra={"error": str(e), "error_message": e.message},
        )
        await _mark_identity_needs_reauth(request, auth_ctx, ProviderType.BOX.value)
        err = ErrorSchema(
            code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
            message="Your Box connection has expired or been revoked. Please reconnect your account in Settings.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
        )
    except BoxAPIError as e:
        # Check if this is an auth-related error (401 Unauthorized)
        if e.response_info.status_code == 401:
            logger.warning(
                "Box API auth error - token may have been revoked",
                extra={"error": str(e), "status_code": e.response_info.status_code},
            )
            await _mark_identity_needs_reauth(request, auth_ctx, ProviderType.BOX.value)
            err = ErrorSchema(
                code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
                message="Your Box connection has expired or been revoked. Please reconnect your account in Settings.",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
            )
        raise

    logger.debug(
        "fetched box files", extra={"files": box_files, "folder_id": folder_id}
    )

    for file in box_files.entries or []:
        filename = file.name or ""

        # Skip files with unsupported types (but always show folders)
        is_folder = file.type == "folder"
        if not is_folder and not _is_supported_file_type(filename):
            continue

        files.files.append(
            File(
                id=file.id,
                type=FileType(file.type),
                name=filename,
            )
        )

    return files


@files_router.get(
    "/docs/sharepoint/files/",
    responses={401: {"model": ErrorSchema}, 409: {"model": ErrorSchema}},
)
async def get_sharepoint_files(
    request: Request,
    site_id: str | None = None,
    drive_id: str | None = None,
    folder_id: str | None = None,
    token_data: OAuthToken = Depends(get_access_token(ProviderType.SHAREPOINT)),
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FilesListSchema:
    """
    List files from SharePoint/OneDrive using Microsoft Graph API.

    - If no parameters: lists user's drives (OneDrive + SharePoint document libraries)
    - If site_id + drive_id (no folder_id): lists root items in that drive
    - If site_id + drive_id + folder_id: lists items in that folder

    Note: site_id can be "personal" for OneDrive or an actual SharePoint site ID.
    """
    logger.debug(
        "SharePoint files request",
        extra={
            "site_id": site_id,
            "drive_id": drive_id,
            "folder_id": folder_id,
            "user_id": auth_ctx.user.id,
        },
    )

    files: list[File] = []

    if not token_data.access_token:
        logger.error(
            "Invalid or missing SharePoint access token",
            extra={"token_data": token_data},
        )
        raise HTTPException(
            status_code=401, detail="Invalid or expired SharePoint access token"
        )

    headers = {"Authorization": f"Bearer {token_data.access_token}"}

    try:
        async with httpx.AsyncClient() as client:
            if not site_id:
                # Show two top-level options: Quick access drives + Browse all sites
                logger.debug("Fetching top-level SharePoint navigation")

                # First, add a "Browse Sites" option
                files.append(
                    File(
                        id="browse:sites",
                        type=FileType.FOLDER,
                        name="📁 Browse SharePoint Sites",
                        mime_type="application/vnd.sharepoint.sites",
                    )
                )

                # Then list user's quick-access drives
                response = await client.get(
                    f"{MICROSOFT_GRAPH_API}/me/drives",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(
                    "Received drives from Microsoft Graph",
                    extra={"drive_count": len(data.get("value", []))},
                )

                for drive in data.get("value", []):
                    current_drive_id = drive["id"]
                    drive_name = drive.get("name", "Drive")

                    # Get the site ID if available (may be None for personal OneDrive)
                    # Note: sharePointIds.siteId returns only a GUID, but Graph API /sites/{site-id}
                    # endpoints require the compound format {hostname},{siteCollectionId},{webId}.
                    # Using the GUID alone causes 404 errors. Instead, use "personal" as a sentinel
                    # to indicate we should use /drives/{drive_id} endpoints (no site context).
                    site_info = drive.get("sharePointIds", {})
                    site_id_value = site_info.get("siteId", "")

                    # For drives, we'll encode both site and drive ID in the ID field
                    # Use "personal" sentinel for all quick-access drives (proper site ID unavailable)
                    if site_id_value and "," in site_id_value:
                        # Valid compound site ID from browse path
                        file_id = f"drive:{site_id_value}:{current_drive_id}"
                    else:
                        # Personal OneDrive or SharePoint drive without proper site context
                        file_id = f"drive:personal:{current_drive_id}"

                    files.append(
                        File(
                            id=file_id,
                            type=FileType.FOLDER,
                            name=drive_name,
                            mime_type="application/vnd.sharepoint.drive",
                        )
                    )

            elif site_id == "browse":
                # List all SharePoint sites the user has access to
                logger.debug("Fetching SharePoint sites")
                response = await client.get(
                    f"{MICROSOFT_GRAPH_API}/sites?search=*&$top={SHAREPOINT_MAX_ITEMS}",
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(
                    "Received SharePoint sites",
                    extra={"site_count": len(data.get("value", []))},
                )

                for site in data.get("value", []):
                    files.append(
                        File(
                            id=f"site:{site['id']}",
                            type=FileType.FOLDER,
                            name=site.get("displayName") or site.get("name", ""),
                            mime_type="application/vnd.sharepoint.site",
                        )
                    )

            elif site_id and not drive_id:
                # List drives (document libraries) in the site
                # "personal" is a synthetic sentinel, not a valid site ID - skip this branch
                if site_id == "personal":
                    logger.debug(
                        "Skipping site drives listing for personal OneDrive",
                        extra={"site_id": site_id},
                    )
                    # Personal OneDrive doesn't have a concept of listing drives for a site
                    # The back button should never navigate here; return empty to the root
                else:
                    logger.debug(
                        "Fetching drives for site",
                        extra={"site_id": site_id},
                    )
                    response = await client.get(
                        f"{MICROSOFT_GRAPH_API}/sites/{site_id}/drives",
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    logger.debug(
                        "Received drives for site",
                        extra={
                            "site_id": site_id,
                            "drive_count": len(data.get("value", [])),
                        },
                    )

                    for drive in data.get("value", []):
                        files.append(
                            File(
                                id=f"drive:{site_id}:{drive['id']}",
                                type=FileType.FOLDER,
                                name=drive.get("name", ""),
                                mime_type="application/vnd.sharepoint.drive",
                            )
                        )

            elif site_id and drive_id and not folder_id:
                # List root items in the drive
                # Handle personal OneDrive (site_id = "personal") vs SharePoint drives
                if site_id == "personal":
                    url = f"{MICROSOFT_GRAPH_API}/drives/{drive_id}/root/children?$top={SHAREPOINT_MAX_ITEMS}"
                else:
                    url = f"{MICROSOFT_GRAPH_API}/sites/{site_id}/drives/{drive_id}/root/children?$top={SHAREPOINT_MAX_ITEMS}"

                logger.debug(
                    "Fetching drive root items",
                    extra={
                        "site_id": site_id,
                        "drive_id": drive_id,
                        "url": url,
                    },
                )
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                logger.debug(
                    "Received drive root items",
                    extra={
                        "site_id": site_id,
                        "drive_id": drive_id,
                        "item_count": len(data.get("value", [])),
                    },
                )

                for item in data.get("value", []):
                    is_folder = "folder" in item
                    filename = item.get("name", "")

                    # Skip unsupported file types (but always show folders)
                    if not is_folder and not _is_supported_file_type(filename):
                        continue

                    files.append(
                        File(
                            id=f"item:{site_id}:{drive_id}:{item['id']}",
                            type=FileType.FOLDER if is_folder else FileType.FILE,
                            name=filename,
                            mime_type=item.get("file", {}).get("mimeType"),
                        )
                    )

            elif site_id and drive_id and folder_id:
                # List items in a folder
                # Handle personal OneDrive (site_id = "personal") vs SharePoint drives
                if site_id == "personal":
                    url = f"{MICROSOFT_GRAPH_API}/drives/{drive_id}/items/{folder_id}/children?$top={SHAREPOINT_MAX_ITEMS}"
                else:
                    url = f"{MICROSOFT_GRAPH_API}/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children?$top={SHAREPOINT_MAX_ITEMS}"

                logger.debug(
                    "Fetching folder items",
                    extra={
                        "site_id": site_id,
                        "drive_id": drive_id,
                        "folder_id": folder_id,
                        "url": url,
                    },
                )
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                logger.debug(
                    "Received folder items",
                    extra={
                        "site_id": site_id,
                        "drive_id": drive_id,
                        "folder_id": folder_id,
                        "item_count": len(data.get("value", [])),
                    },
                )

                for item in data.get("value", []):
                    is_folder = "folder" in item
                    filename = item.get("name", "")

                    # Skip unsupported file types (but always show folders)
                    if not is_folder and not _is_supported_file_type(filename):
                        continue

                    files.append(
                        File(
                            id=f"item:{site_id}:{drive_id}:{item['id']}",
                            type=FileType.FOLDER if is_folder else FileType.FILE,
                            name=filename,
                            mime_type=item.get("file", {}).get("mimeType"),
                        )
                    )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.warning(
                "SharePoint API auth error - token may have been revoked",
                extra={"error": str(e)},
            )
            await _mark_identity_needs_reauth(
                request, auth_ctx, ProviderType.SHAREPOINT.value
            )
            err = ErrorSchema(
                code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
                message="Your SharePoint connection has expired or been revoked. Please reconnect your account in Settings.",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
            )
        raise

    logger.debug(
        "SharePoint files response",
        extra={
            "file_count": len(files),
            "site_id": site_id,
            "drive_id": drive_id,
            "folder_id": folder_id,
        },
    )
    return FilesListSchema(files=files)


# File Management Endpoints


class FileSchema(BaseModel):
    """Schema for file response."""

    uuid: uuidpkg.UUID
    filename: str
    source: str
    file_path: str | None = None
    external_id: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    added: str  # ISO datetime string
    knowledge_base_id: int | None = None
    owner_uuid: uuidpkg.UUID
    encoded_content: dict[int, str] | None = None  # Page number to text mapping

    @classmethod
    def from_file(
        cls,
        file: DBFile,
        owner_uuid: uuidpkg.UUID | None = None,
        encoded_content: dict[int, str] | None = None,
    ) -> "FileSchema":
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
            source=file.source,
            file_path=file.file_path,
            external_id=file.external_id,
            mime_type=file.mime_type,
            size_bytes=file.size_bytes,
            added=file.added.isoformat(),
            knowledge_base_id=file.knowledge_base_id,
            owner_uuid=owner_uuid,
            encoded_content=encoded_content,
        )


class FileListSchema(BaseModel):
    """Schema for file list response."""

    files: list[FileSchema]


class FileUpdateRequestSchema(BaseModel):
    """Schema for file update request."""

    filename: str | None = Field(default=None, min_length=1, max_length=255)
    knowledge_base_uuid: uuidpkg.UUID | None = Field(
        default=None
    )  # Allow changing base attachment


class DriveUploadRequestSchema(BaseModel):
    """Schema for Google Drive file upload request."""

    file_ids: list[str] = Field(
        ..., description="List of Google Drive file IDs to upload"
    )
    knowledge_base_uuid: uuidpkg.UUID | None = Field(
        default=None, description="Optional base UUID to attach files to"
    )


class BoxUploadRequestSchema(BaseModel):
    """Schema for Box file upload request."""

    file_ids: list[str] = Field(..., description="List of Box file IDs to upload")
    knowledge_base_uuid: uuidpkg.UUID | None = Field(
        default=None, description="Optional base UUID to attach files to"
    )


class SharePointUploadRequestSchema(BaseModel):
    """Schema for SharePoint file upload request."""

    file_ids: list[str] = Field(
        ...,
        description="List of SharePoint file IDs in format 'item:site_id:drive_id:item_id'",
    )
    knowledge_base_uuid: uuidpkg.UUID | None = Field(
        default=None, description="Optional base UUID to attach files to"
    )


@files_router.get("/files/", responses={401: {"model": ErrorSchema}})
async def list_files(
    request: Request,
    knowledge_base_uuid: uuidpkg.UUID | None = None,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FileListSchema:
    """
    List all files owned by the current user, optionally filtered by knowledge base.
    """
    file_repo: FileRepository = request.app.state.deps.file_repo
    user_repo: UserRepository = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    user_uuid = current_user.uuid

    if knowledge_base_uuid:
        knowledge_base_repo: KnowledgeBaseRepository = (
            request.app.state.deps.knowledge_base_repo
        )
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Knowledge Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        files = knowledge_base.files
    else:
        files = await file_repo.get_files(user=current_user, file_ids=None)

    return FileListSchema(
        files=[FileSchema.from_file(file, owner_uuid=user_uuid) for file in files]
    )


@files_router.get(
    "/files/{file_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def get_file(
    request: Request,
    file_uuid: uuidpkg.UUID,
    include_content: bool = False,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FileSchema:
    """
    Get a specific file by UUID.

    Args:
        file_uuid: UUID of the file to retrieve
        include_content: Whether to include encoded document content in the response
    """
    file_repo = request.app.state.deps.file_repo
    user_repo = request.app.state.deps.user_repo

    file = await file_repo.get_file(file_uuid=file_uuid)

    if not file:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"File with UUID {file_uuid} not found",
        )
        raise HTTPException(status_code=404, detail=err.model_dump())

    # Verify ownership
    if file.owner_id != int(auth_ctx.user.id):
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Access denied",
        )
        raise HTTPException(status_code=403, detail=err.model_dump())

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    # Get encoded content if requested
    encoded_content = None
    if include_content and file.file_path:
        # Get knowledge base if this file belongs to one
        knowledge_base = None
        knowledge_base_repo = None
        file_repo = request.app.state.deps.file_repo
        if file.knowledge_base_id:
            knowledge_base_repo = request.app.state.deps.knowledge_base_repo
            knowledge_base = await knowledge_base_repo.get_knowledge_base(
                current_user,
                knowledge_base_id=file.knowledge_base_id,
            )

        encoded_content = await get_or_create_encoded_content(
            file=file,
            file_repo=file_repo,
            knowledge_base=knowledge_base,
            knowledge_base_repo=knowledge_base_repo,
        )

    return FileSchema.from_file(
        file, owner_uuid=current_user.uuid, encoded_content=encoded_content
    )


@files_router.put(
    "/files/{file_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def update_file(
    request: Request,
    file_uuid: uuidpkg.UUID,
    payload: FileUpdateRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> FileSchema:
    """
    Update a file by UUID.
    """
    file_repo: FileRepository = request.app.state.deps.file_repo
    user_repo: UserRepository = request.app.state.deps.user_repo

    # First get the file to find the ID
    file = await file_repo.get_file(file_uuid=file_uuid)

    if not file:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"File with UUID {file_uuid} not found",
        )
        raise HTTPException(status_code=404, detail=err.model_dump())

    # Get current user's UUID early (needed for KB lookup below)
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    knowledge_base_id = None
    if payload.knowledge_base_uuid:
        knowledge_base_repo = request.app.state.deps.knowledge_base_repo
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=payload.knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        knowledge_base_id = knowledge_base.id

    file_data = FileUpdate(
        filename=payload.filename,
        knowledge_base_id=knowledge_base_id,
    )

    # Add null check for file.id
    if not file.id:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Invalid file ID",
        )
        raise HTTPException(status_code=400, detail=err.model_dump())

    updated_file = await file_repo.update_file(
        file.id, file_data, owner_id=int(auth_ctx.user.id)
    )

    if not updated_file:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Failed to update file or access denied",
        )
        raise HTTPException(status_code=403, detail=err.model_dump())

    return FileSchema.from_file(updated_file, owner_uuid=current_user.uuid)


@files_router.delete(
    "/files/{file_uuid}",
    responses={401: {"model": ErrorSchema}, 404: {"model": ErrorSchema}},
)
async def delete_file(
    request: Request,
    file_uuid: uuidpkg.UUID,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> dict[str, str]:
    """
    Delete a file by UUID.
    """
    file_repo: FileRepository = request.app.state.deps.file_repo

    # First get the file to find the ID
    file = await file_repo.get_file(file_uuid=file_uuid)

    if not file or not file.id:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message=f"File with UUID {file_uuid} not found",
        )
        raise HTTPException(status_code=404, detail=err.model_dump())

    success = await file_repo.delete_file(file.id, owner_id=int(auth_ctx.user.id))

    if not success:
        err = ErrorSchema(
            code=ErrorCodes.UNKNOWN_ERROR,
            message="Failed to delete file or access denied",
        )
        raise HTTPException(status_code=403, detail=err.model_dump())

    return {"message": "File deleted successfully"}


@files_router.post("/files/drive/upload", responses={401: {"model": ErrorSchema}})
async def upload_drive_files(
    request: Request,
    payload: DriveUploadRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
    token_data: OAuthToken = Depends(get_access_token(ProviderType.GOOGLE)),
) -> list[FileSchema | dict[str, Any]]:
    """
    Import files from Google Drive by downloading them and optionally attach them to a base.
    Returns a list of results for each file (either FileSchema for success or error dict).
    """
    file_ids = payload.file_ids
    knowledge_base_uuid = payload.knowledge_base_uuid

    if not file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")

    file_repo = request.app.state.deps.file_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    user_uuid = current_user.uuid

    # Validate base if provided
    knowledge_base_id = None
    knowledge_base = None
    knowledge_base_repo = None
    if knowledge_base_uuid:
        knowledge_base_repo = request.app.state.deps.knowledge_base_repo
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        knowledge_base_id = knowledge_base.id

    # Setup Google Drive API client
    user_creds = UserCreds(
        access_token=token_data.access_token,
        expires_at=token_data.expires_at,
    )  # type: ignore[no-untyped-call]

    results: list[FileSchema | dict[str, Any]] = []

    try:
        async with Aiogoogle(user_creds=user_creds) as aiogoogle:
            drive_v3 = await aiogoogle.discover("drive", "v3")

            for file_id in file_ids:
                try:
                    # Get file metadata using keyword parameters
                    file_metadata = await aiogoogle.as_user(
                        drive_v3.files.get(
                            fileId=file_id, fields="id,name,mimeType,size"
                        )  # type: ignore[no-untyped-call]
                    )

                    filename = file_metadata.get("name") or f"drive_file_{file_id}"
                    mime_type = file_metadata.get("mimeType")

                    # Handle Google Apps files by exporting them
                    is_google_app = mime_type and mime_type in GOOGLE_APPS_EXPORTABLE
                    if is_google_app:
                        # Export Google Apps file to supported format
                        export_format = GOOGLE_APPS_EXPORTABLE[mime_type]
                        export_mime_type = {
                            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        }.get(export_format)

                        if not export_mime_type:
                            results.append(
                                {
                                    "filename": filename,
                                    "error": f"Cannot export {mime_type} to a supported format",
                                }
                            )
                            continue

                        # Update filename to include proper extension
                        if not filename.lower().endswith(f".{export_format}"):
                            filename = f"{pathlib.Path(filename).stem}.{export_format}"

                        # Download exported content
                        file_content = await aiogoogle.as_user(
                            drive_v3.files.export(
                                fileId=file_id, mimeType=export_mime_type
                            )  # type: ignore[no-untyped-call]
                        )
                    else:
                        # Skip other Google Apps files that we can't export
                        if mime_type and mime_type.startswith(
                            "application/vnd.google-apps"
                        ):
                            results.append(
                                {
                                    "filename": filename,
                                    "error": "This Google Apps file type cannot be exported to a supported format.",
                                }
                            )
                            continue

                        # Check file extension for regular files
                        file_extension = (
                            pathlib.Path(filename).suffix.lower().lstrip(".")
                        )
                        if file_extension not in document_loader.SUPPORTED_FILE_TYPES:
                            results.append(
                                {
                                    "filename": filename,
                                    "error": f"Unsupported file type: {file_extension}",
                                }
                            )
                            continue

                        # Download regular file content
                        try:
                            # Try the standard download method first
                            file_content = await aiogoogle.as_user(
                                drive_v3.files.get(fileId=file_id, alt="media")  # type: ignore[no-untyped-call]
                            )

                            # If we get a dict response, it might be metadata instead of content
                            if isinstance(file_content, dict):
                                # Check if this is download metadata with a download URI
                                if (
                                    "response" in file_content
                                    and "downloadUri"
                                    in file_content.get("response", {})
                                ):
                                    download_uri = file_content["response"][
                                        "downloadUri"
                                    ]
                                    # Make a direct HTTP request to download the file
                                    headers = {
                                        "Authorization": f"Bearer {token_data.access_token}"
                                    }
                                    async with aiohttp.ClientSession() as session:
                                        async with session.get(
                                            download_uri, headers=headers
                                        ) as resp:
                                            if resp.status == 200:
                                                file_content = await resp.read()
                                            else:
                                                raise Exception(
                                                    f"Failed to download file: HTTP {resp.status}"
                                                )
                                else:
                                    # If it's a dict but not downloaded metadata, try to convert to string
                                    file_content = str(file_content).encode("utf-8")
                                    logger.warning(
                                        f"Got unexpected dict response for file {file_id}: {file_content[:200].decode('utf-8', errors='replace')}..."
                                    )

                        except Exception as download_error:
                            logger.warning(
                                f"Standard download failed for {file_id}: {download_error}, trying alternative method"
                            )
                            # Fallback: try using httpx to make a direct API call
                            download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                            headers = {
                                "Authorization": f"Bearer {token_data.access_token}"
                            }

                            async with httpx.AsyncClient() as client:
                                response = await client.get(
                                    download_url, headers=headers
                                )
                                if response.status_code == 200:
                                    file_content = response.content
                                else:
                                    raise Exception(
                                        f"Failed to download file via fallback method: HTTP {response.status_code}"
                                    )

                    # Ensure file_content is bytes
                    if isinstance(file_content, str):
                        file_content = file_content.encode("utf-8")
                    elif not isinstance(file_content, bytes):
                        # Handle other types by converting to string first then bytes
                        file_content = (
                            str(file_content).encode("utf-8") if file_content else b""
                        )

                    # Create directory structure based on base or user
                    if knowledge_base_id:
                        # Use base path for files attached to a base
                        knowledge_base = await request.app.state.deps.knowledge_base_repo.get_knowledge_base(
                            current_user,
                            knowledge_base_uuid=knowledge_base_uuid,
                        )
                        file_dir = (
                            pathlib.Path(request.app.state.deps.upload_path)
                            / knowledge_base.path
                        )
                    else:
                        # Use user's UUID for standalone files
                        file_dir = pathlib.Path(
                            request.app.state.deps.upload_path
                        ) / str(user_uuid)

                    fs = get_file_system()
                    # Ensure directory exists
                    try:
                        fs.mkdir(str(file_dir), create_parents=True)
                    except FileExistsError:
                        pass

                    file_path = str(file_dir / filename)

                    # Save the file
                    with fs.open(file_path, "wb") as buffer:
                        buffer.write(file_content)

                    # Create file record in database
                    source = "google_drive"
                    if is_google_app:
                        source = f"google_{GOOGLE_APPS_EXPORTABLE[mime_type]}"  # e.g., "google_docx", "google_pptx"

                    file_data = FileCreate(
                        filename=filename,
                        source=source,
                        file_path=file_path,
                        external_id=file_id,
                        mime_type=mime_type,
                        size_bytes=len(file_content),
                        knowledge_base_id=knowledge_base_id,
                    )

                    db_file = await file_repo.create_file(
                        file_data, owner_id=int(auth_ctx.user.id)
                    )

                    # Encode the document in the background (don't wait for it)
                    asyncio.create_task(
                        get_or_create_encoded_content(
                            file=db_file,
                            file_repo=file_repo,
                            knowledge_base=knowledge_base,
                            knowledge_base_repo=knowledge_base_repo,
                        )
                    )

                    results.append(FileSchema.from_file(db_file, owner_uuid=user_uuid))

                except AiogoogleAuthError:
                    # Re-raise auth errors to be handled at the outer level
                    raise
                except Exception as e:
                    logger.exception("Failed to import from Google Drive")
                    results.append(
                        {
                            "file_id": file_id,
                            "error": f"Failed to import file from Google Drive: {str(e)}",
                        }
                    )

    except AiogoogleAuthError as e:
        # Access token was rejected by Google (likely revoked by user)
        logger.warning(
            "Google API auth error during file upload - token may have been revoked",
            extra={"error": str(e)},
        )
        await _mark_identity_needs_reauth(request, auth_ctx, ProviderType.GOOGLE.value)
        err = ErrorSchema(
            code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
            message="Your Google connection has expired or been revoked. Please reconnect your account in Settings.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
        )

    return results


@files_router.post("/files/box/upload", responses={401: {"model": ErrorSchema}})
async def upload_box_files(
    request: Request,
    payload: BoxUploadRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
    token_data: OAuthToken = Depends(get_access_token(ProviderType.BOX)),
) -> list[FileSchema | dict[str, Any]]:
    """
    Import files from Box by downloading them and optionally attach them to a base.
    Returns a list of results for each file (either FileSchema for success or error dict).
    """
    file_ids = payload.file_ids
    knowledge_base_uuid = payload.knowledge_base_uuid

    if not file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")

    file_repo = request.app.state.deps.file_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    user_uuid = current_user.uuid

    # Validate base if provided
    knowledge_base_id = None
    knowledge_base = None
    knowledge_base_repo = None
    if knowledge_base_uuid:
        knowledge_base_repo = request.app.state.deps.knowledge_base_repo
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        knowledge_base_id = knowledge_base.id

    # Setup Box API client
    box_client = BoxClient(
        auth=BoxDeveloperTokenAuth(token=token_data.access_token),
    )

    # Set up file directory path once for all files
    if knowledge_base_id:
        # Use base path for files attached to a base
        knowledge_base = (
            await request.app.state.deps.knowledge_base_repo.get_knowledge_base(
                current_user,
                knowledge_base_uuid=knowledge_base_uuid,
            )
        )
        file_dir = (
            pathlib.Path(request.app.state.deps.upload_path) / knowledge_base.path
        )
    else:
        # Use user's UUID for standalone files
        file_dir = pathlib.Path(request.app.state.deps.upload_path) / str(user_uuid)

    fs = get_file_system()
    # Ensure directory exists
    try:
        fs.mkdir(str(file_dir), create_parents=True)
    except FileExistsError:
        pass

    results: list[FileSchema | dict[str, Any]] = []

    for file_id in file_ids:
        try:
            # Get file metadata (Box SDK is synchronous only)
            file_info = await asyncio.get_running_loop().run_in_executor(
                None, box_client.files.get_file_by_id, file_id
            )

            filename = file_info.name or f"box_file_{file_id}"

            # Check file extension
            file_extension = pathlib.Path(filename).suffix.lower().lstrip(".")
            if file_extension not in document_loader.SUPPORTED_FILE_TYPES:
                results.append(
                    {
                        "filename": filename,
                        "error": f"Unsupported file type: {file_extension}",
                    }
                )
                continue

            # Set up file path using the pre-calculated directory
            file_path = str(file_dir / filename)

            # Download file content and stream to disk
            def get_box_file_stream(client: BoxClient, file_id: str) -> Any:
                """Get Box file stream (Box SDK is synchronous)"""
                return client.downloads.download_file(file_id)

            # Get the file stream using executor (Box SDK is sync)
            file_stream = await asyncio.get_running_loop().run_in_executor(
                None, get_box_file_stream, box_client, file_id
            )

            # Stream to disk
            total_bytes = 0
            with fs.open(file_path, "wb") as buffer:
                for chunk in file_stream:
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    buffer.write(chunk)
                    total_bytes += len(chunk)

            # Create file record in database
            file_data = FileCreate(
                filename=filename,
                source="box",
                file_path=file_path,
                external_id=file_id,
                mime_type=None,  # Box doesn't always provide mime type
                size_bytes=total_bytes,
                knowledge_base_id=knowledge_base_id,
            )

            db_file = await file_repo.create_file(
                file_data, owner_id=int(auth_ctx.user.id)
            )

            # Encode the document in the background (don't wait for it)
            asyncio.create_task(
                get_or_create_encoded_content(
                    file=db_file,
                    file_repo=file_repo,
                    knowledge_base=knowledge_base,
                    knowledge_base_repo=knowledge_base_repo,
                )
            )

            results.append(FileSchema.from_file(db_file, owner_uuid=user_uuid))

        except BoxSDKError as e:
            # BoxSDKError is raised when the developer token has expired/been revoked
            # This happens during the SDK's internal token refresh attempt
            logger.warning(
                "Box SDK error during file upload - token may have expired or been revoked",
                extra={"error": str(e), "error_message": e.message, "file_id": file_id},
            )
            await _mark_identity_needs_reauth(request, auth_ctx, ProviderType.BOX.value)
            err = ErrorSchema(
                code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
                message="Your Box connection has expired or been revoked. Please reconnect your account in Settings.",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
            )
        except BoxAPIError as e:
            # Check if this is an auth-related error (401 Unauthorized)
            if e.response_info.status_code == 401:
                logger.warning(
                    "Box API auth error during file upload - token may have been revoked",
                    extra={
                        "error": str(e),
                        "file_id": file_id,
                        "status_code": e.response_info.status_code,
                    },
                )
                await _mark_identity_needs_reauth(
                    request, auth_ctx, ProviderType.BOX.value
                )
                err = ErrorSchema(
                    code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
                    message="Your Box connection has expired or been revoked. Please reconnect your account in Settings.",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
                )
            # Re-raise other Box errors to be handled by the generic exception handler
            raise
        except Exception as e:
            error_message = str(e)
            logger.exception(
                "Failed to upload file from Box", extra={"file_id": file_id}
            )
            # Check if this is a Box permission error (403)
            if "403" in error_message and (
                "permission" in error_message.lower()
                or "access denied" in error_message.lower()
            ):
                # Return a 500 error for permission issues with detailed guidance
                err = ErrorSchema(
                    code=ErrorCodes.UNKNOWN_ERROR,
                    message=f"Box access denied - insufficient permissions for file {file_id}. "
                    f"This error typically occurs when:\n"
                    f"1. The Box OAuth application doesn't have 'Read and Write' permission\n"
                    f"2. The user doesn't have access to the specific file\n"
                    f"3. The file is in a restricted folder\n"
                    f"Please check your Box OAuth application configuration and ensure the user has access to this file.",
                )
                raise HTTPException(status_code=500, detail=err.model_dump())

            results.append(
                {
                    "file_id": file_id,
                    "error": f"Failed to import file from Box: {error_message}",
                }
            )

    # Check if any uploads failed and return appropriate status code
    failed_files = [
        result for result in results if isinstance(result, dict) and "error" in result
    ]
    if failed_files:
        # If all files failed, return 500
        if len(failed_files) == len(results):
            error_messages = [
                result["error"]
                for result in failed_files
                if isinstance(result, dict) and "error" in result
            ]
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message=f"All file uploads failed. Errors: {error_messages}",
            )
            raise HTTPException(status_code=500, detail=err.model_dump())

    return results


@files_router.post("/files/sharepoint/upload", responses={401: {"model": ErrorSchema}})
async def upload_sharepoint_files(
    request: Request,
    payload: SharePointUploadRequestSchema,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
    token_data: OAuthToken = Depends(get_access_token(ProviderType.SHAREPOINT)),
) -> list[FileSchema | dict[str, Any]]:
    """
    Import files from SharePoint by downloading them and optionally attach them to a base.
    Returns a list of results for each file (either FileSchema for success or error dict).

    File IDs should be in format: 'item:site_id:drive_id:item_id'
    """
    file_ids = payload.file_ids
    knowledge_base_uuid = payload.knowledge_base_uuid

    logger.debug(
        "SharePoint file upload request",
        extra={
            "file_count": len(file_ids),
            "knowledge_base_uuid": knowledge_base_uuid,
            "user_id": auth_ctx.user.id,
        },
    )

    if not file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")

    file_repo = request.app.state.deps.file_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    user_uuid = current_user.uuid

    # Validate base if provided
    knowledge_base_id = None
    knowledge_base = None
    knowledge_base_repo = None
    if knowledge_base_uuid:
        knowledge_base_repo = request.app.state.deps.knowledge_base_repo
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        knowledge_base_id = knowledge_base.id

    headers = {"Authorization": f"Bearer {token_data.access_token}"}

    # Set up file directory path once for all files
    if knowledge_base:
        # Use base path for files attached to a base (already fetched above)
        file_dir = (
            pathlib.Path(request.app.state.deps.upload_path) / knowledge_base.path
        )
    else:
        # Use user's UUID for standalone files
        file_dir = pathlib.Path(request.app.state.deps.upload_path) / str(user_uuid)

    fs = get_file_system()
    # Ensure directory exists
    try:
        fs.mkdir(str(file_dir), create_parents=True)
    except FileExistsError:
        pass

    results: list[FileSchema | dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        for file_id in file_ids:
            try:
                # Parse file ID format: 'item:site_id:drive_id:item_id'
                parts = file_id.split(":")
                if len(parts) != 4 or parts[0] != "item":
                    results.append(
                        {
                            "file_id": file_id,
                            "error": "Invalid file ID format. Expected 'item:site_id:drive_id:item_id'",
                        }
                    )
                    continue

                _, site_id, drive_id, item_id = parts

                logger.debug(
                    "Processing SharePoint file",
                    extra={
                        "file_id": file_id,
                        "site_id": site_id,
                        "drive_id": drive_id,
                        "item_id": item_id,
                    },
                )

                # Get file metadata
                # Handle personal OneDrive (site_id = "personal") vs SharePoint drives
                if site_id == "personal":
                    metadata_url = (
                        f"{MICROSOFT_GRAPH_API}/drives/{drive_id}/items/{item_id}"
                    )
                else:
                    metadata_url = f"{MICROSOFT_GRAPH_API}/sites/{site_id}/drives/{drive_id}/items/{item_id}"

                metadata_response = await client.get(metadata_url, headers=headers)
                metadata_response.raise_for_status()
                metadata = metadata_response.json()

                filename = metadata.get("name", f"sharepoint_file_{item_id}")
                mime_type = metadata.get("file", {}).get("mimeType")

                # Check file extension
                file_extension = pathlib.Path(filename).suffix.lower().lstrip(".")
                if file_extension not in document_loader.SUPPORTED_FILE_TYPES:
                    results.append(
                        {
                            "filename": filename,
                            "error": f"Unsupported file type: {file_extension}",
                        }
                    )
                    continue

                # Download file content
                download_url = metadata.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    # Fallback: construct download URL
                    # Handle personal OneDrive (site_id = "personal") vs SharePoint drives
                    if site_id == "personal":
                        download_url = f"{MICROSOFT_GRAPH_API}/drives/{drive_id}/items/{item_id}/content"
                    else:
                        download_url = f"{MICROSOFT_GRAPH_API}/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"

                download_response = await client.get(
                    download_url,
                    headers=headers,
                    follow_redirects=True,
                )
                download_response.raise_for_status()
                file_content = download_response.content

                logger.debug(
                    "Downloaded SharePoint file",
                    extra={
                        "file_id": file_id,
                        "filename": filename,
                        "size_bytes": len(file_content),
                    },
                )

                file_path = str(file_dir / filename)

                # Save the file
                with fs.open(file_path, "wb") as buffer:
                    buffer.write(file_content)

                # Create file record in database
                file_data = FileCreate(
                    filename=filename,
                    source="sharepoint",
                    file_path=file_path,
                    external_id=file_id,
                    mime_type=mime_type,
                    size_bytes=len(file_content),
                    knowledge_base_id=knowledge_base_id,
                )

                db_file = await file_repo.create_file(
                    file_data, owner_id=int(auth_ctx.user.id)
                )

                # Encode the document in the background (don't wait for it)
                asyncio.create_task(
                    get_or_create_encoded_content(
                        file=db_file,
                        file_repo=file_repo,
                        knowledge_base=knowledge_base,
                        knowledge_base_repo=knowledge_base_repo,
                    )
                )

                results.append(FileSchema.from_file(db_file, owner_uuid=user_uuid))

                logger.debug(
                    "Successfully imported SharePoint file",
                    extra={
                        "file_id": file_id,
                        "db_file_id": db_file.id,
                        "filename": filename,
                    },
                )

            except httpx.HTTPStatusError as e:
                # Handle auth errors by raising HTTPException (will propagate to FastAPI)
                if e.response.status_code == 401:
                    logger.warning(
                        "SharePoint API auth error during file upload",
                        extra={"error": str(e), "file_id": file_id},
                    )
                    await _mark_identity_needs_reauth(
                        request, auth_ctx, ProviderType.SHAREPOINT.value
                    )
                    err = ErrorSchema(
                        code=ErrorCodes.OAUTH_REAUTH_REQUIRED,
                        message="Your SharePoint connection has expired or been revoked. Please reconnect your account in Settings.",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=err.model_dump(),
                    )
                # For non-auth HTTP errors, add to results instead of raising
                results.append(
                    {
                        "file_id": file_id,
                        "error": f"Failed to import file from SharePoint: {str(e)}",
                    }
                )
            except Exception as e:
                logger.exception(
                    "Failed to upload file from SharePoint", extra={"file_id": file_id}
                )
                results.append(
                    {
                        "file_id": file_id,
                        "error": f"Failed to import file from SharePoint: {str(e)}",
                    }
                )

    success_count = sum(1 for r in results if isinstance(r, FileSchema))
    error_count = len(results) - success_count

    logger.debug(
        "SharePoint file upload complete",
        extra={
            "total_files": len(file_ids),
            "success_count": success_count,
            "error_count": error_count,
        },
    )

    # Check if any uploads failed and return appropriate status code
    failed_files = [
        result for result in results if isinstance(result, dict) and "error" in result
    ]
    if failed_files:
        # If all files failed, return 500
        if len(failed_files) == len(results):
            error_messages = [
                result["error"]
                for result in failed_files
                if isinstance(result, dict) and "error" in result
            ]
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message=f"All file uploads failed. Errors: {error_messages}",
            )
            raise HTTPException(status_code=500, detail=err.model_dump())

    return results


@files_router.post("/files/local/upload", responses={401: {"model": ErrorSchema}})
async def upload_local_files(
    request: Request,
    files: list[UploadFile],
    knowledge_base_uuid: uuidpkg.UUID | None = None,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> list[FileSchema | dict[str, Any]]:
    """
    Upload one or more local files and optionally attach them to a knowledge base.
    Returns a list of results for each file (either FileSchema for success or error dict).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    file_repo = request.app.state.deps.file_repo
    user_repo = request.app.state.deps.user_repo

    # Get current user's UUID
    current_user = await user_repo.get_user(user_id=int(auth_ctx.user.id))
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    user_uuid = current_user.uuid

    # Validate knowledge base if provided
    knowledge_base_id = None
    knowledge_base = None
    knowledge_base_repo = None
    if knowledge_base_uuid:
        knowledge_base_repo = request.app.state.deps.knowledge_base_repo
        knowledge_base = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base or knowledge_base.owner_id != int(auth_ctx.user.id):
            err = ErrorSchema(
                code=ErrorCodes.UNKNOWN_ERROR,
                message="Knowledge Base not found or access denied",
            )
            raise HTTPException(status_code=404, detail=err.model_dump())
        knowledge_base_id = knowledge_base.id

    results: list[FileSchema | dict[str, Any]] = []
    for file in files:
        if not file or not file.filename or not file.filename.strip():
            results.append(
                {
                    "filename": getattr(file, "filename", None),
                    "error": "File must have a non-empty filename",
                }
            )
            continue

        file_extension = pathlib.Path(file.filename).suffix.lower().lstrip(".")
        if file_extension not in document_loader.SUPPORTED_FILE_TYPES:
            results.append(
                {
                    "filename": file.filename,
                    "error": f"Unsupported file type: {file_extension}",
                }
            )
            continue

        try:
            contents = await file.read()

            # Create directory structure based on base or user
            if knowledge_base_id:
                # Use base path for files attached to a base
                knowledge_base = (
                    await request.app.state.deps.knowledge_base_repo.get_knowledge_base(
                        current_user,
                        knowledge_base_uuid=knowledge_base_uuid,
                    )
                )
                file_dir = (
                    pathlib.Path(request.app.state.deps.upload_path)
                    / knowledge_base.path
                )
            else:
                # Use user's UUID for standalone files
                file_dir = pathlib.Path(request.app.state.deps.upload_path) / str(
                    user_uuid
                )

            fs = get_file_system()
            # Ensure directory exists
            try:
                fs.mkdir(str(file_dir), create_parents=True)
            except FileExistsError:
                pass

            file_path = str(file_dir / file.filename)

            # Save the file
            with fs.open(file_path, "wb") as buffer:
                buffer.write(contents)

            # Create file record in database
            file_data = FileCreate(
                filename=file.filename,
                source="local",
                file_path=file_path,
                mime_type=file.content_type,
                size_bytes=len(contents),
                knowledge_base_id=knowledge_base_id,
            )

            db_file = await file_repo.create_file(
                file_data, owner_id=int(auth_ctx.user.id)
            )

            # Encode the document in the background (don't wait for it)
            asyncio.create_task(
                get_or_create_encoded_content(
                    file=db_file,
                    file_repo=file_repo,
                    knowledge_base=knowledge_base,
                    knowledge_base_repo=knowledge_base_repo,
                )
            )

            results.append(FileSchema.from_file(db_file, owner_uuid=user_uuid))

        except Exception as e:
            logger.exception("Error processing file")
            results.append(
                {
                    "filename": file.filename,
                    "error": f"Failed to process file: {str(e)}",
                }
            )

    return results
