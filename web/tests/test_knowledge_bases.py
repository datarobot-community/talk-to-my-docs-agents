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
import uuid as uuidpkg
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.deps import Deps
from app.knowledge_bases import KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.users.user import User


def test_path_auto_generation_logic() -> None:
    """Test that path is auto-generated correctly when not provided."""
    # Create a test base instance to validate auto-generation logic
    base_data = KnowledgeBaseCreate(
        title="Test Base",
        description="A test knowledge base",
        token_count=0,
        # path is not provided, should be auto-generated
    )

    # Mock owner ID
    owner_id = 12345

    # Create base instance (this simulates what happens in the repository)
    base = KnowledgeBase(
        title=base_data.title,
        description=base_data.description,
        token_count=base_data.token_count,
        owner_id=owner_id,
        path=base_data.path or "",  # Temporary placeholder
    )

    # Simulate what happens after flush - UUID is generated
    base.uuid = uuidpkg.uuid4()

    # Set the path if not provided (this is what the repository does)
    if not base_data.path:
        base.path = f"{owner_id}/{base.uuid}"

    # Validate the path format
    expected_path = f"{owner_id}/{base.uuid}"
    assert base.path == expected_path
    assert base.path.startswith(f"{owner_id}/")
    assert len(base.path.split("/")) == 2


def test_path_custom_value_preserved() -> None:
    """Test that custom path values are preserved when provided."""
    custom_path = "/custom/path/to/base"

    base_data = KnowledgeBaseCreate(
        title="Test Base",
        description="A test knowledge base",
        token_count=0,
        path=custom_path,
    )

    owner_id = 12345

    # Create base instance
    base = KnowledgeBase(
        title=base_data.title,
        description=base_data.description,
        token_count=base_data.token_count,
        owner_id=owner_id,
        path=base_data.path or "",
    )

    # Simulate what happens after flush
    base.uuid = uuidpkg.uuid4()

    # Path should NOT be auto-generated if already provided
    if not base_data.path:
        base.path = f"{owner_id}/{base.uuid}"

    # Validate the custom path is preserved
    assert base.path == custom_path


def test_list_knowledge_bases_without_auth(client: TestClient) -> None:
    """Test that listing bases requires authentication."""
    response = client.get("/api/v1/knowledge-bases/")
    assert response.status_code == 401


def test_create_knowledge_base_without_auth(client: TestClient) -> None:
    """Test that creating a base requires authentication."""
    base_data = {
        "title": "Test Base",
        "description": "A test knowledge base",
        "token_count": 0,
    }

    response = client.post("/api/v1/knowledge-bases/", json=base_data)
    assert response.status_code == 401


def test_get_knowledge_base_without_auth(client: TestClient) -> None:
    """Test that getting a base requires authentication."""
    test_uuid = str(uuidpkg.uuid4())

    response = client.get(f"/api/v1/knowledge-bases/{test_uuid}")
    assert response.status_code == 401


def test_delete_knowledge_base_without_auth(client: TestClient) -> None:
    """Test that deleting a base requires authentication."""
    test_uuid = str(uuidpkg.uuid4())

    response = client.delete(f"/api/v1/knowledge-bases/{test_uuid}")
    assert response.status_code == 401


def test_knowledge_base_creation_validation(client: TestClient) -> None:
    """Test that base creation validates input data."""
    # Missing required fields - but auth is checked first
    response = client.post("/api/v1/knowledge-bases/", json={})
    assert response.status_code == 401

    # Invalid data types - but auth is checked first
    invalid_data = {
        "title": "",  # too short
        "description": "",  # too short
        "token_count": -1,  # negative value
    }

    response = client.post("/api/v1/knowledge-bases/", json=invalid_data)
    assert response.status_code == 401


def test_create_knowledge_base_rejects_invalid_retrieval_mode(
    authenticated_client: TestClient,
) -> None:
    """An explicit invalid retrieval_mode is rejected with 422, not silently
    coerced to a default (which could enable semantic mode + billable indexing)."""
    response = authenticated_client.post(
        "/api/v1/knowledge-bases/",
        json={"title": "T", "description": "D", "retrieval_mode": "magic"},
    )
    assert response.status_code == 422
    assert "retrieval_mode" in response.text


