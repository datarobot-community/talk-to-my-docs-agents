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
from datarobot.auth.oauth import OAuthData, OAuthFlowSession, OAuthProvider, OAuthToken
from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import Deps, create_app
from app.api.v1.auth import (
    IdentitySchema,
    OAuthProviderListSchema,
    OAuthRedirectSchema,
    UserSchema,
)
from app.auth.api_key import DRUser, validate_dr_api_key
from app.auth.ctx import get_auth_ctx, must_get_auth_ctx
from app.auth.session import get_oauth_sess_key
from app.users.identity import AuthSchema
from app.users.identity import Identity as AppIdentity
from app.users.user import User as AppUser
from app.users.user import UserCreate
from tests.conftest import dep
from tests.session import sess_client


def test__auth__list_providers(
    deps: Deps,
    client: TestClient,
    oauth_provider: OAuthProvider,
) -> None:
    deps.auth.get_providers.return_value = [oauth_provider]  # type: ignore[attr-defined]

    resp = client.get("/api/v1/oauth/")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, dict)

    actual_providers = OAuthProviderListSchema(**data).providers
    assert len(actual_providers) == 1
    actual_provider = actual_providers[0]

    assert actual_provider.id == oauth_provider.id
    assert actual_provider.type == oauth_provider.type
    assert actual_provider.name == oauth_provider.name


def test__auth__get_auth_url(
    deps: Deps,
    client: TestClient,
    oauth_sess: OAuthFlowSession,
) -> None:
    provider_id = "google"
    expected_redirect_url = "https://auth.test.com/authorize"

    oauth_sess.provider_id = provider_id
    oauth_sess.authorization_url = expected_redirect_url

    deps.auth.get_authorization_url.return_value = oauth_sess  # type: ignore[attr-defined]

    resp = client.post("/api/v1/oauth/authorize/", params={"provider_id": provider_id})
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, dict)

    oauth_data = OAuthRedirectSchema(**data)
    assert oauth_data.redirect_url == expected_redirect_url


async def test__auth__oauth_callback__no_state(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
    dr_oauth_data: OAuthData,
    auth_ctx: AuthCtx[Metadata],
) -> None:
    deps.auth.exchange_code.return_value = dr_oauth_data  # type: ignore[attr-defined]
    webapp.dependency_overrides[get_auth_ctx] = dep(auth_ctx)

    resp = client.post(
        "/api/v1/oauth/callback/",
        params={
            "code": "test-one-time-code",
            "state": "secret-oauth-state",
        },
    )
    assert resp.status_code == 400, resp.text


async def test__auth__oauth_callback__invalid_params(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
    dr_oauth_data: OAuthData,
    auth_ctx: AuthCtx[Metadata],
) -> None:
    deps.auth.exchange_code.return_value = dr_oauth_data  # type: ignore[attr-defined]
    webapp.dependency_overrides[get_auth_ctx] = dep(auth_ctx)

    resp = client.post("/api/v1/oauth/callback/", params={})  # no params
    assert resp.status_code == 400, resp.text


async def test__auth__oauth_callback__oauth_err(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
    dr_oauth_data: OAuthData,
    auth_ctx: AuthCtx[Metadata],
) -> None:
    deps.auth.exchange_code.return_value = dr_oauth_data  # type: ignore[attr-defined]
    webapp.dependency_overrides[get_auth_ctx] = dep(auth_ctx)

    resp = client.post(
        "/api/v1/oauth/callback/",
        params={
            "error": "The authorization was cancelled by the user",
        },
    )
    assert resp.status_code == 400, resp.text


