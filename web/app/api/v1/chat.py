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
import functools
import json
import logging
import re
import uuid as uuidpkg
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Coroutine, List, Tuple
from urllib.parse import urlparse

import datarobot as dr
import litellm
from core.document_loader import EMBEDDED_DOCUMENTS_PHRASE
from datarobot.auth.session import AuthCtx
from datarobot.auth.typing import Metadata
from datarobot.core import getenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import metrics, propagate, trace
from sqlalchemy.exc import NoResultFound

from app.api.v1.knowledge_bases import (
    get_knowledge_base_schema,
)
from app.auth.ctx import must_get_auth_ctx
from app.chats import Chat, ChatCreate, ChatRepository
from app.config import Config
from app.db import DBCtx
from app.files.contents import get_or_create_encoded_content
from app.knowledge_bases import RetrievalMode, is_semantic_ready
from app.messages import Message, MessageCreate, MessageRepository, MessageUpdate, Role
from app.streams import (
    ChatStreamManager,
    MessageEvent,
    SnapshotEvent,
    StreamEvent,
    TaskProgressEvent,
    encode_sse_event,
)
from app.telemetry.metrics import track_chat_request
from app.telemetry.otel import otel

if TYPE_CHECKING:
    from app.files.models import File, FileRepository
    from app.knowledge_bases import KnowledgeBase, KnowledgeBaseRepository
    from app.users.user import User, UserRepository

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)
chat_router = APIRouter(tags=["Chat"])


@functools.cache
def _token_counter() -> metrics.Counter:
    return otel.get_meter("gen_ai").create_counter(
        "gen_ai.client.token.usage",
        unit="{token}",
        description="Number of tokens used in GenAI API calls",
    )


def _otel_input_messages(messages: list[Any]) -> str:
    """Convert OpenAI message format to OTel gen_ai.input.messages spec format."""
    result = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "unknown")
        parts: list[dict[str, Any]] = []

        content = msg.get("content")
        tool_call_id = msg.get("tool_call_id")

        if tool_call_id:
            parts.append(
                {
                    "type": "tool_call_response",
                    "id": tool_call_id,
                    "result": content
                    if isinstance(content, str)
                    else json.dumps(content, default=str),
                }
            )
        elif isinstance(content, str) and content:
            parts.append({"type": "text", "content": content})
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    parts.append({"type": "text", "content": item.get("text", "")})
                else:
                    parts.append(item)

        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments", {})
            try:
                arguments = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )
            except (json.JSONDecodeError, TypeError):
                arguments = raw_args
            parts.append(
                {
                    "type": "tool_call",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": arguments,
                }
            )

        result.append({"role": role, "parts": parts})
    return json.dumps(result, default=str)


def _otel_output_messages(content: str) -> str:
    """Convert a completion string to OTel gen_ai.output.messages spec format."""
    return json.dumps(
        [{"role": "assistant", "parts": [{"type": "text", "content": content}]}]
    )


