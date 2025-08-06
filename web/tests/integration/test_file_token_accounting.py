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

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db import DBCtx
from app.files import FileCreate, FileRepository
from app.files.contents import get_or_create_encoded_content
from app.knowledge_bases import KnowledgeBaseCreate, KnowledgeBaseRepository
from app.users.user import User


class TestFileTokenAccounting:
    """Integration tests for file token accounting."""

    @pytest.mark.asyncio
    async def test_file_token_count_not_updated_on_encoding_bug(
        self, db_ctx: DBCtx, session_user: User
    ) -> None:
        """
        Test demonstrating the bug: when get_or_create_encoded_content is called,
        the file's size_tokens field is not updated, but the knowledge_base token_count is.
        """
        # Ensure we have a valid user ID
        assert session_user.id is not None, "session_user.id should not be None"

        # Create repositories
        file_repo = FileRepository(db_ctx)
        kb_repo = KnowledgeBaseRepository(db_ctx)

        # Create a knowledge base
        kb_data = KnowledgeBaseCreate(
            title="Test KB", description="Test knowledge base", token_count=0
        )
        knowledge_base = await kb_repo.create_knowledge_base(kb_data, session_user.id)

        # Create a temporary file with content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("This is test content for the file that will be encoded.")
            temp_file_path = f.name

        try:
            # Create a file in the database
            file_data = FileCreate(
                filename="test_file.txt",
                source="local",
                file_path=temp_file_path,
                mime_type="text/plain",
                size_bytes=100,
                size_tokens=0,  # Initially 0
                knowledge_base_id=knowledge_base.id,
            )
            db_file = await file_repo.create_file(file_data, owner_id=session_user.id)

            # Get initial values
            initial_file_tokens = db_file.size_tokens
            initial_kb_tokens = knowledge_base.token_count

            # Mock the document encoding to return predictable content
            mock_encoded_content = {
                1: "This is test content for the file that will be encoded."
            }
            expected_token_count = len(mock_encoded_content[1]) // 4  # 14 tokens

            with patch(
                "core.document_loader.convert_document_to_text",
                return_value=mock_encoded_content,
            ):
                # Call get_or_create_encoded_content (this should update both file and KB)
                result = await get_or_create_encoded_content(
                    file=db_file,
                    file_repo=file_repo,
                    knowledge_base=knowledge_base,
                    knowledge_base_repo=kb_repo,
                )

            assert result == mock_encoded_content

            # Refresh the file from the database
            updated_file = await file_repo.get_file(file_id=db_file.id)
            assert updated_file is not None, "File should exist after encoding"

            # Refresh the knowledge base from the database
            updated_kb = await kb_repo.get_knowledge_base(
                knowledge_base_id=knowledge_base.id
            )
            assert updated_kb is not None, "Knowledge base should exist after encoding"

            assert (
                updated_file.size_tokens == initial_file_tokens + expected_token_count
            ), (
                f"File size_tokens should be updated from {initial_file_tokens} to "
                f"{initial_file_tokens + expected_token_count}, but got {updated_file.size_tokens}"
            )

            # The knowledge base token count IS updated (this part works)
            assert updated_kb.token_count == initial_kb_tokens + expected_token_count

        finally:
            # Cleanup
            Path(temp_file_path).unlink(missing_ok=True)
            Path(f"{temp_file_path}.encoded").unlink(missing_ok=True)
