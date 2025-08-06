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
from typing import TYPE_CHECKING, Awaitable, Callable, Final

from datarobot.auth.oauth import OAuthToken, Profile
from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.v1.schema import ErrorCodes, ErrorSchema
from app.auth.api_key import APIKeyValidator
from app.users.identity import AuthSchema, IdentityUpdate, ProviderType
from app.users.tokens import Tokens
from app.users.user import UserCreate

if TYPE_CHECKING:
    from app import Config


AUTH_SESS_KEY: Final[str] = "auth"


class DRAppCtx(BaseModel):
    email: str | None = None
    api_key: str | None = None


def get_datarobot_ctx(request: Request) -> DRAppCtx:
    """
    Returns the scoped DataRobot API key or external (non-DataRobot) user email from the request headers propagated by DataRobot
    """
    config: Config = request.app.state.deps.config

    scoped_api_key = request.headers.get(
        "X-DATAROBOT-API-KEY", config.test_user_api_key
    )
    ext_email = request.headers.get("X-USER-EMAIL", config.test_user_email)

    return DRAppCtx(api_key=scoped_api_key, email=ext_email)


async def get_auth_ctx(
    request: Request, dr_ctx: DRAppCtx = Depends(get_datarobot_ctx)
) -> AuthCtx[Metadata] | None:
    """
    Loads the auth context from the session if it exists.
    TODO: there may be a room for consolidation of this logic with the logic we have in the callback handler:
        web/app/api/v1/auth.py:143
    """
    if auth_sess := request.session.get(AUTH_SESS_KEY, {}):
        # let's just use the existing in-app session
        return AuthCtx[Metadata](**auth_sess)

    # no active app user session found, must be the first application visit
    api_key_validator: APIKeyValidator = request.app.state.deps.api_key_validator
    user_repo = request.app.state.deps.user_repo
    identity_repo = request.app.state.deps.identity_repo

    provider_type: ProviderType
    user_profile: Profile
    provider_user_id: str

    if dr_ctx.api_key:
        dr_user = await api_key_validator.validate(dr_ctx.api_key)

        if not dr_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorSchema(
                    code=ErrorCodes.DATAROBOT_USER_ERROR,
                    message="Could not validate DataRobot User API key.",
                ).model_dump(),
            )

        provider_type = ProviderType.DATAROBOT_USER
        provider_user_id = dr_user.id
        user_profile = dr_user.to_profile()
    elif dr_ctx.email:
        provider_type = ProviderType.EXTERNAL_EMAIL
        provider_user_id = dr_ctx.email
        user_profile = Profile(
            # We don't have much information about external users
            id=dr_ctx.email,
            email=dr_ctx.email,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorSchema(
                code=ErrorCodes.NOT_AUTHED,
                message="DataRobot authentication must be provided.",
            ).model_dump(),
        )

    identity = await identity_repo.get_by_external_user_id(
        auth_type=AuthSchema.DATAROBOT,
        provider_type=provider_type.value,
        provider_user_id=provider_user_id,
    )

    if not identity:
        user = await user_repo.get_user(email=user_profile.email)

        if not user:
            try:
                user = await user_repo.create_user(
                    UserCreate(
                        email=user_profile.email,
                        first_name=user_profile.given_name,
                        last_name=user_profile.family_name,
                        profile_image_url=user_profile.photo_url,
                    ),
                )
            except IntegrityError:
                # Race condition: user was created between our check and create attempt
                # Try to get the existing user
                user = await user_repo.get_user(email=user_profile.email)
                if not user:
                    # If we still can't find the user, re-raise the original error
                    raise

        profile_metadata = user_profile.metadata or {}

        identity = await identity_repo.upsert_identity(
            user_id=user.id,
            auth_type=AuthSchema.DATAROBOT,
            provider_id=provider_type,  # DataRobot auth schemas are global, so no specific provider ID exists
            provider_type=provider_type,
            provider_user_id=user_profile.id,
            update=IdentityUpdate(
                datarobot_org_id=profile_metadata.get("org_id"),
                datarobot_tenant_id=profile_metadata.get("tenant_id"),
            ),
        )

    # reload the user account data
    user = await user_repo.get_user(user_id=identity.user_id)
    auth_ctx: AuthCtx[Metadata] = user.to_auth_ctx()

    request.session[AUTH_SESS_KEY] = auth_ctx.model_dump()

    return auth_ctx


def must_get_auth_ctx(
    auth_ctx: AuthCtx[Metadata] = Depends(get_auth_ctx),
) -> AuthCtx[Metadata]:
    """
    Loads the auth context from the session if it exists.
    """
    if not auth_ctx:
        err = ErrorSchema(
            code=ErrorCodes.NOT_AUTHED,
            message="You are not authenticated to access this resource.",
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=err.model_dump()
        )

    return auth_ctx


def get_access_token(
    provider_id: ProviderType,
) -> Callable[[Request, AuthCtx[Metadata]], Awaitable[OAuthToken]]:
    async def _get_access_token(
        request: Request, auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
    ) -> OAuthToken:
        oauth_tokens: Tokens = request.app.state.deps.tokens

        identity = next(
            (
                identity
                for identity in auth_ctx.identities
                if identity.provider_type == provider_id.value
            )
        )

        if not identity:
            err = ErrorSchema(
                code=ErrorCodes.NOT_AUTHORIZED,
                message=f"Application not authorized to use {provider_id}",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=err.model_dump()
            )

        return await oauth_tokens.get_access_token(identity)

    return _get_access_token