def _capture_message_content() -> bool:
    """Whether to record GenAI message *content* on spans.

    Chat prompts/completions can carry user text and recalled personal memories
    (location, preferences), so per the OTel GenAI semantic conventions this
    content is gated behind OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT and
    is off by default. Non-content metadata (model, provider, token counts, ids)
    is always recorded regardless.
    """
    return (
        str(getenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"))
        .strip()
        .lower()
        == "true"
    )


def _set_genai_input_content(span: Any, prompt: str, messages: list[Any]) -> None:
    """Record input prompt/messages on the span only when content capture is on."""
    if _capture_message_content():
        span.set_attribute("gen_ai.prompt", prompt)
        span.set_attribute("gen_ai.input.messages", _otel_input_messages(messages))


def _set_genai_output_content(span: Any, completion: str) -> None:
    """Record output completion/messages on the span only when capture is on."""
    if _capture_message_content():
        span.set_attribute("gen_ai.completion", completion)
        span.set_attribute("gen_ai.output.messages", _otel_output_messages(completion))


DATAROBOT_IDENTITY_HEADER_NAME = "X-DataRobot-Identity-Token"


class TaskProgressProcessor:
    """Extracts task_progress events from streaming response content and accumulates regular content.

    Processes delta.content strings from litellm's streaming response. Each string is
    already complete (httpx-sse's SSELineDecoder handles HTTP-level buffering).
    This class simply:
    1. Checks if content is a task_progress JSON event
    2. Parses and returns it if so
    3. Accumulates regular response content
    """

    def __init__(self) -> None:
        self.content = ""

    def process_content(self, content: str) -> dict[str, Any] | None:
        """Check if content is a task_progress event and return it, else accumulate.

        Args:
            content: Complete string from delta.content (guaranteed complete by httpx-sse)

        Returns:
            Task progress dict if content is a task_progress event, None otherwise
        """
        if content.startswith('{"task_progress'):
            try:
                parsed = json.loads(content)
                if "task_progress" in parsed:
                    result: dict[str, Any] = parsed["task_progress"]
                    return result
                else:
                    logger.warning(
                        "Content starts with task_progress marker but missing key: %s",
                        content,
                    )
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse task_progress JSON: %s - content: %s",
                    e,
                    content,
                )

        # Regular content or unparseable content
        self.content += content
        return None

    def flush(self) -> str:
        """Return accumulated content."""
        return self.content


agent_deployment_url = str(getenv("AGENT_DEPLOYMENT_URL") or "")
agent_deployment_token = str(getenv("AGENT_DEPLOYMENT_TOKEN") or "dummy")
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
    # if the model is already a datarobot prefix, return it as is
    if raw_model.startswith("datarobot/"):
        return raw_model
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
    """Extract message from JSON error response."""
    if not text or not isinstance(text, str):
        return None
    # Find JSON object start and try to parse
    idx = text.find("{")
    if idx == -1:
        return None
    cleaned = text[idx:].rstrip(".")
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            msg = None
            error_obj = data.get("error", {})
            if isinstance(error_obj, dict):
                # Try error.message, error.detail.message
                msg = error_obj.get("message")
                if not msg:
                    detail = error_obj.get("detail")
                    if isinstance(detail, dict):
                        msg = detail.get("message")
            if not msg:
                msg = data.get("message")
            if not msg:
                detail = data.get("detail")
                # Only use detail if it's a string, not array/dict
                if isinstance(detail, str):
                    msg = detail
            return str(msg) if msg else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
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

    # Try to extract message from JSON (one level, then check for nested)
    if extracted := _extract_json_message(msg):
        msg = extracted
        # Check for one more level of nesting
        if extracted2 := _extract_json_message(msg):
            msg = extracted2

    # Strip ERROR: prefix and OS error codes
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[Errno \d+\]\s*", "", msg)

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
        EMBEDDED_DOCUMENTS_PHRASE
        + ", and each page numbered with 'Page <num>: <content>':"
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
            kb_ready = await _kb_is_semantic_ready(request, auth_ctx)
            if _should_use_direct_path(model, kb_ready):
                await _send_chat_completion(
                    request, message_uuid, stream_manager, auth_ctx
                )
            else:
                await _send_chat_agent_completion(
                    request, message_uuid, stream_manager, auth_ctx
                )

    return task


async def _kb_is_semantic_ready(
    request: Request, auth_ctx: "AuthCtx[Metadata]"
) -> bool:
    """True if the request targets a semantic, READY knowledge base.

    Used to route semantic-mode KB chats to the fast grounded path even when the
    agent model is selected. Best-effort: any failure routes normally (False).
    """
    try:
        data = await request.json()
        kb_uuid = data.get("knowledge_base_id")
        if not kb_uuid:
            return False
        deps = request.app.state.deps
        current_user = await _get_current_user(deps.user_repo, int(auth_ctx.user.id))
        kb = await _get_knowledge_base(
            knowledge_base_uuid_str=kb_uuid,
            knowledge_base_repo=deps.knowledge_base_repo,
            current_user=current_user,
        )
        return bool(kb and is_semantic_ready(kb) and deps.vector_store is not None)
    except Exception:
        return False


