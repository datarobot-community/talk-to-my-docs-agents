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
import asyncio
import json
import logging
import re
import uuid as uuidpkg
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Coroutine, List, Tuple

import datarobot as dr
import litellm
from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from datarobot.core import getenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import NoResultFound

from app.api.v1.knowledge_bases import (
    get_knowledge_base_schema,
)
from app.auth.ctx import must_get_auth_ctx
from app.chats import Chat, ChatCreate, ChatRepository
from app.config import Config
from app.files.contents import get_or_create_encoded_content
from app.messages import Message, MessageCreate, MessageRepository, MessageUpdate, Role
from app.streams import (
    ChatStreamManager,
    MessageEvent,
    SnapshotEvent,
    StreamEvent,
    encode_sse_event,
)

if TYPE_CHECKING:
    from app.files.models import File, FileRepository
    from app.knowledge_bases import KnowledgeBase, KnowledgeBaseRepository
    from app.users.user import User, UserRepository

logger = logging.getLogger(__name__)
chat_router = APIRouter(tags=["Chat"])

agent_deployment_url = getenv("AGENT_DEPLOYMENT_URL") or ""
agent_deployment_token = getenv("AGENT_DEPLOYMENT_TOKEN") or "dummy"
AGENT_MODEL_NAME = "ttmdocs-agents"


SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the provided document(s) to answer "
    "as accurately as possible. If the answer is not contained in the documents, "
    "say you don't know. When documents have page numbers, you can reference "
    "specific pages and their filenames in your answer."
)

SUGGESTIONS_PROMPT = (
    "You are a helpful assistant that generates relevant questions about the provided documents. "
    "Based on the content and context of the documents, generate 3-5 thoughtful questions that "
    "users might want to ask. Focus on the key topics, insights, and information contained in the documents. "
    "Return the questions as a unordered markdown list and prefix each question with **SUGGESTION:**. "
    "Example response: "
    "```markdown\n"
    "The following questions may be helpful:"
    "- **SUGGESTION:**What are the main features of this product?\n"
    "- **SUGGESTION:**How does the pricing structure work?\n"
    "- **SUGGESTION:**What are the system requirements?"
)


def _normalize_model_id(raw_model: str) -> str:
    """
    Add datarobot as a provider and handle any other provider string fixes for
    litellm
    """
    # fallback to datarobot provider
    return f"datarobot/{raw_model}"


def _get_component_name(model: str, config: Config) -> str:
    """Determine which component is being used."""
    if model == AGENT_MODEL_NAME:
        return "AI Agent"
    if config.llm_deployment_id:
        return "LLM Blueprint"
    return "LLM Gateway"


def _is_wakeup_error(error_str: str) -> bool:
    """Check if error indicates a service is waking up from idle."""
    patterns = [
        "waiting for workload reach > 0 replicas",
        "Inference server is unavailable",
    ]
    return any(p in error_str for p in patterns)


def _extract_json_message(text: str) -> str | None:
    """Try to extract message/detail from JSON, return None if not JSON or no message."""
    try:
        # Handle escaped quotes from upstream
        unescaped = text.replace(r"\"", '"')
        data = json.loads(unescaped)
        msg = data.get("message") or data.get("detail")
        return str(msg) if msg else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def _clean_error_message(error_str: str) -> str:
    """Strip wrapper noise from error message."""
    msg = error_str

    # Remove litellm exception prefixes and wrappers
    msg = re.sub(r"litellm\.\w+:\s*", "", msg)
    msg = re.sub(
        r"(InternalServerError:\s*)?OpenAIException\s*-\s*(ERROR:\s*)?", "", msg
    )
    msg = re.sub(r"DatarobotException\s*-\s*", "", msg)

    # Try to extract message from JSON
    extracted = _extract_json_message(msg)
    if extracted:
        msg = extracted

    # Strip ERROR: prefix
    msg = re.sub(r"^ERROR:\s*", "", msg)

    # Take first line only (drop tracebacks)
    return msg.split("\n")[0].strip()


def _format_error_message(error: Exception, model: str, config: Config) -> str:
    """Format error with component name and clean up noise."""
    component = _get_component_name(model, config)
    error_str = str(error)

    if _is_wakeup_error(error_str):
        return f"{component} is waking up. Please retry in a few moments."

    return f"{component}: {_clean_error_message(error_str)}"


