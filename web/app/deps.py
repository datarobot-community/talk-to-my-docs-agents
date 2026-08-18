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
from app.chats import ChatRepository
from app.config import Config
from app.db import DBCtx, create_db_ctx
from app.files import FileRepository
from app.knowledge_bases import KnowledgeBaseRepository
from app.knowledge_bases.memory_api_vdb import ConversationMemory, MemoryApiVectorStore
from app.messages import MessageRepository
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
    vector_store: MemoryApiVectorStore | None = None
    conversation_memory: ConversationMemory | None = None


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

    # Semantic retrieval and agent memory both run on DataRobot's managed Memory
    # API (mem0-compatible). Both need a configured memory space + endpoint; when
    # unconfigured, they stay off and the app uses the legacy keyword path.
    vector_store: MemoryApiVectorStore | None = None
    conversation_memory: ConversationMemory | None = None
    space_id = config.memory_space_id
    if space_id and config.datarobot_endpoint:
        root = config.datarobot_endpoint.rstrip("/")
        root = root[:-7] if root.endswith("/api/v2") else root
        base_url = f"{root}/api-gw/agentic-memory-api"
        if config.vdb_enabled:
            logger.info("Semantic retrieval (DataRobot Memory API) is ENABLED.")
            vector_store = MemoryApiVectorStore(
                base_url=base_url,
                space_id=space_id,
                token=config.datarobot_api_token,
                chunk_chars=config.vdb_chunk_chars,
                overlap=config.vdb_chunk_overlap_chars,
                top_k=config.memory_top_k,
                user_prefix=config.memory_user_prefix,
                index_concurrency=config.vdb_index_concurrency,
                add_batch_size=config.vdb_add_batch_size,
            )
        if config.chat_memory_enabled:
            logger.info("Agent conversation memory (DataRobot Memory API) is ENABLED.")
            conversation_memory = ConversationMemory(
                base_url=base_url,
                space_id=space_id,
                token=config.datarobot_api_token,
                top_k=config.chat_memory_top_k,
            )
    elif config.vdb_enabled or config.chat_memory_enabled:
        logger.warning(
            "VDB_ENABLED/CHAT_MEMORY_ENABLED set but MEMORY_SPACE_ID or "
            "DATAROBOT_ENDPOINT is missing; Memory API features stay OFF "
            "(falling back to keyword/full-content)."
        )

    if config.test_user_api_key:
        logger.error(
            "Test User API key is set, so the application will assume the mocked user. "
            "This must be enabled during local development only."
        )

    if config.test_user_email:
        logger.error(
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
        vector_store=vector_store,
        conversation_memory=conversation_memory,
    )

    # shutdown routine
    await db.shutdown()
    await oauth.close()
    if vector_store is not None:
        await vector_store.dispose()
    if conversation_memory is not None:
        await conversation_memory.dispose()