def get_extra_headers(request: Request) -> dict[str, str]:
    extra_headers: dict[str, str] = {}

    if identity_token := request.headers.get(DATAROBOT_IDENTITY_HEADER_NAME):
        extra_headers[DATAROBOT_IDENTITY_HEADER_NAME] = identity_token

    # Propagate W3C trace context to downstream chat/completions calls.
    propagate.inject(extra_headers)

    return extra_headers


# Upper bound on how long recall may delay a chat response. The transport
# retries transient errors with backoff, which is right for indexing but must
# not stall an interactive request during a Memory API outage.
_MEMORY_RECALL_TIMEOUT_S = 8.0

# Strong references to fire-and-forget store tasks (asyncio only keeps weak
# refs; without this a pending store could be garbage-collected mid-flight).
_MEMORY_STORE_TASKS: set[asyncio.Task[None]] = set()


async def _recall_and_store_memory(
    request: Request,
    current_user: "User",
    turn_text: str,
    request_type: str = "message",
) -> str | None:
    """Best-effort cross-session memory (DataRobot Memory API).

    Returns recalled context to prepend to the prompt (or None), and persists this
    user turn. Scoped per app user. Never raises into the chat flow.

    Only real user turns (``request_type == "message"``) are recalled and stored.
    Auto-generated "suggestion" prompts are skipped so they neither pollute durable
    memory nor incur the store's server-side fact-extraction cost.

    Recall is awaited with a short timeout (it feeds this response); the store is
    fire-and-forget (its result is never used), so neither can stall the chat
    when the Memory API is slow or down.
    """
    conversation_memory = request.app.state.deps.conversation_memory
    if (
        conversation_memory is None
        or request_type != "message"
        or not turn_text.strip()
    ):
        return None
    user_id = str(current_user.uuid)

    memories: list[str] = []
    try:
        memories = await asyncio.wait_for(
            conversation_memory.retrieve(user_id, turn_text),
            timeout=_MEMORY_RECALL_TIMEOUT_S,
        )
    except Exception:
        logger.warning("memory recall unavailable; continuing", exc_info=True)

    async def _store() -> None:
        try:
            await conversation_memory.store(user_id, turn_text)
        except Exception:
            logger.warning("memory store failed; turn not persisted", exc_info=True)

    task = asyncio.create_task(_store())
    _MEMORY_STORE_TASKS.add(task)
    task.add_done_callback(_MEMORY_STORE_TASKS.discard)

    if not memories:
        return None
    recalled = "\n".join(f"- {m}" for m in memories)
    return "Relevant context about the user from earlier conversations:\n" + recalled


async def _noop_chunks() -> list[dict[str, Any]]:
    """Awaitable returning no chunks (used to keep gather() shapes uniform)."""
    return []


async def _retrieve_semantic_chunks(
    request: Request,
    knowledge_base: "KnowledgeBase",
    query: str,
) -> list[dict[str, Any]]:
    """Top semantic chunks for a READY semantic-mode KB, or [] otherwise.

    Best-effort: any failure returns [] so chat falls back to full content. Only
    a semantic-mode KB whose index is READY is retrieved from (a mid-rebuild
    store is partial and would answer confidently-wrong).
    """
    vector_store = request.app.state.deps.vector_store
    if not (
        vector_store
        and knowledge_base.id
        and query
        and is_semantic_ready(knowledge_base)
    ):
        return []
    try:
        retrieved = await vector_store.retrieve(str(knowledge_base.uuid), query)
        # Build the result inside the try so a malformed chunk (missing key,
        # non-iterable result) also degrades to [] per the best-effort contract,
        # rather than raising and cancelling the sibling recall coroutine.
        return [
            {
                "text": c.get("text", ""),
                "score": c.get("score"),
                "source": c.get("source"),
            }
            for c in retrieved
        ]
    except Exception:
        logger.warning(
            "semantic retrieval failed for kb=%s; falling back to full content",
            knowledge_base.uuid,
            exc_info=True,
        )
        return []


