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
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Generator, TypeVar
from unittest.mock import AsyncMock

import pytest
from datarobot.auth.datarobot.oauth import AsyncOAuth
from datarobot.auth.oauth import OAuthFlowSession, OAuthToken
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import create_app
from app.auth.api_key import APIKeyValidator, DRUser
from app.config import Config
from app.db import DBCtx, create_db_ctx
from app.deps import Deps
from app.files import FileRepository
from app.knowledge_bases import KnowledgeBaseRepository
from app.models.chats import ChatRepository
from app.models.messages import MessageRepository
from app.users.identity import AuthSchema, IdentityRepository
from app.users.identity import Identity as AppIdentity
from app.users.tokens import Tokens
from app.users.user import User as AppUser
from app.users.user import UserRepository


@pytest.fixture()
def config() -> Config:
    return Config(
        datarobot_endpoint="https://api.test.datarobot.com",
        datarobot_api_token="test-datarobot-api-key",
        session_secret_key="test-session-secret-key",
        session_https_only=False,
        llm_deployment_id="test-llm-deployment-id",
        database_uri="sqlite+aiosqlite:///:memory:",
        storage_path=".data/test_uploads",
    )


@pytest.fixture
def deps(config: Config) -> Deps:
    """
    Dependency function to provide the necessary dependencies for the FastAPI app.
    Most of the dependencies are mocked to avoid unnecessary complexity in some tests.
    """
    upload_dir = Path(tempfile.mkdtemp())

    return Deps(
        config=config,
        db=AsyncMock(spec=DBCtx),
        identity_repo=AsyncMock(spec=IdentityRepository),
        user_repo=AsyncMock(spec=UserRepository),
        auth=AsyncMock(spec=AsyncOAuth),
        knowledge_base_repo=AsyncMock(spec=KnowledgeBaseRepository),
        file_repo=AsyncMock(spec=FileRepository),
        chat_repo=AsyncMock(spec=ChatRepository),
        message_repo=AsyncMock(spec=MessageRepository),
        api_key_validator=AsyncMock(spec=APIKeyValidator),
        tokens=AsyncMock(spec=Tokens),
        upload_path=upload_dir,
    )


@pytest.fixture
async def db_deps(config: Config) -> Deps:
    """
    Dependency function to provide the necessary dependencies for the FastAPI app with a real database connection.
    This is useful for tests that require actual database interactions.
    """
    tmp_dir = Path(tempfile.mkdtemp())

    config.database_uri = "sqlite+aiosqlite:///:memory:"

    db = await create_db_ctx(config.database_uri)

    return Deps(
        config=config,
        db=db,
        identity_repo=IdentityRepository(db),
        user_repo=UserRepository(db),
        auth=AsyncMock(spec=AsyncOAuth),
        knowledge_base_repo=AsyncMock(spec=KnowledgeBaseRepository),
        file_repo=AsyncMock(spec=FileRepository),
        chat_repo=AsyncMock(spec=ChatRepository),
        message_repo=AsyncMock(spec=MessageRepository),
        api_key_validator=AsyncMock(spec=APIKeyValidator),
        tokens=AsyncMock(spec=Tokens),
        upload_path=tmp_dir,
    )


@pytest.fixture
def webapp(config: Config, deps: Deps) -> FastAPI:
    """
    Create a FastAPI app instance with the provided configuration.
    """
    return create_app(config=config, deps=deps)


@pytest.fixture
def client(webapp: FastAPI) -> Generator[TestClient, None, None]:
    """
    Create a test client for the FastAPI app.

    Note: This client is not authenticated by default. For authenticated endpoints,
    use the `authenticated_client` fixture instead.
    """
    with TestClient(webapp) as client:
        yield client


@pytest.fixture
def simple_client(config: Config, deps: Deps) -> TestClient:
    """
    Create a simple test client for the FastAPI app without authentication.

    Use this fixture for testing endpoints that don't require authentication.
    For authenticated endpoints, use the `authenticated_client` fixture instead.
    """
    app = create_app(config=config, deps=deps)
    # Explicitly set the state since lifespan may not work correctly in TestClient
    app.state.deps = deps
    return TestClient(app)


