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

import json
import tempfile
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.files.contents import calculate_token_count, get_or_create_encoded_content
from app.files.models import File, FileRepository
from app.knowledge_bases import KnowledgeBase, KnowledgeBaseRepository


class TestCalculateTokenCount:
    """Test the token count calculation function."""

    def test_calculate_token_count_basic(self) -> None:
        """Test basic token count calculation."""
        content = {
            1: "This is page 1 content.",
            2: "This is page 2 content.",
        }
        expected = (
            len("This is page 1 content.") + len("This is page 2 content.")
        ) // 4
        assert calculate_token_count(content) == expected

    def test_calculate_token_count_empty(self) -> None:
        """Test token count for empty content."""
        assert calculate_token_count({}) == 0

    def test_calculate_token_count_single_page(self) -> None:
        """Test token count for single page."""
        content = {1: "Single page content"}
        expected = len("Single page content") // 4
        assert calculate_token_count(content) == expected

    def test_calculate_token_count_unicode(self) -> None:
        """Test token count with unicode characters."""
        content = {1: "Unicode content: 你好世界"}
        expected = len("Unicode content: 你好世界") // 4
        assert calculate_token_count(content) == expected


class TestGetOrCreateEncodedContent:
    """Test the get_or_create_encoded_content function."""

    @pytest.fixture
    def mock_knowledge_base(self) -> Mock:
        """Create a mock KnowledgeBase for testing."""
        kb = Mock(spec=KnowledgeBase)
        kb.id = 1
        kb.token_count = 100
        return kb

    @pytest.fixture
    def mock_knowledge_base_repo(self) -> AsyncMock:
        """Create a mock KnowledgeBaseRepository for testing."""
        repo = AsyncMock(spec=KnowledgeBaseRepository)
        return repo

    @pytest.fixture
    def mock_file(self) -> Mock:
        """Create a mock File for testing."""
        file = Mock(spec=File)
        file.id = uuid.uuid4()
        file.filename = "test_file.txt"
        file.source = "local"
        file.file_path = "/tmp/test_file.txt"
        file.owner_id = 1
        file.size_tokens = None  # Start with None to test token calculation
        return file

    @pytest.fixture
    def mock_file_for_temp_path(self, temp_file_with_content: str) -> Mock:
        """Create a mock File for a temp file path."""
        file = Mock(spec=File)
        file.id = uuid.uuid4()
        file.filename = Path(temp_file_with_content).name
        file.source = "local"
        file.file_path = temp_file_with_content
        file.owner_id = 1
        file.size_tokens = None  # Start with None to test token calculation
        return file

    @pytest.fixture
    def mock_file_repo(self) -> AsyncMock:
        """Create a mock FileRepository for testing."""
        repo = AsyncMock(spec=FileRepository)
        return repo

    @pytest.fixture
    def temp_file_with_content(self) -> Generator[str, None, None]:
        """Create a temporary file with some content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Sample file content for testing")
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
        Path(f"{temp_path}.encoded").unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_no_file(
        self, mock_file_repo: AsyncMock
    ) -> None:
        """Test function returns None for non-existent file."""
        # Create a mock file with non-existent path
        mock_file = Mock(spec=File)
        mock_file.id = uuid.uuid4()
        mock_file.filename = "nonexistent.txt"
        mock_file.file_path = "/nonexistent/file.txt"
        mock_file.source = "local"
        mock_file.owner_id = 1
        mock_file.size_tokens = None

        result = await get_or_create_encoded_content(mock_file, mock_file_repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_empty_path(
        self, mock_file_repo: AsyncMock
    ) -> None:
        """Test function returns None for empty file path."""
        # Create a mock file with empty path
        mock_file = Mock(spec=File)
        mock_file.id = uuid.uuid4()
        mock_file.filename = ""
        mock_file.file_path = ""
        mock_file.source = "local"
        mock_file.owner_id = 1
        mock_file.size_tokens = None

        result = await get_or_create_encoded_content(mock_file, mock_file_repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_cached(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function returns cached encoded content when available."""
        # Create a cached encoded file
        cached_content = {1: "Cached page 1", 2: "Cached page 2"}
        encoded_path = f"{temp_file_with_content}.encoded"

        with open(encoded_path, "w") as f:
            json.dump(cached_content, f)

        result = await get_or_create_encoded_content(
            mock_file_for_temp_path, mock_file_repo
        )

        assert result == {1: "Cached page 1", 2: "Cached page 2"}

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_cached_invalid_json(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function handles invalid cached JSON gracefully by re-encoding."""
        # Create an invalid encoded file
        encoded_path = f"{temp_file_with_content}.encoded"

        with open(encoded_path, "w") as f:
            f.write("invalid json content")

        # Mock the document loader to return test content
        mock_content = {1: "Test page 1", 2: "Test page 2"}

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ) as mock_loader:
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path, mock_file_repo
            )

        assert result == mock_content
        # Verify that the document loader was called (proving re-encoding happened)
        mock_loader.assert_called_once_with(temp_file_with_content)

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_new_encoding(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function creates new encoded content when cache doesn't exist."""
        mock_content = {1: "New page 1", 2: "New page 2"}

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ):
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path, mock_file_repo
            )

        assert result == mock_content

        # Verify the encoded file was created
        encoded_path = f"{temp_file_with_content}.encoded"
        assert Path(encoded_path).exists()

        with open(encoded_path, "r") as f:
            cached_data = json.load(f)
        # JSON serializes integer keys as strings
        assert cached_data == {"1": "New page 1", "2": "New page 2"}

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_encoding_failure(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function handles encoding failures gracefully."""
        with patch(
            "core.document_loader.convert_document_to_text",
            side_effect=Exception("Encoding failed"),
        ):
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path, mock_file_repo
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_updates_knowledge_base_token_count(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
        mock_knowledge_base: Mock,
        mock_knowledge_base_repo: AsyncMock,
    ) -> None:
        """Test function updates knowledge base token count when provided."""
        mock_content = {1: "Test page content"}
        expected_token_increment = calculate_token_count(mock_content)
        expected_new_token_count = (
            mock_knowledge_base.token_count + expected_token_increment
        )

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ):
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path,
                mock_file_repo,
                knowledge_base=mock_knowledge_base,
                knowledge_base_repo=mock_knowledge_base_repo,
            )

        assert result == mock_content

        # Verify the knowledge base token count was updated
        mock_knowledge_base_repo.update_knowledge_base_token_count.assert_called_once_with(
            mock_knowledge_base, expected_new_token_count
        )

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_no_update_without_knowledge_base_id(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
        mock_knowledge_base_repo: AsyncMock,
    ) -> None:
        """Test function doesn't update token count when knowledge base has no ID."""
        mock_content = {1: "Test page content"}
        kb_without_id = Mock(spec=KnowledgeBase)
        kb_without_id.id = None
        kb_without_id.token_count = 100

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ):
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path,
                mock_file_repo,
                knowledge_base=kb_without_id,
                knowledge_base_repo=mock_knowledge_base_repo,
            )

        assert result == mock_content

        # Verify the knowledge base token count was NOT updated
        mock_knowledge_base_repo.update_knowledge_base_token_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_no_update_without_repo(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
        mock_knowledge_base: Mock,
    ) -> None:
        """Test function doesn't update token count when no repository is provided."""
        mock_content = {1: "Test page content"}

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ):
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path,
                mock_file_repo,
                knowledge_base=mock_knowledge_base,
                knowledge_base_repo=None,
            )

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_cached_with_token_update(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
        mock_knowledge_base: Mock,
        mock_knowledge_base_repo: AsyncMock,
    ) -> None:
        """Test function doesn't update token count when using cached content."""
        # Create a cached encoded file
        cached_content = {1: "Cached page 1", 2: "Cached page 2"}
        encoded_path = f"{temp_file_with_content}.encoded"

        with open(encoded_path, "w") as f:
            json.dump(cached_content, f)

        result = await get_or_create_encoded_content(
            mock_file_for_temp_path,
            mock_file_repo,
            knowledge_base=mock_knowledge_base,
            knowledge_base_repo=mock_knowledge_base_repo,
        )

        assert result == cached_content

        # Verify the knowledge base token count was NOT updated for cached content
        mock_knowledge_base_repo.update_knowledge_base_token_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_cache_write_failure(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function handles cache write failures gracefully."""
        mock_content = {1: "Test page 1", 2: "Test page 2"}

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ):
            with patch("aiofiles.open", side_effect=Exception("Write failed")):
                result = await get_or_create_encoded_content(
                    mock_file_for_temp_path, mock_file_repo
                )

        # Should still return the content even if caching fails
        assert result == mock_content

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_type_conversion(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function properly converts cached content types."""
        # Create cached content with string keys (as they would be in JSON)
        cached_content = {"1": "Page 1", "2": "Page 2"}
        encoded_path = f"{temp_file_with_content}.encoded"

        with open(encoded_path, "w") as f:
            json.dump(cached_content, f)

        result = await get_or_create_encoded_content(
            mock_file_for_temp_path, mock_file_repo
        )

        # Should convert string keys to integers
        assert result == {1: "Page 1", 2: "Page 2"}
        assert result is not None
        assert all(isinstance(k, int) for k in result.keys())

    @pytest.mark.asyncio
    async def test_get_or_create_encoded_content_invalid_cached_type(
        self,
        temp_file_with_content: str,
        mock_file_for_temp_path: Mock,
        mock_file_repo: AsyncMock,
    ) -> None:
        """Test function re-encodes when cached content is not a dict."""
        # Create cached content that's not a dict
        cached_content = ["not", "a", "dict"]
        encoded_path = f"{temp_file_with_content}.encoded"

        with open(encoded_path, "w") as f:
            json.dump(cached_content, f)

        mock_content = {1: "New page 1", 2: "New page 2"}

        with patch(
            "core.document_loader.convert_document_to_text", return_value=mock_content
        ) as mock_loader:
            result = await get_or_create_encoded_content(
                mock_file_for_temp_path, mock_file_repo
            )

        # Should ignore invalid cache and create new content
        assert result == mock_content
        # Verify that the document loader was actually called (proving re-encoding happened)
        mock_loader.assert_called_once_with(temp_file_with_content)

        # Verify the corrupted cache was overwritten with valid content
        with open(encoded_path, "r") as f:
            updated_cache = json.load(f)
        # JSON serializes integer keys as strings
        assert updated_cache == {"1": "New page 1", "2": "New page 2"}
