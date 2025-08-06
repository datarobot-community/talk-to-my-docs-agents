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
