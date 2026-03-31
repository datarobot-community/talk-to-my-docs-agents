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
from typing import Any

from datarobot.auth.oauth import Profile


def sharepoint_user_info_mapper(raw_data: dict[str, Any]) -> Profile:
    """
    Microsoft Graph User Info to OpenID Connect Profile Mapper.
    Maps the user info response from Microsoft Graph API to the OpenID Connect Profile format.

    Microsoft Graph /me endpoint returns:
    - id: The unique identifier for the user
    - displayName: The user's full display name
    - givenName: The user's first name
    - surname: The user's last name
    - mail or userPrincipalName: The user's email address
    - jobTitle: The user's job title
    - preferredLanguage: The user's preferred language
    """
    user_id = raw_data.get("id")
    email = raw_data.get("mail") or raw_data.get("userPrincipalName")
    display_name = raw_data.get("displayName")
    first_name = raw_data.get("givenName")
    last_name = raw_data.get("surname")
    language = raw_data.get("preferredLanguage")

    if not user_id:
        raise ValueError("User ID is missing in the Microsoft Graph user info response")

    if not email:
        raise ValueError("Email is missing in the Microsoft Graph user info response")

    return Profile(
        id=user_id,
        email=email,
        name=display_name,
        first_name=first_name,
        last_name=last_name,
        locale=language,
        metadata=raw_data,
    )


def box_user_info_mapper(raw_data: dict[str, Any]) -> Profile:
    """
    Box User Info to OpenID Connect Profile Mapper.
    This function maps the raw user info data from custom Box format to the OpenID Connect Profile format.
    """
    full_name = raw_data.get("name")
    first_name: str | None = None
    last_name: str | None = None

    if full_name:
        name_parts = full_name.split(" ")

        first_name = name_parts[0]

        if len(name_parts) > 1:
            last_name = " ".join(name_parts[1:])

    user_id = raw_data.get("id")
    email = raw_data.get("login")
    phone_number = raw_data.get("phone")
    profile_url = raw_data.get("avatar_url")
    language = raw_data.get("language")

    if not user_id:
        raise ValueError("User ID is missing in the user info response")

    if not email:
        raise ValueError("Email is missing in the user info response")

    return Profile(
        id=user_id,
        email=email,
        name=full_name,
        first_name=first_name,
        last_name=last_name,
        locale=language,
        picture=profile_url,
        phone_number=phone_number,
        metadata=raw_data,
    )