def _build_grounded_context(chunks: list[dict[str, Any]]) -> str:
    """Render retrieved chunks into a grounding block for the system prompt."""
    if not chunks:
        return ""
    lines = [
        "Answer the question using ONLY the excerpts below, retrieved from the "
        "user's documents. If the answer is not contained in them, say the "
        "documents do not cover it. Cite the source filename when relevant.",
        "",
        "Excerpts:",
    ]
    for i, c in enumerate(chunks, 1):
        src = c.get("source") or "unknown"
        lines.append(f"[{i}] (source: {src})\n{c.get('text', '')}")
    return "\n".join(lines)


def _assemble_direct_messages(
    system_prompt: str,
    user_message: str,
    grounded_context: str = "",
    recalled: str | None = None,
) -> list[dict[str, str]]:
    """Build [system, user] messages, folding grounding + recall into system."""
    sys_parts = [system_prompt]
    if grounded_context:
        sys_parts.append(grounded_context)
    if recalled:
        sys_parts.append(recalled)
    return [
        {"role": "system", "content": "\n\n".join(sys_parts)},
        {"role": "user", "content": user_message},
    ]


def _should_use_direct_path(model: str, kb_is_semantic_ready: bool) -> bool:
    """Direct grounded path when the model is non-agent OR the KB is semantic+ready.

    A semantic, indexed KB overrides the agent model: retrieval already did the
    search the crew would perform, so a single grounded call is used instead.
    """
    return model != AGENT_MODEL_NAME or kb_is_semantic_ready


def _effective_direct_model(model: str, default_model: str) -> str:
    """Resolve the LLM model for the direct path.

    The agent deployment name is not a real LLM catalog model, so when a semantic
    KB routes the agent model here, use the configured default LLM instead.
    """
    return default_model if model == AGENT_MODEL_NAME else model


# Push partial answer content to the UI in modest increments rather than on every
# token — bounds DB writes / SSE events while still feeling live.
_STREAM_EMIT_CHARS = 48