async def test__auth__oauth_callback__with_user_session(
    db_deps: Deps,
    dr_oauth_data: OAuthData,
    auth_ctx: AuthCtx[Metadata],
    oauth_sess: OAuthFlowSession,
) -> None:
    db_deps.auth.exchange_code.return_value = dr_oauth_data  # type: ignore[attr-defined]

    webapp = create_app(config=db_deps.config, deps=db_deps)
    webapp.dependency_overrides[get_auth_ctx] = dep(auth_ctx)

    app_user = await db_deps.user_repo.create_user(
        UserCreate(
            email=auth_ctx.user.email,
            first_name=auth_ctx.user.family_name,
            last_name=auth_ctx.user.given_name,
        )
    )
    auth_ctx.user.id = str(app_user.id)

    with TestClient(webapp) as client:
        set_sess, _ = sess_client(client)
        set_sess({get_oauth_sess_key(oauth_sess.state): oauth_sess.model_dump()})

        resp = client.post(
            "/api/v1/oauth/callback/",
            params={
                "code": "test-one-time-code",
                "state": oauth_sess.state,
            },
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert isinstance(data, dict)

        user_data = UserSchema(**data)

        assert user_data.uuid == app_user.uuid
        assert len(user_data.identities) == 1

        identity: IdentitySchema = user_data.identities[0]

        assert dr_oauth_data.user_profile

        assert identity.type == AuthSchema.OAUTH2
        assert identity.provider_id == dr_oauth_data.provider.id
        assert identity.provider_type == dr_oauth_data.provider.type
        assert identity.provider_user_id == dr_oauth_data.user_profile.id


async def test__auth__oauth_callback__no_user_session(
    db_deps: Deps,
    dr_oauth_data: OAuthData,
    auth_ctx: AuthCtx[Metadata],
    oauth_sess: OAuthFlowSession,
) -> None:
    db_deps.auth.exchange_code.return_value = dr_oauth_data  # type: ignore[attr-defined]

    webapp = create_app(config=db_deps.config, deps=db_deps)
    webapp.dependency_overrides[get_auth_ctx] = dep(None)

    with TestClient(webapp) as client:
        set_sess, _ = sess_client(client)
        set_sess({get_oauth_sess_key(oauth_sess.state): oauth_sess.model_dump()})

        resp = client.post(
            "/api/v1/oauth/callback/",
            params={
                "code": "test-one-time-code",
                "state": oauth_sess.state,
            },
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert isinstance(data, dict)

        user_data = UserSchema(**data)

        assert user_data.uuid
        assert len(user_data.identities) == 1

        identity: IdentitySchema = user_data.identities[0]

        assert dr_oauth_data.user_profile

        assert identity.type == AuthSchema.OAUTH2
        assert identity.provider_user_id == dr_oauth_data.user_profile.id


def test__auth__get_user(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
    auth_ctx: AuthCtx[Metadata],
    app_user: AppUser,
) -> None:
    deps.user_repo.get_user.return_value = app_user  # type: ignore[attr-defined]
    webapp.dependency_overrides[must_get_auth_ctx] = dep(auth_ctx)

    resp = client.get("/api/v1/user/")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, dict)

    user_data = UserSchema(**data)

    assert user_data.uuid == app_user.uuid
    assert user_data.first_name == app_user.first_name
    assert user_data.last_name == app_user.last_name


def test__auth__get_token(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
    app_identity: AppIdentity,
    oauth_token: OAuthToken,
) -> None:
    dr_user = DRUser(
        id=app_identity.provider_user_id,
        email="michael.scott@datarobot.com",
        org_id="test-org-id",
    )

    deps.identity_repo.get_identity_by_id.return_value = app_identity  # type: ignore[attr-defined]
    deps.tokens.get_access_token.return_value = oauth_token  # type: ignore[attr-defined]
    webapp.dependency_overrides[validate_dr_api_key] = dep(dr_user)

    resp = client.post("/api/v1/oauth/token/", json={"identity_id": "1"})
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, dict)

    token_data = OAuthToken(**data)

    assert token_data.access_token == oauth_token.access_token


def test__auth__get_token__invalid_key(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
) -> None:
    invalid_token = "hey-im-a-bad-token"
    deps.api_key_validator.validate.return_value = None  # type: ignore[attr-defined]

    resp = client.post(
        "/api/v1/oauth/token/",
        headers={"Authorization": f"Bearer {invalid_token}"},
        json={"identity_id": "1"},
    )

    assert resp.status_code == 401, resp.text


def test__auth__get_token__missing_key(
    deps: Deps,
    webapp: FastAPI,
    client: TestClient,
) -> None:
    deps.api_key_validator.validate.return_value = None  # type: ignore[attr-defined]

    resp = client.post("/api/v1/oauth/token/", json={"identity_id": "1"})

    assert resp.status_code == 403, resp.text


def test__auth__logout(
    deps: Deps,
    client: TestClient,
) -> None:
    resp = client.post("/api/v1/logout/")
    assert resp.status_code == 204
