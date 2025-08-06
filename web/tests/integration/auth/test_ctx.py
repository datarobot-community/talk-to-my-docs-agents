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
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from fastapi.exceptions import HTTPException

from app import Deps
from app.auth.api_key import DRUser
from app.auth.ctx import DRAppCtx, get_auth_ctx, get_datarobot_ctx
from app.users.identity import AuthSchema, IdentityCreate, ProviderType
from app.users.user import UserCreate


async def test__get_auth_ctx__new_visit__dr_user(
    db_deps: Deps, dr_user: DRUser
) -> None:
    req = AsyncMock(spec=Request)
    req.session = {}
    req.app.state.deps = db_deps

    db_deps.api_key_validator.validate.return_value = dr_user  # type: ignore[attr-defined]

    dr_ctx = DRAppCtx(api_key="test-scoped-api-key")

    auth_ctx = await get_auth_ctx(req, dr_ctx)

    assert auth_ctx
    assert auth_ctx.user.given_name == dr_user.first_name
    assert auth_ctx.user.family_name == dr_user.last_name
    assert auth_ctx.user.email == dr_user.email

    identity = await db_deps.identity_repo.get_by_user_id(
        ProviderType.DATAROBOT_USER, int(auth_ctx.user.id)
    )

    assert identity
    assert identity.type == AuthSchema.DATAROBOT
    assert identity.provider_type == ProviderType.DATAROBOT_USER
    assert identity.provider_user_id == dr_user.id


async def test__get_auth_ctx__new_visit__ext_email(db_deps: Deps) -> None:
    req = AsyncMock(spec=Request)
    req.session = {}
    req.app.state.deps = db_deps

    email = "test@example.com"
    dr_ctx = DRAppCtx(email=email)

    auth_ctx = await get_auth_ctx(req, dr_ctx)

    assert auth_ctx
    assert auth_ctx.user.email == email

    identity = await db_deps.identity_repo.get_by_user_id(
        ProviderType.EXTERNAL_EMAIL, int(auth_ctx.user.id)
    )

    assert identity
    assert identity.type == AuthSchema.DATAROBOT
    assert identity.provider_type == ProviderType.EXTERNAL_EMAIL
    assert identity.provider_user_id == email


async def test__get_auth_ctx__existing_user__new_identity(
    db_deps: Deps, dr_user: DRUser
) -> None:
    req = AsyncMock(spec=Request)
    req.app.state.deps = db_deps
    req.session = {}

    app_user = await db_deps.user_repo.create_user(UserCreate(email=dr_user.email))
    assert app_user

    dr_user_identity = await db_deps.identity_repo.create_identity(
        IdentityCreate(
            user_id=app_user.id,
            type=AuthSchema.DATAROBOT,
            provider_id=ProviderType.DATAROBOT_USER,
            provider_type=ProviderType.DATAROBOT_USER,
            provider_user_id=dr_user.id,
        )
    )
    assert dr_user_identity

    dr_ctx = DRAppCtx(email=dr_user.email)

    auth_ctx = await get_auth_ctx(req, dr_ctx)

    assert auth_ctx
    assert int(auth_ctx.user.id) == app_user.id
    assert auth_ctx.user.email == dr_user.email
    assert {i.provider_type for i in auth_ctx.identities} == {
        ProviderType.DATAROBOT_USER,
        ProviderType.EXTERNAL_EMAIL,
    }

    identity = await db_deps.identity_repo.get_by_user_id(
        ProviderType.EXTERNAL_EMAIL, int(auth_ctx.user.id)
    )

    assert identity
    assert identity.type == AuthSchema.DATAROBOT
    assert identity.provider_type == ProviderType.EXTERNAL_EMAIL
    assert identity.provider_user_id == dr_user.email


async def test__get_auth_ctx__new_visit__empty_dr_ctx(db_deps: Deps) -> None:
    """
    Test the case when neither DataRobot API key nor external email is provided
    (exception case that should not happen to DR deployments, but possible during local dev)
    """
    req = AsyncMock(spec=Request)
    req.session = {}
    req.app.state.deps = db_deps

    with pytest.raises(HTTPException):
        _ = await get_auth_ctx(req, DRAppCtx())


def test__dr_ctx__api_key(db_deps: Deps) -> None:
    req = AsyncMock(spec=Request)
    req.app.state.deps = db_deps
    req.headers = {
        "X-DATAROBOT-API-KEY": "test_api_key",
    }

    auth = get_datarobot_ctx(req)

    assert auth.api_key
    assert not auth.email


def test__dr_ctx__ext_email(db_deps: Deps) -> None:
    req = AsyncMock(spec=Request)
    req.app.state.deps = db_deps
    req.headers = {"X-USER-EMAIL": "test@example.com"}

    auth = get_datarobot_ctx(req)

    assert not auth.api_key
    assert auth.email
