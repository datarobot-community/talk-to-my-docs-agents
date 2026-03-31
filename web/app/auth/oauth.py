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
import logging
from enum import Enum
from typing import TYPE_CHECKING

from datarobot.auth.authlib.oauth import AsyncOAuth as AuthlibOAuth
from datarobot.auth.authlib.oauth import OAuthProviderConfig
from datarobot.auth.datarobot.oauth import AsyncOAuth as DatarobotOAuth
from datarobot.auth.oauth import AsyncOAuthComponent

from app.users.auth import box_user_info_mapper, sharepoint_user_info_mapper
from app.users.identity import ProviderType

if TYPE_CHECKING:
    from app import Config

logger = logging.getLogger(__name__)


class OAuthImpl(str, Enum):
    """
    OAuth implementations supported by the application template.
    """

    AUTHLIB = "authlib"
    DATAROBOT = "datarobot"

    @classmethod
    def all(cls) -> list[str]:
        """
        Returns a list of all available OAuth implementations.
        """
        return [impl.value for impl in OAuthImpl]


def get_oauth(config: "Config") -> AsyncOAuthComponent:
    if config.oauth_impl == OAuthImpl.DATAROBOT:
        if not config.datarobot_oauth_providers:
            logger.warning(
                "No OAuth providers configured for the DataRobot implementation. "
                "Use the `DATAROBOT_OAUTH_PROVIDERS` environment variable to set them up."
            )

        return DatarobotOAuth(
            config.datarobot_oauth_providers,
            datarobot_endpoint=config.datarobot_endpoint,
            datarobot_api_token=config.datarobot_api_token,
        )

    if config.oauth_impl == OAuthImpl.AUTHLIB:
        provider_configs: list[OAuthProviderConfig] = []

        if config.google_client_id and config.google_client_secret:
            provider_configs.append(
                OAuthProviderConfig(
                    id=ProviderType.GOOGLE.value,
                    client_id=config.google_client_id,
                    client_secret=config.google_client_secret,
                    scope="openid email profile https://www.googleapis.com/auth/drive.readonly",
                    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                    authorize_params={
                        "access_type": "offline",
                        "prompt": "consent",  # TODO: can we remove the prompt param here?
                    },
                )
            )

        if config.box_client_id and config.box_client_secret:
            provider_configs.append(
                OAuthProviderConfig(
                    id=ProviderType.BOX.value,
                    client_id=config.box_client_id,
                    client_secret=config.box_client_secret,
                    scope="root_readwrite",
                    authorize_url="https://account.box.com/api/oauth2/authorize",
                    access_token_url="https://api.box.com/oauth2/token",
                    userinfo_endpoint="https://api.box.com/2.0/users/me",
                    userinfo_mapper=box_user_info_mapper,
                )
            )

        if (
            config.sharepoint_client_id
            and config.sharepoint_client_secret
            and config.sharepoint_tenant_id
        ):
            # Microsoft Entra ID (Azure AD) OAuth for SharePoint delegated access
            # Uses OpenID Connect discovery for automatic endpoint configuration
            provider_configs.append(
                OAuthProviderConfig(
                    id=ProviderType.SHAREPOINT.value,
                    client_id=config.sharepoint_client_id,
                    client_secret=config.sharepoint_client_secret,
                    # Request delegated permissions for SharePoint access
                    # Sites.Read.All - read access to all SharePoint sites user has access to
                    # User.Read - read user's profile for identity
                    # offline_access - get refresh tokens for long-lived sessions
                    scope="openid email profile Sites.Read.All User.Read offline_access",
                    server_metadata_url=f"https://login.microsoftonline.com/{config.sharepoint_tenant_id}/v2.0/.well-known/openid-configuration",
                    userinfo_endpoint="https://graph.microsoft.com/v1.0/me",
                    userinfo_mapper=sharepoint_user_info_mapper,
                    authorize_params={
                        "prompt": "consent",
                    },
                )
            )

        if not provider_configs:
            logger.warning(
                "No OAuth providers configured for the authlib implementation. "
                "Use the `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BOX_CLIENT_ID`, `BOX_CLIENT_SECRET`, "
                "`SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`, and `SHAREPOINT_TENANT_ID` "
                "environment variables to set them up."
            )

        return AuthlibOAuth(provider_configs)

    raise ValueError(
        f"Unsupported OAuth implementation: {config.oauth_impl}. "
        f"Available implementations: {', '.join(OAuthImpl.all())}."
    )
