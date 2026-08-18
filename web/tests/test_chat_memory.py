# Copyright 2026 DataRobot, Inc.
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
"""Unit tests for the chat cross-session memory hook (_recall_and_store_memory)."""

import asyncio
from types import SimpleNamespace

from app.api.v1.chat import _MEMORY_STORE_TASKS, _recall_and_store_memory


async def _drain_store_tasks() -> None:
    """The store is fire-and-forget; wait for pending tasks so asserts see it."""
    if _MEMORY_STORE_TASKS:
        await asyncio.gather(*_MEMORY_STORE_TASKS, return_exceptions=True)


class _FakeMemory:
    def __init__(self, memories: list[str] | None = None, raises: bool = False) -> None:
        self._memories = memories or []
        self._raises = raises
        self.retrieved: list[tuple[str, str]] = []
        self.stored: list[tuple[str, str]] = []

    async def retrieve(self, user_id: str, query: str, top_k: int | None = None):
        if self._raises:
            raise RuntimeError("memory service down")
        self.retrieved.append((user_id, query))
        return list(self._memories)

    async def store(self, user_id: str, content: str) -> None:
        if self._raises:
            raise RuntimeError("memory service down")
        self.stored.append((user_id, content))


def _request(conversation_memory) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                deps=SimpleNamespace(conversation_memory=conversation_memory)
            )
        )
    )


_USER = SimpleNamespace(uuid="user-1")


async def test_returns_none_when_memory_disabled() -> None:
    out = await _recall_and_store_memory(_request(None), _USER, "hello")
    assert out is None


async def test_returns_none_for_blank_turn() -> None:
    mem = _FakeMemory(["fact"])
    out = await _recall_and_store_memory(_request(mem), _USER, "   ")
    assert out is None
    assert mem.retrieved == [] and mem.stored == []


async def test_recalls_and_stores() -> None:
    mem = _FakeMemory(["User lives in Austin", "User loves hiking"])
    out = await _recall_and_store_memory(_request(mem), _USER, "where do I live?")
    assert out is not None
    assert "Relevant context about the user" in out
    assert "- User lives in Austin" in out and "- User loves hiking" in out
    # both retrieve and store happened, scoped to the app user
    await _drain_store_tasks()
    assert mem.retrieved == [("user-1", "where do I live?")]
    assert mem.stored == [("user-1", "where do I live?")]


async def test_skips_suggestion_requests() -> None:
    # Auto-generated suggestion prompts must not touch durable memory.
    mem = _FakeMemory(["fact"])
    out = await _recall_and_store_memory(
        _request(mem), _USER, "suggest follow-ups", request_type="suggestion"
    )
    assert out is None
    assert mem.retrieved == [] and mem.stored == []


async def test_store_failure_still_returns_recall() -> None:
    # A store failure must not discard facts already recalled.
    class _StoreFails(_FakeMemory):
        async def store(self, user_id: str, content: str) -> None:
            raise RuntimeError("store down")

    mem = _StoreFails(["User lives in Austin"])
    out = await _recall_and_store_memory(_request(mem), _USER, "where do I live?")
    assert out is not None and "User lives in Austin" in out
    await _drain_store_tasks()  # consume the failed task (logged, not raised)


async def test_stores_even_when_no_recall() -> None:
    mem = _FakeMemory([])  # nothing to recall
    out = await _recall_and_store_memory(_request(mem), _USER, "first message")
    assert out is None  # no prior facts
    await _drain_store_tasks()
    assert mem.stored == [("user-1", "first message")]  # turn still persisted


async def test_degrades_on_error() -> None:
    mem = _FakeMemory(raises=True)
    out = await _recall_and_store_memory(_request(mem), _USER, "hello")
    assert out is None  # never raises into the chat flow
    await _drain_store_tasks()  # consume the failed store task


async def test_recall_timeout_does_not_block() -> None:
    # A hanging Memory API must not stall the chat past the recall timeout.
    class _Hangs(_FakeMemory):
        async def retrieve(self, user_id, query, top_k=None):
            await asyncio.sleep(3600)

    import app.api.v1.chat as chat_mod

    orig = chat_mod._MEMORY_RECALL_TIMEOUT_S
    chat_mod._MEMORY_RECALL_TIMEOUT_S = 0.05
    try:
        mem = _Hangs(["fact"])
        out = await asyncio.wait_for(
            _recall_and_store_memory(_request(mem), _USER, "hello"), timeout=5
        )
        assert out is None  # timed out recall degrades to no-memory
        await _drain_store_tasks()
        assert mem.stored == [("user-1", "hello")]  # store still fired
    finally:
        chat_mod._MEMORY_RECALL_TIMEOUT_S = orig


class _RecordingSpan:
    def __init__(self) -> None:
        self.attrs: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attrs[key] = value


def test_genai_content_attributes_off_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Recalled memories flow into messages, so message content must NOT reach span
    attributes unless capture is explicitly enabled."""
    import app.api.v1.chat as chat_mod

    monkeypatch.setattr(chat_mod, "getenv", lambda key, default=None: "false")
    span = _RecordingSpan()
    chat_mod._set_genai_input_content(span, "hi", [{"role": "user", "content": "hi"}])
    chat_mod._set_genai_output_content(span, "the answer")
    assert span.attrs == {}  # no content leaked to the trace backend


def test_genai_content_attributes_recorded_when_enabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.api.v1.chat as chat_mod

    monkeypatch.setattr(chat_mod, "getenv", lambda key, default=None: "true")
    span = _RecordingSpan()
    chat_mod._set_genai_input_content(span, "hi", [{"role": "user", "content": "hi"}])
    chat_mod._set_genai_output_content(span, "the answer")
    assert span.attrs["gen_ai.prompt"] == "hi"
    assert span.attrs["gen_ai.completion"] == "the answer"
    assert "gen_ai.input.messages" in span.attrs
    assert "gen_ai.output.messages" in span.attrs
