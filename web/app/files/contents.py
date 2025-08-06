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
import json
import logging
import pathlib
from typing import TYPE_CHECKING

import aiofiles

from core import document_loader

if TYPE_CHECKING:
    from app.files.models import File, FileRepository
    from app.knowledge_bases import KnowledgeBase, KnowledgeBaseRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_token_count(encoded_content: dict[int, str]) -> int:
    """
    Calculate the estimated token count from encoded content.

    Args:
        encoded_content: Dictionary mapping page numbers to text content

    Returns:
        Estimated token count (total characters / 4)
    """
    total_chars = sum(len(text) for text in encoded_content.values())
    return total_chars // 4


async def get_or_create_encoded_content(
    file: "File",
    file_repo: "FileRepository | None" = None,
    knowledge_base: "KnowledgeBase | None" = None,
    knowledge_base_repo: "KnowledgeBaseRepository | None" = None,
) -> dict[int, str] | None:
    """
    Get encoded content for a file, creating and caching it if it doesn't exist.

    Args:
        file: File object containing the path and metadata
        file_repo: Optional FileRepository for updating file token count
        knowledge_base: Optional KnowledgeBase to update token count
        knowledge_base_repo: Optional KnowledgeBaseRepository for updating token count

    Returns:
        Dictionary mapping page numbers to text content, or None if encoding fails
    """
    if not file.file_path or not pathlib.Path(file.file_path).exists():
        return None

    file_path = file.file_path
    encoded_path = f"{file_path}.encoded"

    # Check if encoded file already exists and is newer than the original
    original_path = pathlib.Path(file_path)
    encoded_file_path = pathlib.Path(encoded_path)

    if (
        encoded_file_path.exists()
        and encoded_file_path.stat().st_mtime >= original_path.stat().st_mtime
    ):
        try:
            async with aiofiles.open(encoded_path, "r", encoding="utf-8") as f:
                content_str = await f.read()
                content = json.loads(content_str)
                # Ensure we return the correct type
                if isinstance(content, dict):
                    return {int(k): str(v) for k, v in content.items()}
                # If cached content is not a dict, fall through to re-encode
        except Exception as e:
            logger.warning(f"Failed to load cached encoded content: {e}")

    # Encode the document
    try:
        # Run document conversion in a thread pool since it's CPU-bound
        loop = asyncio.get_event_loop()
        encoded_content = await loop.run_in_executor(
            None, document_loader.convert_document_to_text, file_path
        )

        # Cache the encoded content
        try:
            async with aiofiles.open(encoded_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(encoded_content, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"Failed to cache encoded content: {e}")

        # Update token counts if repositories are provided
        token_increment = calculate_token_count(encoded_content)

        # Update knowledge base token count if provided
        if knowledge_base and knowledge_base_repo and knowledge_base.id:
            new_kb_token_count = knowledge_base.token_count + token_increment
            await knowledge_base_repo.update_knowledge_base_token_count(
                knowledge_base, new_kb_token_count
            )

        # Update file token count if file repository is provided
        if file_repo and file.id:
            from app.files.models import FileUpdate

            file_update = FileUpdate(size_tokens=token_increment)
            await file_repo.update_file(file.id, file_update, file.owner_id)

        return encoded_content

    except Exception as e:
        logger.error(f"Failed to encode document {file_path}: {e}")
        return None


async def get_or_create_encoded_content_legacy(
    file_path: str,
    knowledge_base: "KnowledgeBase | None" = None,
    knowledge_base_repo: "KnowledgeBaseRepository | None" = None,
) -> dict[int, str] | None:
    """
    Legacy function signature for backward compatibility.

    DEPRECATED: Use get_or_create_encoded_content with File object instead.

    Args:
        file_path: Path to the original file
        knowledge_base: Optional KnowledgeBase to update token count
        knowledge_base_repo: Optional KnowledgeBaseRepository for updating token count

    Returns:
        Dictionary mapping page numbers to text content, or None if encoding fails
    """
    # Create a minimal file-like object for the new function
    import uuid

    from app.files.models import File

    # Create a temporary file object with just the path
    temp_file = File(
        uuid=uuid.uuid4(),
        filename=pathlib.Path(file_path).name,
        source="legacy",
        file_path=file_path,
        owner_id=0,  # Will not be used for token updates
    )

    # Call the new function without file repository (no file token update)
    return await get_or_create_encoded_content(
        file=temp_file,
        file_repo=None,
        knowledge_base=knowledge_base,
        knowledge_base_repo=knowledge_base_repo,
    )
