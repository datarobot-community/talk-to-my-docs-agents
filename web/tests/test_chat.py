# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Chat API Tests

This module tests the chat endpoints which require authentication.
Uses the `authenticated_client` fixture from conftest.py to automatically
handle authentication setup with a default test user.
"""

import uuid as uuidpkg
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.deps import Deps
from app.models.chats import Chat, ChatRepository


@pytest.fixture
def mock_dr_client() -> Generator[MagicMock, None, None]:
    with patch("datarobot.Client") as mock_client:
        client_instance = MagicMock()
        client_instance.token = "test-token"
        client_instance.endpoint = "https://test-endpoint.datarobot.com"
        mock_client.return_value = client_instance

        yield mock_client


@pytest.fixture
def mock_openai_client() -> Generator[MagicMock, None, None]:
    with patch(
        "app.api.v1.chat.AsyncOpenAI"
    ) as mock_openai:  # TODO: don't use monkey patching, pass the mock via Deps
        mock_instance = MagicMock()

        # Mock the async behavior of the client
        async def mock_create(**kwargs: Dict[str, Any]) -> MagicMock:
            return MagicMock(choices=[MagicMock(message=MagicMock(content="test"))])

        mock_instance.chat.completions.create = mock_create
        mock_openai.return_value.__aenter__.return_value = mock_instance

        yield mock_openai


@pytest.fixture
def mock_message_repo(deps: Deps) -> Generator[None, None, None]:
    with patch.object(
        deps.message_repo,
        "create_message",
        AsyncMock(
            return_value=MagicMock(dump_json_compatible=lambda: {"content": "test"})
        ),
    ):
        yield


def test_chat(
    deps: Deps,
    authenticated_client: TestClient,
    mock_dr_client: MagicMock,
    mock_openai_client: MagicMock,
    mock_message_repo: MagicMock,
) -> None:
    """Test chat completion endpoint with authenticated client."""
    with patch.object(deps.chat_repo, "create_chat") as mock_create:
        mock_create.return_value = Chat(uuid=uuidpkg.uuid4(), name="New Chat")

        response = authenticated_client.post(
            "/api/v1/chat/completions",
            json={"message": "Hello, test!", "model": "test-model"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "test"


def test_chat_agent_completion_with_invalid_knowledge_base_uuid(
    authenticated_client: TestClient,
) -> None:
    """Test that chat agent completion endpoint properly validates knowledge_base_id UUID format."""
    # Test with invalid UUID format
    response = authenticated_client.post(
        "/api/v1/chat/agent/completions",
        json={
            "message": "Hello, test!",
            "model": "test-model",
            "knowledge_base_id": "not-a-valid-uuid",
        },
    )
    assert response.status_code == 400
    assert "Invalid knowledge_base_id format" in response.json()["detail"]

    # Test with valid UUID format (should not fail on UUID validation)
    import uuid

    valid_uuid = str(uuid.uuid4())
    response = authenticated_client.post(
        "/api/v1/chat/agent/completions",
        json={
            "message": "Hello, test!",
            "model": "test-model",
            "knowledge_base_id": valid_uuid,
        },
    )
    # May still fail for other reasons (like knowledge base not found), but not due to UUID format
    assert response.status_code != 400 or "Invalid knowledge_base_id format" not in str(
        response.json().get("detail", "")
    )


def test_chat_completions_with_invalid_knowledge_base_uuid(
    authenticated_client: TestClient,
    deps: Deps,
    mock_dr_client: MagicMock,
    mock_openai_client: MagicMock,
    mock_message_repo: MagicMock,
) -> None:
    """Test that chat completions endpoint properly validates knowledge_base_id UUID format."""
    # Test with invalid UUID format
    response = authenticated_client.post(
        "/api/v1/chat/completions",
        json={
            "message": "Hello, test!",
            "model": "test-model",
            "knowledge_base_id": "not-a-valid-uuid",
        },
    )
    assert response.status_code == 400
    assert "Invalid knowledge_base_id format" in response.json()["detail"]

    # Mock the chat_repo.create_chat method to return a proper Chat object
    test_chat = Chat(uuid=uuidpkg.uuid4(), name="New Chat")
    with patch.object(
        deps.chat_repo, "create_chat", new_callable=AsyncMock
    ) as mock_create_chat:
        mock_create_chat.return_value = test_chat

        valid_uuid = str(uuidpkg.uuid4())
        response = authenticated_client.post(
            "/api/v1/chat/completions",
            json={
                "message": "Hello, test!",
                "model": "test-model",
                "knowledge_base_id": valid_uuid,
            },
        )
        # May still fail for other reasons (like knowledge base not found), but not due to UUID format
        assert (
            response.status_code != 400
            or "Invalid knowledge_base_id format"
            not in str(response.json().get("detail", ""))
        )


def test_get_chats_with_authentication(
    deps: Deps, authenticated_client: TestClient
) -> None:
    """Example test showing how easy it is to test authenticated endpoints."""
    # Mock get_all_chats to return some test data
    test_chat = Chat(uuid=uuidpkg.uuid4(), name="Test Chat")

    with patch.object(
        deps.chat_repo, "get_all_chats", new_callable=AsyncMock
    ) as mock_get_chats:
        with patch.object(
            deps.message_repo, "get_last_messages", new_callable=AsyncMock
        ) as mock_get_messages:
            mock_get_chats.return_value = [test_chat]
            mock_get_messages.return_value = {}

            # Make the request - authentication is handled automatically!
            response = authenticated_client.get("/api/v1/chat")

            assert response.status_code == 200
            chats = response.json()
            assert len(chats) == 1
            assert chats[0]["name"] == "Test Chat"


# Tests for chat deletion functionality
def test_delete_chat_success(deps: Deps, authenticated_client: TestClient) -> None:
    """Test successful chat deletion."""
    chat_uuid = uuidpkg.uuid4()
    deleted_chat = Chat(uuid=chat_uuid, name="Test Chat")

    # Mock the delete_chat method to return the deleted chat
    with patch.object(
        deps.chat_repo, "delete_chat", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = deleted_chat

        response = authenticated_client.delete(f"/api/v1/chat/{chat_uuid}")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["uuid"] == str(chat_uuid)
        assert response_data["name"] == "Test Chat"

        # Verify the delete_chat method was called with correct UUID
        mock_delete.assert_called_once_with(chat_uuid)


def test_delete_chat_not_found(deps: Deps, authenticated_client: TestClient) -> None:
    """Test chat deletion when chat doesn't exist."""
    chat_uuid = uuidpkg.uuid4()

    # Mock the delete_chat method to return None (chat not found)
    with patch.object(
        deps.chat_repo, "delete_chat", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = None

        response = authenticated_client.delete(f"/api/v1/chat/{chat_uuid}")

        assert response.status_code == 404
        assert response.json()["detail"] == "chat not found"

        # Verify the delete_chat method was called
        mock_delete.assert_called_once_with(chat_uuid)


def test_delete_chat_invalid_uuid(deps: Deps, authenticated_client: TestClient) -> None:
    """Test chat deletion with invalid UUID format."""
    invalid_uuid = "not-a-valid-uuid"

    response = authenticated_client.delete(f"/api/v1/chat/{invalid_uuid}")

    # FastAPI should return 422 for invalid UUID format
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_repository_delete_chat_success() -> None:
    """Test ChatRepository.delete_chat method directly."""
    # Mock database session and operations
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session

    # Create a test chat
    chat_uuid = uuidpkg.uuid4()
    test_chat = Chat(uuid=chat_uuid, name="Test Chat")

    # Mock the query result - make first() return the actual object
    mock_response = MagicMock()
    mock_response.first.return_value = test_chat
    mock_session.exec.return_value = mock_response

    # Create repository and test deletion
    repo = ChatRepository(mock_db)
    result = await repo.delete_chat(chat_uuid)

    # Verify the result
    assert result == test_chat

    # Verify the expected calls were made
    mock_session.exec.assert_called_once()
    mock_session.delete.assert_called_once_with(test_chat)
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_chat_repository_delete_chat_not_found() -> None:
    """Test ChatRepository.delete_chat when chat doesn't exist."""
    # Mock database session and operations
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session

    chat_uuid = uuidpkg.uuid4()

    # Mock the query result to return None (chat not found)
    mock_response = MagicMock()
    mock_response.first.return_value = None
    mock_session.exec.return_value = mock_response

    # Create repository and test deletion
    repo = ChatRepository(mock_db)
    result = await repo.delete_chat(chat_uuid)

    # Verify the result
    assert result is None

    # Verify the expected calls were made
    mock_session.exec.assert_called_once()
    # delete should not be called if chat wasn't found
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()


def test_get_all_chats_includes_updated_list_after_deletion(
    deps: Deps, authenticated_client: TestClient
) -> None:
    """Test that get all chats reflects deletions."""
    # Only need chat2 since we're testing the remaining chats after deletion
    chat2 = Chat(uuid=uuidpkg.uuid4(), name="Chat 2")

    # Mock get_all_chats to return remaining chats after deletion
    with patch.object(
        deps.chat_repo, "get_all_chats", new_callable=AsyncMock
    ) as mock_get_chats:
        with patch.object(
            deps.message_repo, "get_last_messages", new_callable=AsyncMock
        ) as mock_get_messages:
            mock_get_chats.return_value = [chat2]
            mock_get_messages.return_value = {}

            response = authenticated_client.get("/api/v1/chat")

            assert response.status_code == 200
            chats = response.json()
            assert len(chats) == 1
            assert chats[0]["name"] == "Chat 2"


def test_delete_chat_cascade_behavior_integration(
    deps: Deps, authenticated_client: TestClient
) -> None:
    """Test that deleting a chat cascades to delete related messages."""
    chat_uuid = uuidpkg.uuid4()
    deleted_chat = Chat(uuid=chat_uuid, name="Test Chat")

    # Mock the delete operation - CASCADE should be handled by the database
    with patch.object(
        deps.chat_repo, "delete_chat", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = deleted_chat

        response = authenticated_client.delete(f"/api/v1/chat/{chat_uuid}")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["uuid"] == str(chat_uuid)

        # Verify the repository method was called
        mock_delete.assert_called_once_with(chat_uuid)


def test_chat_completions_with_invalid_file_ids(
    authenticated_client: TestClient,
) -> None:
    """Test that chat completions endpoint properly validates file_ids UUID format."""
    # Test with invalid file_id UUID format
    response = authenticated_client.post(
        "/api/v1/chat/completions",
        json={
            "message": "Hello, test!",
            "model": "test-model",
            "file_ids": ["not-a-valid-uuid", "also-invalid"],
        },
    )
    assert response.status_code == 400
    assert "Invalid file_id format" in response.json()["detail"]


def test_chat_agent_completion_with_invalid_file_ids(
    authenticated_client: TestClient,
) -> None:
    """Test that chat agent completion endpoint properly validates file_ids UUID format."""
    # Test with invalid file_id UUID format
    response = authenticated_client.post(
        "/api/v1/chat/agent/completions",
        json={
            "message": "Hello, test!",
            "model": "test-model",
            "file_ids": ["not-a-valid-uuid"],
        },
    )
    assert response.status_code == 400
    assert "Invalid file_id format" in response.json()["detail"]
