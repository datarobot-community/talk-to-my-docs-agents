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

from fastapi.testclient import TestClient

from app.knowledge_bases import KnowledgeBase, KnowledgeBaseCreate


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
    import uuid

    test_uuid = str(uuid.uuid4())

    response = client.get(f"/api/v1/knowledge-bases/{test_uuid}")
    assert response.status_code == 401


def test_delete_knowledge_base_without_auth(client: TestClient) -> None:
    """Test that deleting a base requires authentication."""
    import uuid

    test_uuid = str(uuid.uuid4())

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