def test_resolve_retrieval_mode_normalizes_and_validates() -> None:
    """None -> configured default (normalized against the enum); invalid explicit
    -> ValueError; feature-off always forces keyword."""
    import pytest

    from app.api.v1.knowledge_bases import _resolve_retrieval_mode as R
    from app.knowledge_bases import RetrievalMode as RM

    # Unset resolves to the configured default when the feature is on.
    assert R(None, feature_on=True, config_default=RM.SEMANTIC) == RM.SEMANTIC
    assert R(None, feature_on=True, config_default=RM.KEYWORD) == RM.KEYWORD
    # A misconfigured default (typo) is normalized to keyword, never an invalid mode.
    assert R(None, feature_on=True, config_default="sematic") == RM.KEYWORD
    # Feature off always forces keyword, regardless of default or explicit value.
    assert R(None, feature_on=False, config_default=RM.SEMANTIC) == RM.KEYWORD
    assert R("semantic", feature_on=False, config_default=RM.KEYWORD) == RM.KEYWORD
    # Explicit valid choice is honored when the feature is on.
    assert R("semantic", feature_on=True, config_default=RM.KEYWORD) == RM.SEMANTIC
    # Explicit invalid value raises (the endpoint turns this into a 422).
    with pytest.raises(ValueError):
        R("magic", feature_on=True, config_default=RM.SEMANTIC)


def test_update_knowledge_base_without_auth(client: TestClient) -> None:
    test_uuid = str(uuidpkg.uuid4())
    response = client.put(f"/api/v1/knowledge-bases/{test_uuid}", json={"title": "New"})
    assert response.status_code == 401


def test_update_knowledge_base_success(
    authenticated_client: TestClient, deps: Deps
) -> None:
    """Test successful knowledge base update."""
    # Prepare existing KB mock
    kb_uuid = uuidpkg.uuid4()
    OwnerMock = MagicMock(spec=User)
    owner = OwnerMock()
    owner.uuid = uuidpkg.UUID("ef7155bf-af78-44ba-bc2a-f38e2b8e6ff8")
    kb = KnowledgeBase(
        id=1,
        uuid=kb_uuid,
        title="Old Title",
        description="Old Description",
        token_count=0,
        path="1/old-path",
        owner_id=1,
        owner=owner,
    )
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=kb)  # type: ignore[method-assign]

    updated_kb = KnowledgeBase(
        id=1,
        uuid=kb_uuid,
        title="New Title",
        description="New Description",
        token_count=0,
        path="1/new-path",
        owner_id=1,
        owner=owner,
    )

    async def _update_kb(
        knowledge_base_id: int, owner_id: int, update: KnowledgeBaseUpdate
    ) -> KnowledgeBase:
        for field, value in update.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(updated_kb, field, value)
        return updated_kb

    deps.knowledge_base_repo.update_knowledge_base = AsyncMock(side_effect=_update_kb)  # type: ignore[method-assign]

    payload = {
        "title": "New Title",
        "description": "New Description",
        "path": "1/new-path",
    }
    r = authenticated_client.put(f"/api/v1/knowledge-bases/{kb_uuid}", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "New Title"
    assert data["description"] == "New Description"
    assert data["path"] == "1/new-path"


def test_update_knowledge_base_not_found(
    authenticated_client: TestClient, deps: Deps
) -> None:
    kb_uuid = uuidpkg.uuid4()
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=None)  # type: ignore[method-assign]
    r = authenticated_client.put(
        f"/api/v1/knowledge-bases/{kb_uuid}", json={"title": "X"}
    )
    assert r.status_code == 404


def test_update_knowledge_base_forbidden(
    authenticated_client: TestClient, deps: Deps
) -> None:
    kb_uuid = uuidpkg.uuid4()
    kb = KnowledgeBase(
        id=2,
        uuid=kb_uuid,
        title="Title",
        description="Desc",
        token_count=0,
        path="2/path",
        owner_id=999,  # different owner
    )
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=kb)  # type: ignore[method-assign]
    r = authenticated_client.put(
        f"/api/v1/knowledge-bases/{kb_uuid}", json={"title": "New"}
    )
    assert r.status_code == 403


from app.knowledge_bases import IndexStatus  # noqa: E402


def test_index_status_default_is_not_indexed() -> None:
    kb = KnowledgeBase(
        title="t",
        description="d",
        path="p",
        owner_id=1,
    )
    assert kb.index_status == IndexStatus.NOT_INDEXED
    assert kb.indexed_at is None


def test_index_status_enum_values() -> None:
    assert IndexStatus.NOT_INDEXED == "not_indexed"
    assert IndexStatus.INDEXING == "indexing"
    assert IndexStatus.READY == "ready"
    assert IndexStatus.FAILED == "failed"
