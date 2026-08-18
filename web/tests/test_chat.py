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
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import litellm.exceptions
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import NoResultFound

from app.api.v1.chat import (
    _get_or_create_chat_id,
    _send_chat_agent_completion,
    _send_chat_completion,
)
from app.chats import Chat, ChatRepository
from app.deps import Deps
from app.messages import Message, MessageUpdate, Role
from app.users.user import User


# Fixtures
@pytest.fixture
def mock_dr_client() -> Generator[MagicMock, None, None]:
    with patch("datarobot.Client") as mock_client:
        client_instance = MagicMock()
        client_instance.token = "test-token"
        client_instance.endpoint = "https://test-endpoint.datarobot.com"
        mock_client.return_value = client_instance
        yield mock_client


@pytest.fixture
def mock_litellm_completion() -> Generator[MagicMock, None, None]:
    """Fixture for a successful (streaming) litellm completion.

    The fast grounded chat path streams (``async for chunk in await acompletion``),
    so the mock resolves to an async iterator of delta chunks that accumulate to
    "test".
    """
    with patch("litellm.acompletion") as mock_acompletion:

        async def _mock_acompletion(*args: Any, **kwargs: Any) -> Any:
            async def _stream() -> Any:
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "test"
                chunk.choices[0].delta.refusal = None
                yield chunk

            return _stream()

        mock_acompletion.side_effect = _mock_acompletion
        yield mock_acompletion


@pytest.fixture
def mock_message_repo() -> AsyncMock:
    """Fixture for mocking message repository with proper return values."""
    return AsyncMock(
        return_value=MagicMock(dump_json_compatible=lambda: {"content": "test"})
    )


@pytest.fixture
def mock_api_connection_error() -> litellm.exceptions.APIConnectionError:
    """Fixture to create a standard APIConnectionError for testing."""
    error_message = "Request is too large"
    return litellm.exceptions.APIConnectionError(
        f"litellm.APIConnectionError: DatarobotException - {error_message}",
        llm_provider="datarobot",
        model="test-model",
    )


@pytest.fixture
def sample_chat() -> Chat:
    """Fixture to create a test chat object."""
    return Chat(uuid=uuidpkg.uuid4(), name="Test Chat")


@pytest.fixture
def sample_user_message(sample_chat: Chat) -> Message:
    """Fixture to create a test user message object."""
    return Message(
        uuid=uuidpkg.uuid4(),
        chat_id=sample_chat.uuid,
        model="test-model",
        role=Role.USER,
        content="Hello, test!",
    )


@pytest.fixture
def sample_llm_message(sample_chat: Chat) -> Message:
    """Fixture to create a test user message object."""
    return Message(
        uuid=uuidpkg.uuid4(),
        chat_id=sample_chat.uuid,
        model="test-model",
        role=Role.ASSISTANT,
        content="Test response",
        in_progress=True,
    )


@pytest.fixture
def test_user() -> User:
    """Fixture to create a test user object."""
    return User(
        uuid=uuidpkg.uuid4(),
        email="test@example.com",
        first_name="Test",
        last_name="User",
    )


# Basic chat tests
async def test_new_chat(
    deps: Deps,
    authenticated_client: TestClient,
    mock_dr_client: MagicMock,
    mock_litellm_completion: MagicMock,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
) -> None:
    """Test chat completion endpoint with authenticated client."""
    with (
        patch.object(deps.chat_repo, "create_chat") as mock_create_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
    ):
        mock_create_chat.return_value = sample_chat
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]

        response = authenticated_client.post(
            "/api/v1/chat",
            json={
                "message": sample_user_message.content,
                "model": sample_user_message.model,
            },
        )
        assert response.status_code == 200
        assert response.json() == sample_chat.dump_json_compatible()

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        assert called_kwargs["update"] == MessageUpdate(
            content="test", in_progress=False
        )


def test_get_chats_with_authentication(
    deps: Deps, authenticated_client: TestClient, sample_chat: Chat
) -> None:
    """Example test showing how easy it is to test authenticated endpoints."""
    with (
        patch.object(
            deps.chat_repo, "get_all_chats", new_callable=AsyncMock
        ) as mock_get_chats,
        patch.object(
            deps.message_repo, "get_last_messages", new_callable=AsyncMock
        ) as mock_get_messages,
    ):
        mock_get_chats.return_value = [sample_chat]
        mock_get_messages.return_value = {}

        response = authenticated_client.get("/api/v1/chat")

        assert response.status_code == 200
        chats = response.json()
        assert len(chats) == 1
        assert chats[0]["name"] == "Test Chat"