@pytest.fixture
def authenticated_client(
    config: Config, deps: Deps, app_user: AppUser, app_identity: AppIdentity
) -> TestClient:
    """
    Create an authenticated test client with a default user session.

    This client automatically includes:
    - Authentication headers (X-DATAROBOT-API-KEY, X-USER-EMAIL)
    - Mocked user and identity data
    - Properly configured deps for authenticated endpoints

    Use this fixture for testing endpoints that require authentication.
    """
    app = create_app(config=config, deps=deps)
    app.state.deps = deps

    # Create a test client with authentication headers
    client = TestClient(app)

    # Set up authentication headers that will be used by get_datarobot_ctx
    client.headers.update(
        {
            "X-DATAROBOT-API-KEY": "test-api-key",
            "X-USER-EMAIL": app_user.email,
        }
    )

    # Mock the API key validator to return our test user
    from app.auth.api_key import DRUser

    test_dr_user = DRUser(
        id=str(app_user.id),
        org_id="test-org-id",
        tenant_id="test-tenant-id",
        email=app_user.email,
        first_name=app_user.first_name,
        last_name=app_user.last_name,
        lang="en",
        feature_flags={},
    )

    # Configure the mocked API key validator
    deps.api_key_validator.validate = AsyncMock(return_value=test_dr_user)  # type: ignore[method-assign]

    # Mock the user and identity repositories to return our test data
    deps.user_repo.get_user = AsyncMock(return_value=app_user)  # type: ignore[method-assign]
    deps.identity_repo.get_by_external_user_id = AsyncMock(return_value=app_identity)  # type: ignore[method-assign]
    deps.identity_repo.upsert_identity = AsyncMock(return_value=app_identity)  # type: ignore[method-assign]

    return client


@pytest.fixture
def app_user() -> AppUser:
    return AppUser(
        id=1,
        email="test@datarobot.com",
        first_name="Michael",
        last_name="Smith",
    )


@pytest.fixture
def app_identity(app_user: AppUser) -> AppIdentity:
    return AppIdentity(
        id=1,
        type=AuthSchema.OAUTH2,
        user_id=app_user.id or 1,  # Handle potential None value
        provider_id="google",
        provider_type="google",
        provider_user_id="google-user-id",
        provider_identity_id="provider-identity-id",
        access_token="access-token",
        access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_token="refresh-token",
        datarobot_org_id="org-id",
        datarobot_tenant_id="tenant-id",
    )


@pytest.fixture
def oauth_token() -> OAuthToken:
    ttl = 3600  # 1 hour in seconds

    return OAuthToken(
        access_token="sk-access-token",
        token_type="Bearer",
        expires_in=ttl,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
        scope="openid email profile",
        refresh_token="rt-refresh-token",
    )


@pytest.fixture
def oauth_sess() -> OAuthFlowSession:
    return OAuthFlowSession(
        provider_id="google",
        authorization_url="https://auth.test.com/authorize",
        redirect_uri="https://app.test.com/callback",
        state="test-state",
    )


@pytest.fixture
def dr_user() -> DRUser:
    return DRUser(
        id="61092ffc5f851383dd782b30",
        org_id="57e43914d75f160c3bac26f6",
        tenant_id="7a88e3bd-c606-4f16-8c7b-ccde5dd413f1",
        email="angela.martins@example.com",
        first_name="Angela",
        last_name="Martins",
        lang="en",
        feature_flags={
            "ENABLE_FEATURE_ONE": True,
            "ENABLE_FEATURE_TWO": False,
        },
    )


T = TypeVar("T")


def dep(value: T) -> Callable[[Request], Awaitable[T]]:
    """
    A convenient wrapper to turn a mocked value into a FastAPI.Deps() function
    """

    async def mock_deps(request: Request) -> T:
        return value

    return mock_deps


@pytest.fixture(scope="session", autouse=True)
def clear_environment() -> Generator[None, None, None]:
    """Clear all environment variables at the start of the testing session."""
    # Store original environment
    original_env = dict(os.environ)

    # Clear all environment variables
    os.environ.clear()

    yield

    # Restore original environment after all tests complete
    os.environ.clear()
    os.environ.update(original_env)