async def _get_current_user(user_repo: "UserRepository", user_id: int) -> "User":
    current_user = await user_repo.get_user(user_id=user_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")
    return current_user


async def _augment_message_with_files(
    message: str,
    files: "list[File]",
    file_repo: "FileRepository",
    knowledge_base: "KnowledgeBase | None" = None,
    knowledge_base_repo: "KnowledgeBaseRepository | None" = None,
) -> str:
    """Augment the message with file information."""

    file_content = []
    for file in files:
        if not file.file_path:
            logger.warning(f"File {file.filename} has no file_path, skipping.")
            continue
        file_contents = await get_or_create_encoded_content(
            file=file,
            file_repo=file_repo,
            knowledge_base=knowledge_base,
            knowledge_base_repo=knowledge_base_repo,
        )

        if file_contents is None:
            continue
        # Handle paginated content
        pages_text = []
        for page_num, page_content in file_contents.items():
            pages_text.append(f"Page {page_num}:\n{page_content}")

        file_content.append(
            f"File: {file.filename}\ncontents:\n{chr(10).join(pages_text)}\n---\n\n"
        )

    documents_intro = (
        "Here are the relevant documents with each document separated by three dashes, "
        "and each page numbered with 'Page <num>: <content>':"
    )

    return f"{message}\n\n{documents_intro}\n\n" + "\n---\n".join(file_content)


def _format_chat(chat: Chat, message: Message | None) -> dict[str, Any]:
    data: dict[str, Any] = chat.dump_json_compatible()
    if message:
        message_data = message.dump_json_compatible()
        data["updated_at"] = message_data["created_at"]
        data["model"] = message_data["model"]
    else:
        data["updated_at"] = data["created_at"]
        data["model"] = None
    return data


async def _get_or_create_chat_id(
    chat_repo: ChatRepository, chat_id: str | None, current_user: "User"
) -> tuple[uuidpkg.UUID, bool]:
    """
    Get or create a chat ID. Returns tuple of (chat_uuid, was_created).
    """
    # If no chat_id provided, create new chat
    if not chat_id:
        new_chat = await chat_repo.create_chat(
            ChatCreate(name="New Chat", user_uuid=current_user.uuid)
        )
        return new_chat.uuid, True

    # Try to parse the chat_id as UUID
    try:
        uuid_value = uuidpkg.UUID(chat_id)
    except ValueError:
        # Invalid UUID format, create new chat
        new_chat = await chat_repo.create_chat(
            ChatCreate(name="New Chat", user_uuid=current_user.uuid)
        )
        return new_chat.uuid, True

    # Check if chat exists
    try:
        await chat_repo.get_chat(uuid_value)
        return uuid_value, False
    except NoResultFound:
        # Chat doesn't exist, create new chat
        new_chat = await chat_repo.create_chat(
            ChatCreate(name="New Chat", user_uuid=current_user.uuid)
        )
        return new_chat.uuid, True


async def _get_files(
    current_user: "User",
    file_ids_str: list[str],
    file_repo: "FileRepository",
) -> list["File"]:
    if not file_ids_str:
        return []
    # Validate and convert file IDs
    file_ids = []
    for file_id_str in file_ids_str:
        try:
            file_ids.append(uuidpkg.UUID(file_id_str))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail=f"Invalid file_id format: {file_id_str}"
            )

    files = await file_repo.get_files(user=current_user, file_ids=file_ids)
    return files