# Chat deletion tests
def test_delete_chat_success(
    deps: Deps, authenticated_client: TestClient, sample_chat: Chat
) -> None:
    """Test successful chat deletion."""
    with patch.object(
        deps.chat_repo, "delete_chat", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = sample_chat

        response = authenticated_client.delete(f"/api/v1/chat/{sample_chat.uuid}")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["uuid"] == str(sample_chat.uuid)
        assert response_data["name"] == "Test Chat"

        mock_delete.assert_called_once_with(sample_chat.uuid)


def test_delete_chat_not_found(deps: Deps, authenticated_client: TestClient) -> None:
    """Test chat deletion when chat doesn't exist."""
    chat_uuid = uuidpkg.uuid4()

    with patch.object(
        deps.chat_repo, "delete_chat", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = None

        response = authenticated_client.delete(f"/api/v1/chat/{chat_uuid}")

        assert response.status_code == 404
        assert response.json()["detail"] == "chat not found"

        mock_delete.assert_called_once_with(chat_uuid)


def test_delete_chat_invalid_uuid(deps: Deps, authenticated_client: TestClient) -> None:
    """Test chat deletion with invalid UUID format."""
    invalid_uuid = "not-a-valid-uuid"

    response = authenticated_client.delete(f"/api/v1/chat/{invalid_uuid}")

    # FastAPI should return 422 for invalid UUID format
    assert response.status_code == 422


@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completions_with_invalid_knowledge_base_uuid(
    authenticated_client: TestClient,
    deps: Deps,
    mock_dr_client: MagicMock,
    mock_litellm_completion: MagicMock,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
) -> None:
    """Test that chat completions endpoint properly validates knowledge_base_id UUID format."""
    with (
        patch.object(deps.chat_repo, "create_chat") as mock_create_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_create_chat.return_value = sample_chat
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]

        response = authenticated_client.post(
            "/api/v1/chat",
            json={
                "message": sample_user_message.content,
                "model": model,
                "knowledge_base_id": "not-a-valid-uuid",
            },
        )
        assert response.status_code == 200
        assert response.json() == sample_chat.dump_json_compatible()

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        # Error includes component prefix
        expected_component = (
            "AI Agent" if model == "ttmdocs-agents" else "LLM Blueprint"
        )
        assert called_kwargs["update"] == MessageUpdate(
            error=f"{expected_component}: 400: Invalid knowledge_base_id format",
            in_progress=False,
        )


@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completion_with_valid_knowledge_base_uuid(
    authenticated_client: TestClient,
    deps: Deps,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
) -> None:
    """Test that chat agent completion endpoint properly validates knowledge_base_id UUID format."""
    with (
        patch.object(deps.chat_repo, "create_chat") as mock_create_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch.object(
            deps.knowledge_base_repo, "get_knowledge_base", new_callable=AsyncMock
        ) as mock_get_kb,
        patch("litellm.acompletion") as mock_acompletion,
        patch("app.api.v1.chat._augment_message_with_files") as mock_augment,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_create_chat.return_value = sample_chat
        mock_kb = MagicMock()
        valid_uuid = str(uuidpkg.uuid4())
        mock_kb.uuid = valid_uuid
        mock_get_kb.return_value = mock_kb
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]
        mock_augment.return_value = "test message"

        async def _mock_completion(*args: Any, **kwargs: Any) -> Any:
            # Support both streaming and non-streaming responses
            if kwargs.get("stream", False):

                async def _stream() -> Any:
                    # Simulate streaming chunks
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta = MagicMock()
                    chunk.choices[0].delta.content = "Test KB agent response"
                    chunk.choices[0].delta.refusal = None
                    yield chunk

                return _stream()
            else:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Test KB agent response",
                            }
                        }
                    ]
                }

        mock_acompletion.side_effect = _mock_completion

        authenticated_client.post(
            "/api/v1/chat",
            json={
                "message": "Hello, test!",
                "model": model,
                "knowledge_base_id": valid_uuid,
            },
            headers={"X-DataRobot-Identity-Token": "identity_token"},
        )

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        assert mock_acompletion.call_args.kwargs["extra_headers"] == {
            "X-DataRobot-Identity-Token": "identity_token"
        }

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        assert called_kwargs["update"] == MessageUpdate(
            content="Test KB agent response", in_progress=False
        )


