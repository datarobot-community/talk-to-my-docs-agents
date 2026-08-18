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
"""Endpoint tests for pgvector-backed search, KB delete, and file-delete reindex."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.knowledge_bases import IndexStatus, KnowledgeBase


def _fake_kb(
    kb_uuid: str, kb_id: int = 1, retrieval_mode: str = "semantic"
) -> MagicMock:
    kb = MagicMock(spec=KnowledgeBase)
    kb.id = kb_id
    kb.uuid = kb_uuid
    kb.index_status = IndexStatus.READY
    kb.retrieval_mode = retrieval_mode
    return kb


async def test_search_returns_chunks_from_vector_store(
    authenticated_client: TestClient,
) -> None:
    """The endpoint returns the chunks the pgvector store retrieves."""
    kb_uuid = "11111111-1111-1111-1111-111111111111"
    deps = authenticated_client.app.state.deps
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=_fake_kb(kb_uuid)
    )
    deps.vector_store = MagicMock()
    deps.vector_store.retrieve = AsyncMock(
        return_value=[
            {
                "text": "relevant document passage",
                "score": 0.91,
                "source": "policy.pdf",
                "metadata": {},
            }
        ]
    )

    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{kb_uuid}/search",
        params={"q": "relevant passage", "top_k": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["text"] == "relevant document passage"
    assert data["results"][0]["score"] == 0.91
    assert data["results"][0]["source"] == "policy.pdf"
    deps.vector_store.retrieve.assert_awaited_once()


async def test_search_empty_when_no_vector_store(
    authenticated_client: TestClient,
) -> None:
    """No vector store configured -> empty results (not an error)."""
    kb_uuid = "22222222-2222-2222-2222-222222222222"
    deps = authenticated_client.app.state.deps
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=_fake_kb(kb_uuid)
    )
    deps.vector_store = None

    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{kb_uuid}/search", params={"q": "anything"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_empty_when_not_indexed(
    authenticated_client: TestClient,
) -> None:
    """Indexed-but-no-matches (or not yet indexed) -> empty results."""
    kb_uuid = "55555555-5555-5555-5555-555555555555"
    deps = authenticated_client.app.state.deps
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=_fake_kb(kb_uuid)
    )
    deps.vector_store = MagicMock()
    deps.vector_store.retrieve = AsyncMock(return_value=[])

    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{kb_uuid}/search", params={"q": "anything"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_empty_in_keyword_mode(
    authenticated_client: TestClient,
) -> None:
    """A keyword-mode KB never hits the vector store (original behavior)."""
    kb_uuid = "66666666-6666-6666-6666-666666666666"
    deps = authenticated_client.app.state.deps
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=_fake_kb(kb_uuid, retrieval_mode="keyword")
    )
    deps.vector_store = MagicMock()
    deps.vector_store.retrieve = AsyncMock(return_value=[{"text": "x", "score": 1.0}])

    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{kb_uuid}/search", params={"q": "anything"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []
    deps.vector_store.retrieve.assert_not_awaited()  # gated off in keyword mode


async def test_search_empty_while_indexing(
    authenticated_client: TestClient,
) -> None:
    """A semantic KB whose index is not READY (mid-rebuild) returns empty results
    and never hits the store, matching the chat path's READY gate."""
    kb_uuid = "77777777-7777-7777-7777-777777777777"
    deps = authenticated_client.app.state.deps
    kb = _fake_kb(kb_uuid)
    kb.index_status = IndexStatus.INDEXING
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=kb)
    deps.vector_store = MagicMock()
    deps.vector_store.retrieve = AsyncMock(return_value=[{"text": "x", "score": 1.0}])

    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{kb_uuid}/search", params={"q": "anything"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []
    deps.vector_store.retrieve.assert_not_awaited()  # gated off until READY


async def test_search_returns_404_for_unknown_kb(
    authenticated_client: TestClient,
) -> None:
    unknown_uuid = "99999999-9999-9999-9999-999999999999"
    authenticated_client.app.state.deps.knowledge_base_repo.get_knowledge_base = (
        AsyncMock(return_value=None)
    )
    response = authenticated_client.get(
        f"/api/v1/knowledge-bases/{unknown_uuid}/search", params={"q": "anything"}
    )
    assert response.status_code == 404


async def test_delete_kb_removes_vectors(
    authenticated_client: TestClient,
) -> None:
    """Deleting a KB removes its vectors from the pgvector store."""
    kb_uuid = "33333333-3333-3333-3333-333333333333"
    deps = authenticated_client.app.state.deps
    kb = _fake_kb(kb_uuid)
    kb.owner_id = int(authenticated_client.app_user.id)  # type: ignore[attr-defined]
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=kb)
    deps.knowledge_base_repo.delete_knowledge_base = AsyncMock(return_value=True)
    deps.vector_store = MagicMock()
    deps.vector_store.delete_kb = AsyncMock()

    response = authenticated_client.delete(f"/api/v1/knowledge-bases/{kb_uuid}")

    assert response.status_code == 200
    deps.vector_store.delete_kb.assert_awaited_once_with(str(kb_uuid))


async def test_delete_file_triggers_reindex(
    authenticated_client: TestClient,
) -> None:
    """Deleting a file from a KB schedules a re-index so its chunks drop out."""
    kb_uuid = "44444444-4444-4444-4444-444444444444"
    deps = authenticated_client.app.state.deps

    file = MagicMock()
    file.id = 7
    file.knowledgebase = MagicMock()
    file.knowledgebase.uuid = kb_uuid
    deps.file_repo.get_file = AsyncMock(return_value=file)
    deps.file_repo.delete_file = AsyncMock(return_value=True)

    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=_fake_kb(kb_uuid)
    )
    deps.vector_store = MagicMock()

    with patch("app.api.v1.files.index_knowledge_base", new=AsyncMock()) as index_mock:
        response = authenticated_client.delete(f"/api/v1/files/{kb_uuid}")

    assert response.status_code == 200
    index_mock.assert_called_once()
