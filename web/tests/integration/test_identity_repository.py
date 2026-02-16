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

# Copyright 2025 DataRobot, Inc.
#
# Tests for IdentityRepository.upsert_identity focusing on concurrency safety and update semantics.

from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app import Deps
from app.users.identity import AuthSchema, IdentityRepository, IdentityUpdate
from app.users.user import UserCreate


@pytest.mark.asyncio
async def test_upsert_identity_create(db_deps: Deps) -> None:
    user_repo = db_deps.user_repo
    identity_repo: IdentityRepository = db_deps.identity_repo

    user = await user_repo.create_user(
        UserCreate(email="create@example.com", first_name="Al", last_name="Bo")
    )
    assert user.id

    identity = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-1",
    )

    assert identity.id is not None
    assert identity.user_id == user.id
    assert identity.provider_user_id == "google-user-1"


@pytest.mark.asyncio
async def test_upsert_identity_update_existing(db_deps: Deps) -> None:
    user_repo = db_deps.user_repo
    identity_repo: IdentityRepository = db_deps.identity_repo

    user = await user_repo.create_user(
        UserCreate(email="update@example.com", first_name="Al", last_name="Bo")
    )
    assert user.id

    created = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-2",
    )

    # Update access token via upsert
    updated = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-2",
        update=IdentityUpdate(access_token="new-token"),
    )

    assert updated.id == created.id
    assert updated.access_token == "new-token"


@pytest.mark.asyncio
async def test_upsert_identity_concurrent_insert_simulated(
    db_deps: Deps, monkeypatch: Any
) -> None:
    """Simulate race condition by raising IntegrityError on first commit attempt."""
    user_repo = db_deps.user_repo
    identity_repo: IdentityRepository = db_deps.identity_repo

    user = await user_repo.create_user(
        UserCreate(email="race@example.com", first_name="Al", last_name="Bo")
    )
    assert user.id

    # Accessing protected attr for test instrumentation.
    original_session_ctx = identity_repo._db.session

    call_counter = {"count": 0}

    @asynccontextmanager
    async def wrapped_session(writable: bool = False):  # type: ignore[no-untyped-def]
        async with original_session_ctx(writable) as sess:  # noqa: SIM117 (explicit for clarity)
            original_commit = sess.commit

            async def failing_commit():  # type: ignore[no-untyped-def]
                call_counter["count"] += 1
                if call_counter["count"] == 1:
                    raise IntegrityError("simulated", {}, None)  # type: ignore[arg-type]
                await original_commit()

            sess.commit = failing_commit  # type: ignore[method-assign]
            yield sess

    monkeypatch.setattr(identity_repo._db, "session", wrapped_session)

    identity = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-3",
    )

    assert identity.id is not None
    assert call_counter["count"] >= 1


@pytest.mark.asyncio
async def test_upsert_identity_preserves_fields_when_update_none_values_false(
    db_deps: Deps,
) -> None:
    """
    Verify that upsert_identity with update_none_values=False (default) preserves
    existing values when IdentityUpdate fields are explicitly set to None.
    """
    user_repo = db_deps.user_repo
    identity_repo: IdentityRepository = db_deps.identity_repo

    user = await user_repo.create_user(
        UserCreate(email="preserve@example.com", first_name="Al", last_name="Bo")
    )
    assert user.id

    # Create identity with datarobot metadata
    created = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.DATAROBOT,
        provider_id="datarobot_user",
        provider_type="datarobot_user",
        provider_user_id="dr-user-1",
        update=IdentityUpdate(
            datarobot_org_id="org-123",
            datarobot_tenant_id="tenant-456",
        ),
    )

    assert created.datarobot_org_id == "org-123"
    assert created.datarobot_tenant_id == "tenant-456"

    # Simulate the DataRobot scenario where profile_metadata doesn't have org_id/tenant_id
    # dict.get() returns None for missing keys, which would previously clear existing values
    profile_metadata: dict[str, str] = {}  # Missing org_id and tenant_id
    updated = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.DATAROBOT,
        provider_id="datarobot_user",
        provider_type="datarobot_user",
        provider_user_id="dr-user-1",
        update=IdentityUpdate(
            datarobot_org_id=profile_metadata.get("org_id"),  # Returns None
            datarobot_tenant_id=profile_metadata.get("tenant_id"),  # Returns None
        ),
        # update_none_values=False is the default
    )

    assert updated.id == created.id
    # Existing datarobot metadata should be preserved because update_none_values=False
    assert updated.datarobot_org_id == "org-123", (
        "datarobot_org_id should be preserved when None with update_none_values=False"
    )
    assert updated.datarobot_tenant_id == "tenant-456", (
        "datarobot_tenant_id should be preserved when None with update_none_values=False"
    )


@pytest.mark.asyncio
async def test_upsert_identity_clears_fields_when_update_none_values_true(
    db_deps: Deps,
) -> None:
    """
    Verify that upsert_identity can clear fields when update_none_values=True.

    This tests the OAuth re-authorization flow where tokens need to be explicitly
    cleared. By setting update_none_values=True, None values in IdentityUpdate
    will overwrite existing field values, enabling intentional token clearing.
    """
    user_repo = db_deps.user_repo
    identity_repo: IdentityRepository = db_deps.identity_repo

    user = await user_repo.create_user(
        UserCreate(email="clear@example.com", first_name="Al", last_name="Bo")
    )
    assert user.id

    # Create identity with tokens
    created = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-clear",
        update=IdentityUpdate(
            access_token="old-token",
            refresh_token="old-refresh",
        ),
    )

    assert created.access_token == "old-token"
    assert created.refresh_token == "old-refresh"

    # Clear tokens by setting them to None with update_none_values=True
    updated = await identity_repo.upsert_identity(
        user_id=user.id,
        auth_type=AuthSchema.OAUTH2,
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-clear",
        update=IdentityUpdate(
            access_token=None,  # Explicitly set to None to clear
            refresh_token=None,  # Explicitly set to None to clear
        ),
        update_none_values=True,  # Required to allow None values to clear fields
    )

    assert updated.id == created.id
    assert updated.access_token is None, (
        "access_token should be cleared when update_none_values=True"
    )
    assert updated.refresh_token is None, (
        "refresh_token should be cleared when update_none_values=True"
    )