async def _consume_stream(
    stream: Any,
    *,
    emit_chars: int,
    on_partial: Callable[[str], Coroutine[Any, Any, None]],
) -> Tuple[str, Any]:
    """Consume a streaming chat completion.

    Accumulates ``delta.content`` and invokes ``on_partial(accumulated_text)`` once
    the content has grown by at least ``emit_chars`` since the last call, so the
    caller can push incremental updates to the UI. Returns
    ``(full_content, usage_payload)``. Raises if the stream signals an error via the
    datarobot-genai ``refusal`` field.
    """
    parts: list[str] = []
    usage: Any | None = None
    last_emit = 0
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = choices[0].delta
        if getattr(delta, "refusal", None) == "error":
            raise RuntimeError(
                getattr(delta, "content", None) or "LLM error with no message"
            )
        content = getattr(delta, "content", None)
        if not isinstance(content, str) or not content:
            continue
        parts.append(content)
        acc = "".join(parts)
        if len(acc) - last_emit >= emit_chars:
            last_emit = len(acc)
            await on_partial(acc)
    return "".join(parts), usage


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

    config: Config = request.app.state.deps.config
    # A semantic-mode KB routes even the agent model to this fast grounded path.
    # The agent deployment name ("ttmdocs-agents") is not a real LLM catalog
    # model, so fall back to the configured default LLM for the completion.
    model = _effective_direct_model(model, config.llm_default_model)

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
    message_obj = await message_repo.get_message(message_uuid)
    chat_id = message_obj.chat_id if message_obj else None

    # Determine system prompt and message based on request type
    system_prompt = (
        SUGGESTIONS_PROMPT if request_type == "suggestion" else SYSTEM_PROMPT
    )
    # Cross-session memory recall and semantic retrieval are independent Memory
    # API round-trips; run them concurrently to save a round-trip on the hot path.
    recalled, chunks = await asyncio.gather(
        _recall_and_store_memory(request, current_user, message, request_type),
        _retrieve_semantic_chunks(request, knowledge_base, message)
        if knowledge_base is not None
        else _noop_chunks(),
    )

    grounded_context = _build_grounded_context(chunks)
    if grounded_context:
        # Semantic path: the KB's documents are covered by the retrieved chunks, so
        # don't inline them again. But user-uploaded files that are NOT part of the
        # KB aren't in the vector store, so still inline those so their content
        # isn't lost.
        augmented_message = message
        if files:
            augmented_message = await _augment_message_with_files(
                message,
                files=files,
                file_repo=file_repo,
                knowledge_base=knowledge_base,
                knowledge_base_repo=knowledge_base_repo,
            )
    else:
        # Fallback: original behavior (full file / KB content in the message).
        augmented_message = message
        if combined_files:
            augmented_message = await _augment_message_with_files(
                message,
                files=combined_files,
                file_repo=file_repo,
                knowledge_base=knowledge_base,
                knowledge_base_repo=knowledge_base_repo,
            )

    messages = _assemble_direct_messages(
        system_prompt, augmented_message, grounded_context, recalled
    )

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

    provider = model.split("/")[0] if "/" in model else model
    with track_chat_request(model=model):
        logger.info(
            "LLM chat started",
            extra={
                "model": model,
                "turn_id": str(message_uuid),
                "chat_id": str(chat_id),
            },
        )
        with _tracer.start_as_current_span(f"gen_ai.chat {model}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.provider.name", provider)
            span.set_attribute(
                "server.address", urlparse(api_base).hostname or api_base
            )
            _set_genai_input_content(span, message, messages)
            span.set_attribute("datarobot.turn_id", str(message_uuid))
            dr_ctx_dict = (
                auth_ctx.metadata.get("dr_ctx", {}) if auth_ctx.metadata else {}
            )
            dr_user_id = dr_ctx_dict.get("user_id")
            if dr_user_id:
                span.set_attribute("datarobot.user_id", str(dr_user_id))
            if chat_id:
                span.set_attribute("gen_ai.conversation.id", str(chat_id))

            async def _emit_partial(acc: str) -> None:
                # Stream partial content to the UI as it is generated (persist +
                # publish, same shape as the final update below) so the user sees
                # the answer fill in instead of waiting for the whole completion.
                if not chat_id:
                    return
                partial = await message_repo.update_message(
                    uuid=message_uuid,
                    update=MessageUpdate(content=acc, in_progress=True),
                )
                if partial:
                    stream_manager.publish(
                        chat_id,
                        MessageEvent(data=partial.dump_json_compatible()),
                    )

            stream = await litellm.acompletion(
                messages=messages,
                model=_normalize_model_id(model),
                api_base=api_base,
                extra_headers=get_extra_headers(request),
                stream=True,
                stream_options={"include_usage": True},
            )
            llm_message_content, usage_payload = await _consume_stream(
                stream, emit_chars=_STREAM_EMIT_CHARS, on_partial=_emit_partial
            )
            _set_genai_output_content(span, llm_message_content)
            if usage_payload:
                token_attrs = {
                    "gen_ai.request.model": model,
                    "gen_ai.provider.name": provider,
                }
                if isinstance(usage_payload, dict):
                    prompt_tokens = usage_payload.get("prompt_tokens")
                    completion_tokens = usage_payload.get("completion_tokens")
                else:
                    prompt_tokens = getattr(usage_payload, "prompt_tokens", None)
                    completion_tokens = getattr(
                        usage_payload, "completion_tokens", None
                    )
                if prompt_tokens is not None:
                    span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
                    _token_counter().add(
                        prompt_tokens,
                        {**token_attrs, "gen_ai.token.type": "input"},
                    )
                if completion_tokens is not None:
                    span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
                    _token_counter().add(
                        completion_tokens,
                        {**token_attrs, "gen_ai.token.type": "output"},
                    )
        logger.info(
            "LLM chat completed",
            extra={"model": model, "turn_id": str(message_uuid)},
        )
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

    # Cross-session agent memory: prepend recalled facts to the question.
    recalled = await _recall_and_store_memory(
        request, current_user, request_data.get("message", ""), request_type
    )
    if recalled:
        content["question"] = f"{recalled}\n\nQuestion: {content['question']}"

    # Add knowledge base to content if provided
    if knowledge_base_schema and knowledge_base:
        vector_store = request.app.state.deps.vector_store
        user_message_text = request_data.get("message", "")

        # Retrieve the most relevant chunks from the DataRobot Memory API (the query
        # is embedded server-side and matched against the KB's stored chunks).
        # Only when this KB is in semantic mode AND its index is READY: during a
        # full-replace rebuild the store is partially populated, and answering
        # from a partial chunk set would be confidently wrong — fall back to the
        # full-content path instead. Keyword mode keeps the original behavior.
        top_chunks: list[dict[str, Any]] = []
        semantic = is_semantic_ready(knowledge_base)
        if vector_store and knowledge_base.id and user_message_text and semantic:
            try:
                retrieved = await vector_store.retrieve(
                    str(knowledge_base.uuid), user_message_text
                )
                top_chunks = [
                    {
                        "text": c["text"],
                        "score": c["score"],
                        "source": c["source"],
                    }
                    for c in retrieved
                ]
                logger.info(
                    "VDB retrieval kb=%s: %d chunk(s) for query %r",
                    knowledge_base.uuid,
                    len(top_chunks),
                    user_message_text[:80],
                )
            except Exception:
                logger.warning(
                    "VDB retrieval failed for kb=%s; falling back to full content",
                    knowledge_base.uuid,
                )
                top_chunks = []
        elif knowledge_base.retrieval_mode == RetrievalMode.SEMANTIC:
            # Semantic KB but retrieval can't run (index building/failed, no
            # store, or empty query) — full-content fallback below.
            logger.info(
                "VDB retrieval skipped kb=%s: index_status=%s vector_store=%s msg=%s",
                knowledge_base.uuid,
                knowledge_base.index_status,
                bool(vector_store),
                bool(user_message_text),
            )

        if top_chunks:
            # Pass only relevant chunks + lightweight KB metadata (no full encoded_content)
            kb_payload = knowledge_base_schema.model_dump(mode="json")
            # Strip heavy encoded_content from each file to avoid token waste
            for f in kb_payload.get("files", []):
                f.pop("encoded_content", None)
            kb_payload["semantic_chunks"] = top_chunks
            content["knowledge_base"] = kb_payload
        else:
            # Fallback: not indexed yet (or retrieval unavailable) — pass full content
            content["knowledge_base"] = knowledge_base_schema.model_dump(mode="json")

        content["topic"] = knowledge_base_schema.description

    # NOTE: content["question"] already carries the (possibly memory-prefixed)
    # augmented message; re-assigning it here would discard recalled memory.
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

    # Get message to access chat_id for publishing task progress
    message_obj = await message_repo.get_message(message_uuid)
    chat_id = message_obj.chat_id if message_obj else None

    agent_provider = llm_model.split("/")[0] if "/" in llm_model else llm_model
    agent_api_base = str(agent_kwargs.get("api_base", ""))
    with track_chat_request(model=llm_model):
        logger.info(
            "Agent chat started",
            extra={
                "model": llm_model,
                "turn_id": str(message_uuid),
                "chat_id": str(chat_id),
            },
        )
        with _tracer.start_as_current_span(f"gen_ai.agent {llm_model}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model", llm_model)
            span.set_attribute("gen_ai.provider.name", agent_provider)
            span.set_attribute(
                "server.address", urlparse(agent_api_base).hostname or agent_api_base
            )
            _set_genai_input_content(span, request_data.get("message", ""), messages)
            span.set_attribute("datarobot.turn_id", str(message_uuid))
            dr_ctx_dict = (
                auth_ctx.metadata.get("dr_ctx", {}) if auth_ctx.metadata else {}
            )
            dr_user_id = dr_ctx_dict.get("user_id")
            if dr_user_id:
                span.set_attribute("datarobot.user_id", str(dr_user_id))
            if chat_id:
                span.set_attribute("gen_ai.conversation.id", str(chat_id))
            processor = TaskProgressProcessor()
            usage_payload: Any | None = None

            async for chunk in await litellm.acompletion(
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                timeout=600,
                extra_headers=get_extra_headers(request),
                **agent_kwargs,
            ):
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_payload = chunk.usage
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    # Check for error signaled via refusal field (set by datarobot-genai)
                    if hasattr(delta, "refusal") and delta.refusal == "error":
                        error_msg = delta.content or "Agent error with no error message"
                        logger.error(
                            "Agent streaming error signaled via refusal field: %s",
                            error_msg,
                        )
                        raise Exception(error_msg)
                    if hasattr(delta, "content") and delta.content:
                        content = delta.content
                        if not isinstance(content, str):
                            logger.warning(
                                "Received non-string content in streaming delta: %s (type: %s)",
                                content,
                                type(content).__name__,
                            )
                            continue

                        task_progress = processor.process_content(content)
                        if task_progress and chat_id:
                            stream_manager.publish(
                                chat_id,
                                TaskProgressEvent(data=task_progress),
                            )

            llm_message_content = processor.flush()
            _set_genai_output_content(span, llm_message_content)
            # Extract token usage from streaming response
            if usage_payload:
                token_attrs = {
                    "gen_ai.request.model": llm_model,
                    "gen_ai.provider.name": agent_provider,
                }
                if isinstance(usage_payload, dict):
                    prompt_tokens = usage_payload.get("prompt_tokens")
                    completion_tokens = usage_payload.get("completion_tokens")
                else:
                    prompt_tokens = getattr(usage_payload, "prompt_tokens", None)
                    completion_tokens = getattr(
                        usage_payload, "completion_tokens", None
                    )
                if prompt_tokens is not None:
                    span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
                    _token_counter().add(
                        prompt_tokens,
                        {**token_attrs, "gen_ai.token.type": "input"},
                    )
                if completion_tokens is not None:
                    span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
                    _token_counter().add(
                        completion_tokens,
                        {**token_attrs, "gen_ai.token.type": "output"},
                    )
            else:
                logger.warning(
                    "No usage payload in agent streaming response; token usage attributes not set",
                    extra={"model": llm_model, "turn_id": str(message_uuid)},
                )

            if not llm_message_content.strip():
                # The upstream stream ended without ever producing content and without
                # signaling an error via the refusal field (e.g. the connection was cut
                # mid-stream by a worker timeout, or a malformed error event was dropped
                # by the SSE parser). Raise so `_update_message_on_exception` surfaces a
                # visible error instead of silently persisting an empty assistant message.
                raise Exception(
                    "Agent returned an empty response. The stream may have been "
                    "interrupted before completion; please retry."
                )

        logger.info(
            "Agent chat completed",
            extra={"model": llm_model, "turn_id": str(message_uuid)},
        )
    update_model = MessageUpdate(
        content=llm_message_content,
        in_progress=False,
    )
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
    db: DBCtx = request.app.state.deps.db
    async with db.session_scope():
        new_chat: Chat = await chat_repo.create_chat(
            ChatCreate(name="New Chat", user_uuid=current_user.uuid)
        )

        _, response_message = await _create_new_message_exchange(
            message_repo, new_chat.uuid, model, message
        )

    stream_manager: ChatStreamManager = request.app.state.stream_manager
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
    db: DBCtx = request.app.state.deps.db

    # Check if chat exists
    chat = await chat_repo.get_chat(chat_uuid)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    stream_manager: ChatStreamManager = request.app.state.stream_manager

    async with db.session_scope():
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
