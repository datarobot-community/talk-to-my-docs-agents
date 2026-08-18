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
"""Unit tests for MemoryApiVectorStore (mocked HTTP; no network)."""

import json

import pytest

from app.knowledge_bases.memory_api_vdb import (
    ConversationMemory,
    MemoryApiVectorStore,
)


class _FakeResponse:
    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Call:
    def __init__(self, method: str, url: str, body: dict | None, params: dict | None):
        self.method = method
        self.url = url
        self.body = body
        self.params = params or {}


class _FakeClient:
    """Records requests; returns queued responses matched by (method, substring)."""

    def __init__(self) -> None:
        self.calls: list[_Call] = []
        self.handlers: list[tuple[str, str, _FakeResponse]] = []

    def queue(self, method: str, substr: str, status: int, payload: dict) -> None:
        self.handlers.append((method, substr, _FakeResponse(status, payload)))

    async def request(self, method: str, url: str, **kw):  # type: ignore[no-untyped-def]
        self.calls.append(_Call(method, url, kw.get("json"), kw.get("params")))
        for m, substr, resp in self.handlers:
            if m == method and substr in url:
                return resp
        return _FakeResponse(200, {})

    async def aclose(self) -> None:
        pass

    def of(self, method: str) -> list[_Call]:
        return [c for c in self.calls if c.method == method]


@pytest.fixture
def store() -> tuple[MemoryApiVectorStore, _FakeClient]:
    client = _FakeClient()
    s = MemoryApiVectorStore(
        base_url="https://x/api-gw/agentic-memory-api",
        space_id="sp1",
        client=client,
        chunk_chars=1200,
        overlap=150,
        top_k=10,
        user_prefix="kb-",
        add_batch_size=20,
    )
    return s, client