@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completions_with_invalid_file_ids(
    authenticated_client: TestClient,
    deps: Deps,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
) -> None:
    """Test that chat completions endpoint properly validates file_ids UUID format."""
    with (
        patch.object(deps.chat_repo, "get_chat") as mock_get_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_get_chat.return_value = sample_chat
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]

        response = authenticated_client.post(
            f"/api/v1/chat/{sample_chat.uuid}/messages",
            json={
                "message": "Hello, test!",
                "model": model,
                "file_ids": ["not-a-valid-uuid", "also-invalid"],
            },
        )
        assert response.status_code == 200
        assert response.json() == [
            sample_user_message.dump_json_compatible(),
            sample_llm_message.dump_json_compatible(),
        ]

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        # Error includes component prefix
        expected_component = (
            "AI Agent" if model == "ttmdocs-agents" else "LLM Blueprint"
        )
        assert called_kwargs["update"] == MessageUpdate(
            error=f"{expected_component}: 400: Invalid file_id format: not-a-valid-uuid",
            in_progress=False,
        )


# Chat repository tests
@pytest.mark.asyncio
async def test_chat_repository_delete_chat_success(sample_chat: Chat) -> None:
    """Test ChatRepository.delete_chat method directly."""
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session
    mock_db.commit = AsyncMock()

    mock_response = MagicMock()
    mock_response.first.return_value = sample_chat
    mock_session.exec.return_value = mock_response

    repo = ChatRepository(mock_db)
    result = await repo.delete_chat(sample_chat.uuid)

    assert result == sample_chat
    mock_session.exec.assert_called_once()
    mock_session.delete.assert_called_once_with(sample_chat)
    mock_db.commit.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_chat_repository_delete_chat_not_found() -> None:
    """Test ChatRepository.delete_chat when chat doesn't exist."""
    mock_session = AsyncMock()
    mock_db = MagicMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session

    chat_uuid = uuidpkg.uuid4()

    mock_response = MagicMock()
    mock_response.first.return_value = None
    mock_session.exec.return_value = mock_response

    repo = ChatRepository(mock_db)
    result = await repo.delete_chat(chat_uuid)

    assert result is None
    mock_session.exec.assert_called_once()
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()


# _get_or_create_chat_id tests
@pytest.mark.asyncio
async def test_get_or_create_chat_id_handles_no_result_found(
    test_user: User,
) -> None:
    """Test that _get_or_create_chat_id properly handles NoResultFound exception."""
    mock_db = MagicMock()
    chat_repo = ChatRepository(mock_db)

    new_chat_uuid = uuidpkg.uuid4()
    mock_new_chat = MagicMock()
    mock_new_chat.uuid = new_chat_uuid

    existing_uuid_str = str(uuidpkg.uuid4())

    with (
        patch.object(chat_repo, "get_chat", new_callable=AsyncMock) as mock_get_chat,
        patch.object(
            chat_repo, "create_chat", new_callable=AsyncMock
        ) as mock_create_chat,
    ):
        mock_get_chat.side_effect = NoResultFound("No chat found")
        mock_create_chat.return_value = mock_new_chat

        result_uuid, was_created = await _get_or_create_chat_id(
            chat_repo, existing_uuid_str, test_user
        )

        assert was_created is True
        assert result_uuid == new_chat_uuid
        mock_get_chat.assert_called_once_with(uuidpkg.UUID(existing_uuid_str))
        mock_create_chat.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_chat_id_reuses_existing_chat(
    test_user: User,
    sample_chat: Chat,
) -> None:
    """Test that _get_or_create_chat_id reuses existing chat when found."""
    mock_db = MagicMock()
    chat_repo = ChatRepository(mock_db)

    existing_uuid_str = str(sample_chat.uuid)

    with (
        patch.object(chat_repo, "get_chat", new_callable=AsyncMock) as mock_get_chat,
        patch.object(
            chat_repo, "create_chat", new_callable=AsyncMock
        ) as mock_create_chat,
    ):
        mock_get_chat.return_value = sample_chat

        result_uuid, was_created = await _get_or_create_chat_id(
            chat_repo, existing_uuid_str, test_user
        )

        assert was_created is False
        assert result_uuid == sample_chat.uuid
        mock_get_chat.assert_called_once_with(sample_chat.uuid)
        mock_create_chat.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_chat_id_creates_new_chat_when_no_id_provided(
    test_user: User,
) -> None:
    """Test that _get_or_create_chat_id creates new chat when no chat_id is provided."""
    mock_db = MagicMock()
    chat_repo = ChatRepository(mock_db)

    new_chat_uuid = uuidpkg.uuid4()
    mock_new_chat = MagicMock()
    mock_new_chat.uuid = new_chat_uuid

    with (
        patch.object(chat_repo, "get_chat", new_callable=AsyncMock) as mock_get_chat,
        patch.object(
            chat_repo, "create_chat", new_callable=AsyncMock
        ) as mock_create_chat,
    ):
        mock_create_chat.return_value = mock_new_chat

        result_uuid, was_created = await _get_or_create_chat_id(
            chat_repo, None, test_user
        )

        assert was_created is True
        assert result_uuid == new_chat_uuid
        mock_get_chat.assert_not_called()
        mock_create_chat.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_chat_id_creates_new_chat_with_invalid_uuid_format(
    test_user: User,
) -> None:
    """Test that _get_or_create_chat_id creates new chat when chat_id has invalid UUID format."""
    mock_db = MagicMock()
    chat_repo = ChatRepository(mock_db)

    new_chat_uuid = uuidpkg.uuid4()
    mock_new_chat = MagicMock()
    mock_new_chat.uuid = new_chat_uuid

    with (
        patch.object(chat_repo, "get_chat", new_callable=AsyncMock) as mock_get_chat,
        patch.object(
            chat_repo, "create_chat", new_callable=AsyncMock
        ) as mock_create_chat,
    ):
        mock_create_chat.return_value = mock_new_chat

        invalid_chat_id = "not-a-valid-uuid-format"
        result_uuid, was_created = await _get_or_create_chat_id(
            chat_repo, invalid_chat_id, test_user
        )

        assert was_created is True
        assert result_uuid == new_chat_uuid
        mock_get_chat.assert_not_called()
        mock_create_chat.assert_called_once()


