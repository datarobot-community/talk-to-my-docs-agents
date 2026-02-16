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
from datetime import UTC, datetime, timedelta

import pytest
from datarobot.auth.datarobot.exceptions import OAuthServiceError
from datarobot.auth.oauth import OAuthToken

from app import Deps
from app.users.identity import IdentityCreate
from app.users.tokens import Tokens


async def test__tokens__custom_token_mgmt__no_cached_token(
    db_deps: Deps, oauth_token: OAuthToken
) -> None:
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    db_deps.auth.refresh_access_token.return_value = oauth_token  # type: ignore[attr-defined]

    token = await tokens.get_access_token(identity=identity.to_data())

    assert token.access_token == oauth_token.access_token
    assert token.expires_at == oauth_token.expires_at

    # make sure the token was cached
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity
    assert token.access_token == updated_identity.access_token
    assert updated_identity.access_token_expires_at
    assert token.expires_at == updated_identity.access_token_expires_at.replace(
        tzinfo=UTC
    )


async def test__tokens__custom_token_mgmt__cached_token(
    db_deps: Deps, oauth_token: OAuthToken
) -> None:
    current_token = "sk-super-curr-token"
    current_expires_at = datetime.now(UTC) + timedelta(hours=1)

    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
            access_token=current_token,
            access_token_expires_at=current_expires_at,
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    db_deps.auth.refresh_access_token.return_value = oauth_token  # type: ignore[attr-defined]

    token = await tokens.get_access_token(identity=identity.to_data())

    assert current_token == token.access_token
    assert token.expires_at
    assert current_expires_at == token.expires_at.replace(tzinfo=UTC)

    # make sure the token is still the same in DB
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity
    assert current_token == updated_identity.access_token
    assert updated_identity.access_token_expires_at
    assert current_expires_at == updated_identity.access_token_expires_at.replace(
        tzinfo=UTC
    )


async def test__tokens__custom_token_mgmt__expired_token(
    db_deps: Deps, oauth_token: OAuthToken
) -> None:
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
            access_token="sk-super-old-token",
            access_token_expires_at=datetime.now(UTC)
            - timedelta(hours=1),  # past timestamp
            refresh_token="sk-old-refresh-token",
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    db_deps.auth.refresh_access_token.return_value = oauth_token  # type: ignore[attr-defined]

    token = await tokens.get_access_token(identity=identity.to_data())

    assert token.access_token == oauth_token.access_token
    assert token.expires_at == oauth_token.expires_at

    # make sure the token was cached
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity
    assert oauth_token.access_token == updated_identity.access_token
    assert updated_identity.access_token_expires_at
    assert oauth_token.expires_at == updated_identity.access_token_expires_at.replace(
        tzinfo=UTC
    )
    assert oauth_token.refresh_token == updated_identity.refresh_token


async def test__tokens__refresh_failure__marks_needs_reauth(
    db_deps: Deps,
) -> None:
    """
    When token refresh fails with OAuthServiceError, the identity should be marked
    as needs_reauth=True so the UI can prompt the user to reconnect.
    """
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
            access_token="sk-expired-token",
            access_token_expires_at=datetime.now(UTC) - timedelta(hours=1),  # expired
            refresh_token="sk-refresh-token",
            needs_reauth=False,  # Start with False
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    # Mock the refresh to fail with OAuthServiceError (e.g., token revoked by user)
    db_deps.auth.refresh_access_token.side_effect = OAuthServiceError(  # type: ignore[attr-defined]
        message="Token has been revoked",
        status_code=401,
    )

    # Attempt to get access token - should raise OAuthServiceError
    with pytest.raises(OAuthServiceError):
        await tokens.get_access_token(identity=identity.to_data())

    # Verify the identity is now marked as needs_reauth
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity is not None
    assert updated_identity.needs_reauth is True, (
        "Identity should be marked as needs_reauth=True when token refresh fails"
    )


async def test__tokens__successful_refresh__clears_needs_reauth(
    db_deps: Deps, oauth_token: OAuthToken
) -> None:
    """
    When token refresh succeeds, any previously set needs_reauth flag should be
    cleared (set to False).
    """
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
            access_token="sk-expired-token",
            access_token_expires_at=datetime.now(UTC) - timedelta(hours=1),  # expired
            refresh_token="sk-refresh-token",
            needs_reauth=True,  # Start with True (simulating previous failure)
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    # Mock successful refresh
    db_deps.auth.refresh_access_token.return_value = oauth_token  # type: ignore[attr-defined]

    # Get access token - should succeed and refresh
    token = await tokens.get_access_token(identity=identity.to_data())

    assert token.access_token == oauth_token.access_token

    # Verify the identity now has needs_reauth=False
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity is not None
    assert updated_identity.needs_reauth is False, (
        "Identity should have needs_reauth=False after successful token refresh"
    )


async def test__tokens__valid_token__does_not_change_needs_reauth(
    db_deps: Deps, oauth_token: OAuthToken
) -> None:
    """
    When the cached token is still valid (not expired), the needs_reauth flag
    should not be modified.
    """
    identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id="1",
            provider_id="google",
            provider_type="google",
            provider_user_id="test-ext-user-id",
            access_token="sk-valid-token",
            access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),  # valid
            refresh_token="sk-refresh-token",
            needs_reauth=True,  # This shouldn't change since no refresh happens
        )
    )

    tokens = Tokens(
        oauth=db_deps.auth,
        identity_repo=db_deps.identity_repo,
    )

    # Get access token - should return cached token without refresh
    token = await tokens.get_access_token(identity=identity.to_data())

    assert token.access_token == "sk-valid-token"

    # Verify the needs_reauth flag was not modified (no refresh occurred)
    updated_identity = await db_deps.identity_repo.get_identity_by_id(identity.id)

    assert updated_identity is not None
    # Note: The flag stays True because no refresh was performed
    # In practice, this state would only occur if needs_reauth was set but
    # the access token was then restored via a different path
    assert updated_identity.needs_reauth is True
