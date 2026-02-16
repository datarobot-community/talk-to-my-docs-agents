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
"""
Tests for the needs_reauth OAuth token revocation handling feature.

This feature handles the case where a user revokes access from a provider's
security settings (e.g., Google or Box). When this happens:
1. Token refresh fails with OAuthServiceError
2. The identity is marked with needs_reauth=True
3. The UI shows a warning prompting the user to reconnect
4. After successful re-authorization, needs_reauth is cleared to False
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import Deps
from app.users.identity import IdentityCreate, IdentityUpdate


@pytest.mark.asyncio
async def test__identity__needs_reauth_default_false(db_deps: Deps) -> None:
    """New identities should have needs_reauth=False by default."""
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google_drive",
            provider_user_id="test-user-id",
        )
    )

    assert identity.needs_reauth is False


@pytest.mark.asyncio
async def test__identity__update_needs_reauth_to_true(db_deps: Deps) -> None:
    """Test that needs_reauth can be updated to True."""
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google_drive",
            provider_user_id="test-user-id",
            needs_reauth=False,
        )
    )

    assert identity.id is not None

    # Update to mark as needing re-auth
    await db_deps.identity_repo.update_identity(
        identity_id=identity.id,
        update=IdentityUpdate(needs_reauth=True),
    )

    updated = await db_deps.identity_repo.get_identity_by_id(identity.id)
    assert updated is not None
    assert updated.needs_reauth is True


@pytest.mark.asyncio
async def test__identity__update_needs_reauth_to_false(db_deps: Deps) -> None:
    """Test that needs_reauth can be cleared back to False."""
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google_drive",
            provider_user_id="test-user-id",
            needs_reauth=True,  # Start with True
        )
    )

    assert identity.id is not None
    assert identity.needs_reauth is True

    # Clear the flag
    await db_deps.identity_repo.update_identity(
        identity_id=identity.id,
        update=IdentityUpdate(needs_reauth=False),
    )

    updated = await db_deps.identity_repo.get_identity_by_id(identity.id)
    assert updated is not None
    assert updated.needs_reauth is False


@pytest.mark.asyncio
async def test__identity__update_only_needs_reauth_preserves_other_fields(
    db_deps: Deps,
) -> None:
    """
    Test that updating only needs_reauth doesn't affect other identity fields.
    """
    original_token = "original-access-token"
    original_refresh = "original-refresh-token"
    original_expires = datetime.now(UTC) + timedelta(hours=1)

    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google_drive",
            provider_user_id="test-user-id",
            access_token=original_token,
            refresh_token=original_refresh,
            access_token_expires_at=original_expires,
            needs_reauth=False,
        )
    )

    assert identity.id is not None

    # Update only needs_reauth
    await db_deps.identity_repo.update_identity(
        identity_id=identity.id,
        update=IdentityUpdate(needs_reauth=True),
    )

    updated = await db_deps.identity_repo.get_identity_by_id(identity.id)
    assert updated is not None

    # needs_reauth should be updated
    assert updated.needs_reauth is True

    # Other fields should remain unchanged
    assert updated.access_token == original_token
    assert updated.refresh_token == original_refresh
    assert updated.access_token_expires_at is not None
    # Compare without microseconds due to potential DB precision differences
    assert updated.access_token_expires_at.replace(
        microsecond=0
    ) == original_expires.replace(microsecond=0, tzinfo=None)


@pytest.mark.asyncio
async def test__identity__multiple_identities_independent_needs_reauth(
    db_deps: Deps,
) -> None:
    """
    Test that needs_reauth is independent for each identity.
    A user with multiple provider connections should have independent needs_reauth states.
    """
    # Create Google identity
    google_identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google_drive",
            provider_user_id="google-user-id",
            needs_reauth=False,
        )
    )

    # Create Box identity for the same user
    box_identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="box",
            provider_type="box",
            provider_user_id="box-user-id",
            needs_reauth=False,
        )
    )

    assert google_identity.id is not None
    assert box_identity.id is not None

    # Mark only Google as needing reauth
    await db_deps.identity_repo.update_identity(
        identity_id=google_identity.id,
        update=IdentityUpdate(needs_reauth=True),
    )

    # Verify Google needs reauth but Box doesn't
    updated_google = await db_deps.identity_repo.get_identity_by_id(google_identity.id)
    updated_box = await db_deps.identity_repo.get_identity_by_id(box_identity.id)

    assert updated_google is not None
    assert updated_box is not None
    assert updated_google.needs_reauth is True
    assert updated_box.needs_reauth is False