# APIConnectionError tests
@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completion_api_connection_error(
    deps: Deps,
    authenticated_client: TestClient,
    mock_dr_client: MagicMock,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
    mock_api_connection_error: litellm.exceptions.APIConnectionError,
) -> None:
    """Test that chat completion endpoint properly handles APIConnectionError."""
    with (
        patch.object(deps.chat_repo, "create_chat") as mock_create_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch("litellm.acompletion") as mock_acompletion,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_create_chat.return_value = sample_chat
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]
        mock_acompletion.side_effect = mock_api_connection_error

        response = authenticated_client.post(
            "/api/v1/chat",
            json={"message": "Hello, test!", "model": model},
        )

        assert response.status_code == 200
        assert response.json() == sample_chat.dump_json_compatible()

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        # Error is cleaned up with component prefix
        expected_component = (
            "AI Agent" if model == "ttmdocs-agents" else "LLM Blueprint"
        )
        assert called_kwargs["update"] == MessageUpdate(
            error=f"{expected_component}: Request is too large",
            in_progress=False,
        )


@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completion_api_connection_error_with_files(
    deps: Deps,
    authenticated_client: TestClient,
    mock_dr_client: MagicMock,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
) -> None:
    """Test that chat completion endpoint properly handles APIConnectionError."""
    with (
        patch.object(deps.chat_repo, "get_chat") as mock_get_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch.object(
            deps.file_repo, "get_files", new_callable=AsyncMock
        ) as mock_get_files,
        patch.object(
            deps.knowledge_base_repo, "get_knowledge_base", new_callable=AsyncMock
        ) as mock_get_kb,
        patch("litellm.acompletion") as mock_acompletion,
        patch("app.api.v1.chat._augment_message_with_files") as mock_augment,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_get_chat.return_value = sample_chat
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]
        mock_get_files.return_value = []
        mock_get_kb.return_value = None
        mock_augment.return_value = "augmented message with files"

        # Different error scenario
        error_message = "Connection timeout"
        mock_acompletion.side_effect = litellm.exceptions.APIConnectionError(
            f"litellm.APIConnectionError: {error_message}",
            llm_provider="datarobot",
            model=model,
        )

        response = authenticated_client.post(
            f"/api/v1/chat/{sample_chat.uuid}/messages",
            json={"message": "Hello, test!", "model": model},
        )

        assert response.status_code == 200
        assert response.json() == [
            sample_user_message.dump_json_compatible(),
            sample_llm_message.dump_json_compatible(),
        ]

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        # Error is cleaned up with component prefix and message extracted from JSON
        expected_component = (
            "AI Agent" if model == "ttmdocs-agents" else "LLM Blueprint"
        )
        assert called_kwargs["update"] == MessageUpdate(
            error=f"{expected_component}: {error_message}",
            in_progress=False,
        )