async def _get_knowledge_base(
    knowledge_base_uuid_str: str | None,
    knowledge_base_repo: "KnowledgeBaseRepository",
    current_user: "User",
) -> "KnowledgeBase | None":
    """Get Knowledge Base by UUID."""
    if not knowledge_base_uuid_str:
        return None
    try:
        knowledge_base_uuid = uuidpkg.UUID(knowledge_base_uuid_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid knowledge_base_id format")

    # Get Knowledge Base files if knowledge base is provided
    knowledge_base_obj: KnowledgeBase | None = None
    if knowledge_base_uuid:
        knowledge_base_obj = await knowledge_base_repo.get_knowledge_base(
            current_user,
            knowledge_base_uuid=knowledge_base_uuid,
        )
        if not knowledge_base_obj:
            raise HTTPException(status_code=400, detail="Knowledge Base not found.")
    return knowledge_base_obj


async def _create_new_message_exchange(
    message_repo: MessageRepository,
    chat_id: uuidpkg.UUID,
    model: str,
    user_message: str,
) -> Tuple[Message, Message]:
    prompt_message = await message_repo.create_message(
        MessageCreate(
            chat_id=chat_id,
            role=Role.USER,
            model=model,
            content=user_message,
            components="",
            error=None,
            in_progress=False,
        )
    )

    response_message = await message_repo.create_message(
        MessageCreate(
            chat_id=chat_id,
            role=Role.ASSISTANT,
            model=model,
            in_progress=True,
            content="",
            components="",
            error=None,
        )
    )

    return prompt_message, response_message


@asynccontextmanager
async def _update_message_on_exception(
    request: Request,
    message_uuid: uuidpkg.UUID,
    stream_manager: ChatStreamManager,
    model: str,
    config: Config,
) -> AsyncIterator[None]:
    """
    Context manager for running a chat completions safely
    - Catches exceptions raised inside the block
    - Logs the error
    - Updates DB or request state if needed
    """
    try:
        yield
    except Exception as e:
        logger.error(f"{type(e).__name__} occurred %s", str(e))
        message_repo: MessageRepository = request.app.state.deps.message_repo
        formatted_error = _format_error_message(e, model, config)
        update_model = MessageUpdate(in_progress=False, error=formatted_error)
        updated_message = await message_repo.update_message(
            uuid=message_uuid,
            update=update_model,
        )
        if updated_message and updated_message.chat_id:
            stream_manager.publish(
                updated_message.chat_id,
                MessageEvent(data=updated_message.dump_json_compatible()),
            )


def _get_safe_completion_task(
    model: str,
    request: Request,
    message_uuid: uuidpkg.UUID,
    stream_manager: ChatStreamManager,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> Callable[[], Coroutine[Any, Any, None]]:
    config: Config = request.app.state.deps.config

    async def task() -> None:
        async with _update_message_on_exception(
            request, message_uuid, stream_manager, model, config
        ):
            if model == AGENT_MODEL_NAME:
                await _send_chat_agent_completion(
                    request, message_uuid, stream_manager, auth_ctx
                )
            else:
                await _send_chat_completion(
                    request, message_uuid, stream_manager, auth_ctx
                )

    return task


async def _send_chat_completion(
    request: Request,
    message_uuid: uuidpkg.UUID,
    stream_manager: ChatStreamManager,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> None:
    # Get current user's UUID
    current_user = await _get_current_user(
        request.app.state.deps.user_repo, int(auth_ctx.user.id)
    )

    request_data = await request.json()
    message = request_data["message"]
    model = request_data["model"]
    file_ids_str = request_data.get("file_ids", [])
    knowledge_base_uuid_str = request_data.get("knowledge_base_id")
    request_type = request_data.get("type", "message")

    # Get repositories
    file_repo: FileRepository = request.app.state.deps.file_repo
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )
    # Get combined files from both sources
    files = await _get_files(
        current_user=current_user,
        file_ids_str=file_ids_str,
        file_repo=file_repo,
    )
    knowledge_base = await _get_knowledge_base(
        knowledge_base_uuid_str=knowledge_base_uuid_str,
        knowledge_base_repo=knowledge_base_repo,
        current_user=current_user,
    )
    knowledge_base_files = knowledge_base.files if knowledge_base is not None else []

    # Combine both sets of files
    combined_files = files + knowledge_base_files

    message_repo: MessageRepository = request.app.state.deps.message_repo

    # Determine system prompt and message based on request type
    system_prompt = (
        SUGGESTIONS_PROMPT if request_type == "suggestion" else SYSTEM_PROMPT
    )
    # Augment the message with file content if they exist
    augmented_message = message
    if combined_files:
        augmented_message = await _augment_message_with_files(
            message,
            files=combined_files,
            file_repo=file_repo,
            knowledge_base=knowledge_base,
            knowledge_base_repo=knowledge_base_repo,
        )

    # Create OpenAI messages
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": augmented_message},
    ]

    config: Config = request.app.state.deps.config
    logger.debug("Sending messages to LLM:\n%s", json.dumps(messages, indent=2))

    if config.llm_deployment_id:
        api_base = (
            f"{config.datarobot_endpoint.rstrip('/')}/deployments/"
            f"{config.llm_deployment_id}/chat/completions"
        )
    else:
        api_base = (
            f"{config.datarobot_endpoint.rstrip('/')}/genai/llmgw/chat/completions"
        )

    completion = await litellm.acompletion(
        messages=messages,
        model=_normalize_model_id(model),
        api_base=api_base,
    )
    # Extract message content from LiteLLM response
    llm_message_content = completion["choices"][0]["message"]["content"] or ""
    update_model = MessageUpdate(content=llm_message_content, in_progress=False)
    updated_message = await message_repo.update_message(
        uuid=message_uuid,
        update=update_model,
    )
    if updated_message and updated_message.chat_id:
        stream_manager.publish(
            updated_message.chat_id,
            MessageEvent(data=updated_message.dump_json_compatible()),
        )
    else:
        logger.warning(
            "Failed to update assistant message %s for stream broadcast", message_uuid
        )


async def _send_chat_agent_completion(
    request: Request,
    message_uuid: uuidpkg.UUID,
    stream_manager: ChatStreamManager,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> None:
    # Get current user's UUID
    current_user = await _get_current_user(
        request.app.state.deps.user_repo, int(auth_ctx.user.id)
    )

    request_data = await request.json()
    message = request_data["message"]
    llm_model = request_data.get("model", AGENT_MODEL_NAME)
    knowledge_base_uuid_str = request_data.get("knowledge_base_id")
    file_ids_str = request_data.get("file_ids", [])
    request_type = request_data.get("type", "message")

    message_repo: MessageRepository = request.app.state.deps.message_repo
    file_repo: FileRepository = request.app.state.deps.file_repo
    knowledge_base_repo: KnowledgeBaseRepository = (
        request.app.state.deps.knowledge_base_repo
    )

    # Get/Validate files and knowledge base schema
    files = await _get_files(
        current_user=current_user, file_ids_str=file_ids_str, file_repo=file_repo
    )
    knowledge_base = await _get_knowledge_base(
        knowledge_base_uuid_str=knowledge_base_uuid_str,
        knowledge_base_repo=knowledge_base_repo,
        current_user=current_user,
    )
    knowledge_base_schema = None
    if knowledge_base:
        try:
            knowledge_base_schema = await get_knowledge_base_schema(
                knowledge_base_uuid=knowledge_base.uuid,
                knowledge_base_repo=knowledge_base_repo,
                current_user=current_user,
                include_content=True,
                file_repo=file_repo,
            )
        except (ValueError, TypeError):
            logger.exception(
                "Failed to get knowledge base schema for validation. "
                "knowledge_base_uuid=%s",
                knowledge_base.uuid,
            )

    # URL/token selection now centralized in build_acompletion_args
    message = message if request_type == "message" else SUGGESTIONS_PROMPT
    augmented_message = message
    if files:
        augmented_message = await _augment_message_with_files(
            message,
            files,
            file_repo=file_repo,
            knowledge_base=knowledge_base,
            knowledge_base_repo=knowledge_base_repo,
        )
    # Create OpenAI formatted for Crew AI
    content: dict[str, Any] = {
        "topic": "documentation",
        "question": f"{augmented_message}",
    }

    # Add knowledge base to content if provided
    if knowledge_base_schema:
        content["knowledge_base"] = knowledge_base_schema.model_dump(mode="json")
        content["topic"] = knowledge_base_schema.description

    # Add file content if files are provided
    if files:
        content["question"] = augmented_message
    messages: list[dict[str, str]] = [
        {"role": "user", "content": json.dumps(content)},
    ]

    config: Config = request.app.state.deps.config

    agent_kwargs: dict[str, Any] = {}
    if agent_deployment_url:
        agent_kwargs["api_base"] = agent_deployment_url.rstrip("/")
        agent_kwargs["api_key"] = agent_deployment_token
        agent_kwargs["model"] = "openai/chat"  # To allow direct chat completion
    else:
        agent_kwargs["api_base"] = (
            f"{config.datarobot_endpoint.rstrip('/')}/deployments/"
            f"{config.agent_retrieval_agent_deployment_id}/chat/completions"
        )
        agent_kwargs["model"] = _normalize_model_id(llm_model)
    logger.debug(
        "Sending messages to Agent Workflow:\n%s", json.dumps(messages, indent=2)
    )

    completion = await litellm.acompletion(messages=messages, **agent_kwargs)
    # Extract message content from LiteLLM response
    llm_message_content = completion["choices"][0]["message"]["content"] or ""

    update_model = MessageUpdate(content=llm_message_content, in_progress=False)
    updated_message = await message_repo.update_message(
        uuid=message_uuid,
        update=update_model,
    )
    if updated_message and updated_message.chat_id:
        stream_manager.publish(
            updated_message.chat_id,
            MessageEvent(data=updated_message.dump_json_compatible()),
        )
    else:
        logger.warning(
            "Failed to update agent message %s for stream broadcast", message_uuid
        )


@chat_router.get("/chat/{chat_uuid}/messages-stream")
async def stream_chat(
    request: Request,
    chat_uuid: uuidpkg.UUID,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> StreamingResponse:
    current_user = await _get_current_user(
        request.app.state.deps.user_repo, int(auth_ctx.user.id)
    )

    chat_repo = request.app.state.deps.chat_repo
    chat = await chat_repo.get_chat(chat_uuid)
    if not chat or chat.user_uuid != current_user.uuid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    message_repo = request.app.state.deps.message_repo
    stream_manager: ChatStreamManager = request.app.state.stream_manager

    logger.debug(
        "SSE stream opened for chat %s by user %s", chat_uuid, current_user.uuid
    )

    async def event_generator() -> AsyncIterator[str]:
        async with stream_manager.subscribe(chat_uuid) as subscriber:
            messages = await message_repo.get_chat_messages(chat_uuid)
            yield encode_sse_event(
                SnapshotEvent(data=[m.dump_json_compatible() for m in messages])
            )

            heartbeat_iter = stream_manager.heartbeat()
            queue_task: asyncio.Task[StreamEvent | None] = asyncio.create_task(
                subscriber.queue.get()
            )
            heartbeat_task: asyncio.Task[StreamEvent] = asyncio.create_task(
                anext(heartbeat_iter)
            )

            try:
                while True:
                    if await request.is_disconnected():
                        logger.debug(
                            "Client disconnected from SSE stream for chat %s",
                            chat_uuid,
                        )
                        break

                    if subscriber.should_disconnect:
                        logger.debug(
                            "Subscriber for chat %s marked for disconnect (queue full)",
                            chat_uuid,
                        )
                        break

                    done, _ = await asyncio.wait(
                        [queue_task, heartbeat_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if queue_task in done:
                        try:
                            queue_event = queue_task.result()
                        except asyncio.CancelledError:
                            break
                        if queue_event is None:
                            logger.debug(
                                "Subscriber for chat %s disconnected due to queue full",
                                chat_uuid,
                            )
                            break
                        yield encode_sse_event(queue_event)
                        queue_task = asyncio.create_task(subscriber.queue.get())

                    if heartbeat_task in done:
                        try:
                            heartbeat_event = heartbeat_task.result()
                        except asyncio.CancelledError:
                            break
                        subscriber.heartbeat_count += 1
                        if subscriber.heartbeat_count >= subscriber.max_heartbeats:
                            break
                        yield encode_sse_event(heartbeat_event)
                        heartbeat_task = asyncio.create_task(anext(heartbeat_iter))
            finally:
                queue_task.cancel()
                heartbeat_task.cancel()
                with suppress(Exception):
                    await heartbeat_iter.aclose()
                with suppress(Exception):
                    await queue_task
                with suppress(Exception):
                    await heartbeat_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@chat_router.get("/chat/llm/catalog")
def get_available_llm_catalog(request: Request) -> Any:
    config: Config = request.app.state.deps.config
    if not config.use_datarobot_llm_gateway:
        return {
            "totalCount": 1,
            "count": 1,
            "next": None,
            "previous": None,
            "data": [
                {
                    "name": config.llm_default_model_friendly_name,
                    "model": config.llm_default_model,
                    "llmId": config.llm_default_model,
                    "isActive": True,
                    "isDeprecated": False,
                }
            ],
        }
    dr_client = dr.Client()
    response = dr_client.get("genai/llmgw/catalog/")
    data = response.json()
    return JSONResponse(content=data)


@chat_router.post("/chat")
async def create_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> Chat:
    """Create a new chat, trigger the chat completion and return the UUID of the new chat"""
    # Get current user's UUID
    current_user = await _get_current_user(
        request.app.state.deps.user_repo, int(auth_ctx.user.id)
    )

    request_data = await request.json()
    message = request_data["message"]
    model = request_data["model"]

    chat_repo = request.app.state.deps.chat_repo
    message_repo = request.app.state.deps.message_repo
    new_chat: Chat = await chat_repo.create_chat(
        ChatCreate(name="New Chat", user_uuid=current_user.uuid)
    )

    stream_manager: ChatStreamManager = request.app.state.stream_manager

    _, response_message = await _create_new_message_exchange(
        message_repo, new_chat.uuid, model, message
    )
    chat_completion_task = _get_safe_completion_task(
        model, request, response_message.uuid, stream_manager, auth_ctx
    )
    background_tasks.add_task(chat_completion_task)

    return new_chat


@chat_router.get("/chat")
async def get_list_of_chats(
    request: Request, auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> Any:
    """Return list of all chats"""
    # Get current user's UUID
    current_user = await _get_current_user(
        request.app.state.deps.user_repo, int(auth_ctx.user.id)
    )

    chat_repo = request.app.state.deps.chat_repo
    message_repo = request.app.state.deps.message_repo

    chats = await chat_repo.get_all_chats(current_user)
    chat_ids = [chat.uuid for chat in chats]
    last_messages = await message_repo.get_last_messages(chat_ids)

    return JSONResponse(
        content=[_format_chat(chat, last_messages.get(chat.uuid)) for chat in chats]
    )


@chat_router.get("/chat/{chat_uuid}")
async def get_chat(request: Request, chat_uuid: uuidpkg.UUID) -> Any:
    """Return info about a specific chat"""
    chat_repo = request.app.state.deps.chat_repo
    message_repo = request.app.state.deps.message_repo

    chat = await chat_repo.get_chat(chat_uuid)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found"
        )

    last_message = await message_repo.get_last_messages([chat.uuid])

    return JSONResponse(content=_format_chat(chat, last_message.get(chat.uuid)))


@chat_router.patch("/chat/{chat_uuid}")
async def update_chat(request: Request, chat_uuid: uuidpkg.UUID) -> Any:
    """Updates chat name.
    Payload:
    name: str name of chat
    """
    chat_repo = request.app.state.deps.chat_repo
    request_data = await request.json()
    new_name = request_data.get("name")
    if not new_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is absent or empty",
        )
    chat = await chat_repo.update_chat_name(chat_uuid, new_name)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found"
        )
    return JSONResponse(content=chat.dump_json_compatible())


@chat_router.delete("/chat/{chat_uuid}")
async def delete_chat(request: Request, chat_uuid: uuidpkg.UUID) -> Any:
    """Deletes a chat."""
    chat_repo = request.app.state.deps.chat_repo
    chat = await chat_repo.delete_chat(chat_uuid)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found"
        )
    return JSONResponse(content=chat.dump_json_compatible())


@chat_router.post("/chat/{chat_uuid}/messages")
async def create_chat_messages(
    request: Request,
    background_tasks: BackgroundTasks,
    chat_uuid: uuidpkg.UUID,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx),
) -> List[Message]:
    """Create a new message in an existing chat, trigger the chat completion and return the 'in progresss' message"""
    request_data = await request.json()
    message = request_data["message"]
    model = request_data["model"]

    chat_repo = request.app.state.deps.chat_repo
    message_repo = request.app.state.deps.message_repo

    # Check if chat exists
    chat = await chat_repo.get_chat(chat_uuid)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    stream_manager: ChatStreamManager = request.app.state.stream_manager

    created_messages = await _create_new_message_exchange(
        message_repo, chat.uuid, model, message
    )
    for msg in created_messages:
        if msg.chat_id:
            stream_manager.publish(
                msg.chat_id,
                MessageEvent(data=msg.dump_json_compatible()),
            )

    prompt_message, response_message = created_messages
    chat_completion_task = _get_safe_completion_task(
        model, request, response_message.uuid, stream_manager, auth_ctx
    )
    background_tasks.add_task(chat_completion_task)

    return [prompt_message, response_message]


@chat_router.get("/chat/{chat_uuid}/messages")
async def get_chat_messages(request: Request, chat_uuid: uuidpkg.UUID) -> Any:
    """Return list of all chats"""
    message_repo = request.app.state.deps.message_repo
    messages = await message_repo.get_chat_messages(chat_uuid)
    return JSONResponse(content=[m.dump_json_compatible() for m in messages])
