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
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse

from datarobot.auth.oauth import AsyncOAuthComponent

from app.auth.api_key import APIKeyValidator
from app.auth.oauth import get_oauth
from app.config import Config
from app.db import DBCtx, create_db_ctx
from app.files import FileRepository
from app.knowledge_bases import KnowledgeBaseRepository
from app.models.chats import ChatRepository
from app.models.messages import MessageRepository
from app.users.identity import IdentityRepository
from app.users.tokens import Tokens
from app.users.user import UserRepository

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    config: Config
    db: DBCtx
    user_repo: UserRepository
    identity_repo: IdentityRepository
    knowledge_base_repo: KnowledgeBaseRepository
    file_repo: FileRepository
    chat_repo: ChatRepository
    message_repo: MessageRepository
    api_key_validator: APIKeyValidator
    auth: AsyncOAuthComponent
    tokens: Tokens
    upload_path: Path


def sqlite_uri_to_path(uri: str) -> Path | None:
    """
    Convert a SQLite URI to a file path.
    This is used to ensure the directory exists for SQLite database files.
    If the URI is not a valid Path like `:memory:` or a sqlite URI, it returns None.
    """
    parsed = urlparse(uri)
    if not parsed.scheme.startswith("sqlite"):
        return None

    # Remove leading slashes to get the file path
    db_path_str = parsed.path.replace("/", "", 1)

    if db_path_str == ":memory:":
        return None

    return Path(db_path_str)


@asynccontextmanager
async def create_deps(
    config: Config, deps: Deps | None = None
) -> AsyncGenerator[Deps, None]:
    """
    Create a dependency context for the application (with both startup and shutdown routines).
    Dependencies are basically singletons that are shared on the application server level.
    """
    if deps:
        # this is used for testing when dependencies are given for us
        yield deps
        return

    # startup routine

    # Ensure the directory exists for SQLite database files
    db_path = sqlite_uri_to_path(config.database_uri)
    if db_path:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    db = await create_db_ctx(config.database_uri)

    api_key_validator = APIKeyValidator(datarobot_endpoint=config.datarobot_endpoint)

    # Make upload folder
    upload_path = Path(config.storage_path) / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)

    if config.test_user_api_key:
        logger.warning(
            "Test User API key is set, so the application will assume the mocked user. "
            "This must be enabled during local development only."
        )

    if config.test_user_email:
        logger.warning(
            "Test User email is set, so the application will assume the mocked user. "
            "This must be enabled during local development only."
        )

    oauth = get_oauth(config)

    identity_repo = IdentityRepository(db)

    yield Deps(
        config=config,
        db=db,
        user_repo=UserRepository(db),
        identity_repo=identity_repo,
        knowledge_base_repo=KnowledgeBaseRepository(db),
        file_repo=FileRepository(db),
        chat_repo=ChatRepository(db),
        message_repo=MessageRepository(db),
        api_key_validator=api_key_validator,
        auth=oauth,
        tokens=Tokens(oauth, identity_repo),
        upload_path=upload_path,
    )

    # shutdown routine
    await db.shutdown()
    await oauth.close()