@pytest.mark.parametrize("model", ["test-model", "ttmdocs-agents"])
def test_chat_completion_api_connection_error_with_knowledge_base(
    authenticated_client: TestClient,
    deps: Deps,
    sample_chat: Chat,
    sample_user_message: Message,
    sample_llm_message: Message,
    model: str,
) -> None:
    """Test APIConnectionError handling in chat agent completion with knowledge base."""
    kb_uuid = uuidpkg.uuid4()
    with (
        patch.object(deps.chat_repo, "create_chat") as mock_create_chat,
        patch.object(
            deps.message_repo, "create_message", new_callable=AsyncMock
        ) as mock_create_msg,
        patch.object(
            deps.message_repo, "update_message", new_callable=AsyncMock
        ) as mock_update_msg,
        patch.object(
            deps.knowledge_base_repo, "get_knowledge_base", new_callable=AsyncMock
        ) as mock_get_kb,
        patch("app.api.v1.chat.get_knowledge_base_schema") as mock_get_schema,
        patch("litellm.acompletion") as mock_acompletion,
        patch("app.api.v1.chat._augment_message_with_files") as mock_augment,
        patch(
            "app.api.v1.chat._send_chat_completion", wraps=_send_chat_completion
        ) as chat_completion_spy,
        patch(
            "app.api.v1.chat._send_chat_agent_completion",
            wraps=_send_chat_agent_completion,
        ) as chat_agent_completion_spy,
    ):
        mock_create_chat.return_value = sample_chat
        sample_user_message.model = model
        sample_llm_message.model = model
        mock_create_msg.side_effect = [sample_user_message, sample_llm_message]

        # Mock knowledge base
        mock_kb = MagicMock()
        mock_kb.uuid = kb_uuid
        mock_get_kb.return_value = mock_kb

        # Mock knowledge base schema
        mock_schema = MagicMock()
        mock_schema.model_dump.return_value = {"description": "test schema"}
        mock_schema.description = "test knowledge base"
        mock_get_schema.return_value = mock_schema

        mock_augment.return_value = "test message"

        # Network error
        error_message = "Network unreachable"
        mock_acompletion.side_effect = litellm.exceptions.APIConnectionError(
            f"litellm.APIConnectionError: {error_message}",
            llm_provider="datarobot",
            model="test-model",
        )

        authenticated_client.post(
            "/api/v1/chat",
            json={
                "message": "Query the knowledge base",
                "model": model,
                "knowledge_base_id": str(kb_uuid),
            },
        )

        # Make sure the right completion function was called
        if model == "test-model":
            assert chat_completion_spy.call_count == 1
        if model == "ttmdocs-agents":
            assert chat_agent_completion_spy.call_count == 1

        called_kwargs = mock_update_msg.call_args.kwargs
        assert called_kwargs["uuid"] == sample_llm_message.uuid
        # Error is cleaned up with component prefix
        expected_component = (
            "AI Agent" if model == "ttmdocs-agents" else "LLM Blueprint"
        )
        assert called_kwargs["update"] == MessageUpdate(
            error=f"{expected_component}: {error_message}",
            in_progress=False,
        )