async def test_retrieve_maps_results(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    client.queue(
        "POST",
        "/v1/memories/search/",
        200,
        {
            "results": [
                {
                    "memory": "Q3 revenue was $4.2M",
                    "score": 0.89,
                    "metadata": {"source": "q3.pdf"},
                },
                {
                    "memory": "onboarding needs approval",
                    "score": 0.71,
                    "metadata": {"source": "hr.pdf"},
                },
            ]
        },
    )
    out = await s.retrieve(1, "how much revenue", top_k=2)
    assert [c["text"] for c in out] == [
        "Q3 revenue was $4.2M",
        "onboarding needs approval",
    ]
    assert out[0]["score"] == 0.89 and out[0]["source"] == "q3.pdf"
    body = client.of("POST")[-1].body
    assert body["user_id"] == "kb-1" and body["top_k"] == 2


async def test_retrieve_clamps_top_k_to_service_max(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    client.queue("POST", "/v1/memories/search/", 200, {"results": []})
    await s.retrieve(1, "q", top_k=1000)  # far above the service's cap of 50
    assert client.of("POST")[-1].body["top_k"] == 50


class _SeqClient:
    """Returns a queued sequence of statuses in order (for retry tests)."""

    def __init__(self, statuses: list[int]) -> None:
        self._statuses = list(statuses)
        self.attempts = 0

    async def request(self, method: str, url: str, **kw):  # type: ignore[no-untyped-def]
        self.attempts += 1
        status = self._statuses.pop(0) if self._statuses else 200
        return _FakeResponse(status, {"results": []})

    async def aclose(self) -> None:
        pass


async def test_req_retries_transient_then_succeeds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.knowledge_bases.memory_api_vdb as mod

    monkeypatch.setattr(mod, "_RETRY_BASE_DELAY", 0.0)  # no real sleeping
    client = _SeqClient([502, 503, 200])  # two transient failures, then OK
    s = MemoryApiVectorStore(base_url="https://x", space_id="sp1", client=client)
    out = await s.retrieve(1, "q")
    assert out == []  # succeeded on the 3rd attempt
    assert client.attempts == 3


async def test_req_gives_up_after_max_retries(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.knowledge_bases.memory_api_vdb as mod

    monkeypatch.setattr(mod, "_RETRY_BASE_DELAY", 0.0)
    client = _SeqClient([502] * 10)  # always transient
    s = MemoryApiVectorStore(base_url="https://x", space_id="sp1", client=client)
    with pytest.raises(RuntimeError):
        await s.retrieve(1, "q")
    assert client.attempts == mod._MAX_RETRIES + 1  # 1 initial + N retries


async def test_req_honors_retry_after_header(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A 503 with Retry-After is retried after exactly that many seconds."""
    slept: list[float] = []

    async def _fake_sleep(d: float) -> None:
        slept.append(d)

    monkeypatch.setattr("app.knowledge_bases.memory_api_vdb.asyncio.sleep", _fake_sleep)

    class _Client:
        def __init__(self) -> None:
            self.n = 0

        async def request(self, method, url, **kw):  # type: ignore[no-untyped-def]
            self.n += 1
            if self.n == 1:
                return _FakeResponse(503, {}, headers={"Retry-After": "2"})
            return _FakeResponse(200, {"results": []})

        async def aclose(self) -> None:
            pass

    s = MemoryApiVectorStore(base_url="https://x", space_id="sp1", client=_Client())
    await s.retrieve(1, "q")
    assert slept == [2.0]  # honored Retry-After, not the 0.5s exponential base


async def test_add_document_scopes_and_sets_metadata(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    n = await s.add_document(1, "d1", "hello world", "a.txt")
    adds = [c for c in client.of("POST") if c.url.endswith("/v1/memories/")]
    assert len(adds) == 1 and n == 1
    body = adds[0].body
    assert body["infer"] is False
    assert body["user_id"] == "kb-1"
    assert body["run_id"] == "doc-d1"  # per-doc scope for targeted delete
    assert body["metadata"]["doc_id"] == "d1" and body["metadata"]["source"] == "a.txt"
    assert body["metadata"]["chunk_index"] == 0
    assert body["messages"][0]["content"] == "hello world"


async def test_add_document_batches_chunks(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    """A big doc is sent in batches of <= add_batch_size messages per POST."""
    s, client = store  # fixture sets add_batch_size=20
    big = "\n\n".join(f"paragraph number {i} with some text" for i in range(50))
    n = await s.add_document(1, "d1", big, "a.txt")
    adds = [c for c in client.of("POST") if c.url.endswith("/v1/memories/")]
    assert len(adds) < n  # far fewer requests than chunks
    assert max(len(a.body["messages"]) for a in adds) <= s._add_batch_size
    assert sum(len(a.body["messages"]) for a in adds) == n
    assert all(a.body["run_id"] == "doc-d1" for a in adds)


async def test_add_document_logs_progress(
    store: tuple[MemoryApiVectorStore, _FakeClient], caplog
) -> None:  # type: ignore[no-untyped-def]
    import logging

    s, client = store
    caplog.set_level(logging.INFO, logger="app.knowledge_bases.memory_api_vdb")
    big = "\n\n".join(f"paragraph {i} text here" for i in range(250))
    n = await s.add_document(1, "d1", big, "f.txt")
    progress = [r.message for r in caplog.records if "progress" in r.message]
    assert progress
    assert f"{n}/{n}" in progress[-1]


async def test_add_document_no_chunks_no_request(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    n = await s.add_document(1, "d1", "   ", "a.txt")  # whitespace -> no chunks
    assert n == 0
    assert [c for c in client.of("POST") if c.url.endswith("/v1/memories/")] == []


async def test_add_document_raises_when_an_add_fails(
    store: tuple[MemoryApiVectorStore, _FakeClient], monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """A failed add surfaces as a raised error (so the indexer marks FAILED), and
    gather uses return_exceptions=True so no sibling add outlives the build and
    leaks into the next one."""
    import app.knowledge_bases.memory_api_vdb as mod

    monkeypatch.setattr(mod, "_RETRY_BASE_DELAY", 0.0)  # no real sleeping
    s, client = store
    client.queue("POST", "/v1/memories/", 500, {})  # every add fails
    with pytest.raises(RuntimeError):
        await s.add_document("kb-uuid-1", "d1", "hello world", "a.txt")


async def test_delete_document_scopes_by_kb_and_doc(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    await s.delete_document(1, "d1")
    deletes = client.of("DELETE")
    assert len(deletes) == 1
    assert deletes[0].url.endswith("/v1/memories/")
    assert deletes[0].params == {"user_id": "kb-1", "run_id": "doc-d1"}


async def test_delete_kb_deletes_identity_in_one_call(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, client = store
    await s.delete_kb(7)
    deletes = client.of("DELETE")
    assert len(deletes) == 1
    assert deletes[0].url.endswith("/v1/memories/")
    assert deletes[0].params == {"user_id": "kb-7"}


async def test_doc_sha_is_config_aware(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    s, _ = store
    a = s.doc_sha("same content")
    assert a == s.doc_sha("same content")  # stable
    assert a != s.doc_sha("different")  # content-sensitive
    s._chunk_chars += 1  # a chunking-config change must invalidate the hash
    assert a != s.doc_sha("same content")


def test_chunk_near_limit_paragraph_emits_no_empty_chunks(
    store: tuple[MemoryApiVectorStore, _FakeClient],
) -> None:
    """A paragraph at the chunk-size limit must not produce a leading empty chunk
    when the buffer is empty (an empty buffer needs no separator)."""
    s, _ = store  # chunk_chars=1200
    for size in (s._chunk_chars - 1, s._chunk_chars):
        chunks = s._chunk("x" * size)
        assert chunks == ["x" * size]
        assert all(c for c in chunks)  # no empty chunks slip through


def test_overlap_at_or_above_chunk_size_is_clamped() -> None:
    """An overlap >= chunk_chars would step 1 char at a time and emit ~one chunk per
    character of an oversized paragraph. The overlap is clamped so the window always
    makes real progress."""
    for overlap in (100, 200, 10_000):  # == chunk_chars, > it, absurd
        s = MemoryApiVectorStore(
            base_url="https://x",
            space_id="sp1",
            client=_FakeClient(),
            chunk_chars=100,
            overlap=overlap,
        )
        assert s._overlap <= s._chunk_chars // 2
        chunks = s._chunk("y" * 1000)  # oversized single paragraph
        # Bounded to ~2x the no-overlap count, nowhere near one chunk per character.
        assert len(chunks) <= 2 * (1000 // s._chunk_chars) + 2
        assert all(c for c in chunks)


def test_sane_overlap_is_left_alone() -> None:
    """The clamp must not disturb a normal configuration."""
    s = MemoryApiVectorStore(
        base_url="https://x",
        space_id="sp1",
        client=_FakeClient(),
        chunk_chars=2000,
        overlap=150,
    )
    assert s._overlap == 150


# --- ConversationMemory (Tier 2) ---


@pytest.fixture
def memory() -> tuple[ConversationMemory, _FakeClient]:
    client = _FakeClient()
    m = ConversationMemory(
        base_url="https://x/api-gw/agentic-memory-api",
        space_id="sp1",
        client=client,
        top_k=5,
    )
    return m, client


async def test_conversation_retrieve_returns_texts(
    memory: tuple[ConversationMemory, _FakeClient],
) -> None:
    m, client = memory
    client.queue(
        "POST",
        "/v1/memories/search/",
        200,
        {
            "results": [
                {"memory": "user prefers metric units"},
                {"memory": "based in Austin"},
            ]
        },
    )
    out = await m.retrieve("user-42", "where is the user?", top_k=3)
    assert out == ["user prefers metric units", "based in Austin"]
    body = client.of("POST")[-1].body
    assert body["user_id"] == "user-42" and body["top_k"] == 3


async def test_conversation_store_posts_turn_with_fact_extraction(
    memory: tuple[ConversationMemory, _FakeClient],
) -> None:
    m, client = memory
    await m.store("user-42", "I moved to Austin last month")
    adds = client.of("POST")
    assert len(adds) == 1
    body = adds[0].body
    assert body["user_id"] == "user-42"
    assert body["messages"][0]["content"] == "I moved to Austin last month"
    assert "infer" not in body  # default fact-extraction (mem0 infer=true)
    assert body["metadata"]["kind"] == "chat"


async def test_conversation_store_ignores_blank(
    memory: tuple[ConversationMemory, _FakeClient],
) -> None:
    m, client = memory
    await m.store("user-42", "   ")
    assert client.of("POST") == []


async def test_add_concurrency_budget_is_shared_across_documents() -> None:
    """The add semaphore is per store, not per call.

    Several documents are indexed concurrently, so a per-call semaphore would let
    each one run index_concurrency requests at once (N x the cap). The Memory API
    500s under heavy concurrent writes, so the budget must be global to the store.
    """
    import asyncio

    class _SlowClient:
        def __init__(self) -> None:
            self.in_flight = 0
            self.peak = 0

        async def request(self, method, url, **kw):  # type: ignore[no-untyped-def]
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            await asyncio.sleep(0)  # let siblings pile up if unbounded
            self.in_flight -= 1
            return _FakeResponse(200, {})

        async def aclose(self) -> None:
            pass

    client = _SlowClient()
    s = MemoryApiVectorStore(
        base_url="https://x",
        space_id="sp1",
        client=client,
        chunk_chars=10,
        overlap=0,
        index_concurrency=2,
        add_batch_size=1,  # one request per chunk, to maximize fan-out
    )
    # Three documents, each many chunks, all indexed at once.
    body = "\n\n".join(f"paragraph {i} of text" for i in range(10))
    await asyncio.gather(
        *(s.add_document("kb-u", f"d{i}", body, "f.txt") for i in range(3))
    )

    assert s._write_semaphore() is s._write_semaphore()  # one instance, reused
    assert client.peak <= 2  # global cap honored across all three documents


async def test_delete_document_shares_the_write_budget() -> None:
    """Per-document deletes are gated too.

    The indexer deletes-then-adds many documents at once; an ungated delete per
    document would burst past vdb_index_concurrency against a service that 500s
    under heavy concurrent writes.
    """
    import asyncio

    class _SlowClient:
        def __init__(self) -> None:
            self.in_flight = 0
            self.peak = 0

        async def request(self, method, url, **kw):  # type: ignore[no-untyped-def]
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            await asyncio.sleep(0)
            self.in_flight -= 1
            return _FakeResponse(200, {})

        async def aclose(self) -> None:
            pass

    client = _SlowClient()
    s = MemoryApiVectorStore(
        base_url="https://x", space_id="sp1", client=client, index_concurrency=2
    )
    await asyncio.gather(*(s.delete_document("kb-u", f"d{i}") for i in range(12)))
    assert client.peak <= 2