# Unit tests for error formatting helpers
class TestErrorFormatting:
    """Tests for error message formatting helpers."""

    def test_clean_error_message_strips_prefixes(self) -> None:
        """Test that error message prefixes are stripped."""
        from app.api.v1.chat import _clean_error_message

        assert (
            _clean_error_message("litellm.APIConnectionError: some error")
            == "some error"
        )
        assert _clean_error_message("DatarobotException - some error") == "some error"
        assert (
            _clean_error_message(
                "litellm.InternalServerError: InternalServerError: OpenAIException - ERROR: actual error"
            )
            == "actual error"
        )

    def test_is_wakeup_error(self) -> None:
        """Test wake-up error detection."""
        from app.api.v1.chat import _is_wakeup_error

        assert _is_wakeup_error("waiting for workload reach > 0 replicas")
        assert _is_wakeup_error("Inference server is unavailable")
        assert not _is_wakeup_error("some other error")

    def test_extract_json_message_from_api_errors(self) -> None:
        """Test JSON message extraction from various API error formats."""
        from app.api.v1.chat import _extract_json_message

        # OpenAI error format
        assert (
            _extract_json_message(
                '{"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}}'
            )
            == "Rate limit exceeded"
        )

        # Google/Vertex AI nested error
        assert (
            _extract_json_message(
                '{"error": {"code": 400, "message": "Invalid request", "status": "INVALID_ARGUMENT"}}'
            )
            == "Invalid request"
        )

        # Simple message field
        assert _extract_json_message('{"message": "Simple error"}') == "Simple error"

        # FastAPI detail (string)
        assert (
            _extract_json_message('{"detail": "Not authenticated"}')
            == "Not authenticated"
        )

        # FastAPI detail (array) - should return None, not stringify array
        assert _extract_json_message('{"detail": [{"msg": "field required"}]}') is None

        # Nested error.detail.message
        assert (
            _extract_json_message('{"error": {"detail": {"message": "Inner error"}}}')
            == "Inner error"
        )

        # No JSON
        assert _extract_json_message("plain text error") is None

        # Non-string input
        assert _extract_json_message(123) is None  # type: ignore[arg-type]
        assert _extract_json_message(None) is None  # type: ignore[arg-type]

        # Error field is a string (not a dict) - should not crash
        assert _extract_json_message('{"error": "Simple error string"}') is None

    def test_clean_error_message_nested_json(self) -> None:
        """Test cleaning of nested JSON errors like Google Vertex AI."""
        from app.api.v1.chat import _clean_error_message

        # Real nested error from Google Vertex AI
        nested_error = (
            '{"message":"ERROR: {\\n \\"error\\": {\\n \\"code\\": 400,\\n '
            '\\"message\\": \\"Request contains text fields that are too large.\\",\\n '
            '\\"status\\": \\"INVALID_ARGUMENT\\"\\n }\\n}\\n."}'
        )
        assert (
            _clean_error_message(nested_error)
            == "Request contains text fields that are too large."
        )

    def test_clean_error_message_strips_errno(self) -> None:
        """Test that OS error codes are stripped for cleaner user messages."""
        from app.api.v1.chat import _clean_error_message

        assert _clean_error_message("[Errno 50] Network is down") == "Network is down"
        assert (
            _clean_error_message("[Errno 111] Connection refused")
            == "Connection refused"
        )
        assert _clean_error_message("Connection refused") == "Connection refused"


class TestTaskProgressProcessor:
    """Test TaskProgressProcessor's extraction of task_progress events.

    These tests verify that the processor correctly identifies and parses
    task_progress JSON events, while accumulating all other content.
    No chunk assembly tests needed - httpx-sse guarantees complete chunks.
    """

    def test_valid_task_progress_returns_event(self) -> None:
        """Complete task_progress JSON returns parsed dict."""
        from app.api.v1.chat import TaskProgressProcessor

        processor = TaskProgressProcessor()
        result = processor.process_content(
            '{"task_progress": {"type": "task_started", "task_name": "Search"}}'
        )

        assert result == {"type": "task_started", "task_name": "Search"}
        assert processor.content == ""

    def test_non_task_progress_json_goes_to_content(self) -> None:
        """JSON not starting with marker ends up in content."""
        from app.api.v1.chat import TaskProgressProcessor

        processor = TaskProgressProcessor()
        result = processor.process_content('{"other": "data"}')

        assert result is None
        assert processor.content == '{"other": "data"}'

    def test_regular_text_goes_to_content(self) -> None:
        """Plain text not starting with marker goes to content."""
        from app.api.v1.chat import TaskProgressProcessor

        processor = TaskProgressProcessor()
        result = processor.process_content("Hello, this is regular content.")

        assert result is None
        assert processor.content == "Hello, this is regular content."

    def test_multiple_task_progress_events(self) -> None:
        """Multiple task_progress events are handled correctly."""
        from app.api.v1.chat import TaskProgressProcessor

        processor = TaskProgressProcessor()

        r1 = processor.process_content('{"task_progress": {"type": "started"}}')
        r2 = processor.process_content("Some content in between")
        r3 = processor.process_content('{"task_progress": {"type": "completed"}}')

        assert r1 == {"type": "started"}
        assert r2 is None
        assert r3 == {"type": "completed"}
        assert processor.content == "Some content in between"
