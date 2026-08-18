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
"""Unit tests for the fast grounded (direct) semantic-chat path."""

from types import SimpleNamespace

import app.api.v1.chat as chat_mod
from app.api.v1.chat import (
    AGENT_MODEL_NAME,
    _assemble_direct_messages,
    _build_grounded_context,
    _effective_direct_model,
    _kb_is_semantic_ready,
    _retrieve_semantic_chunks,
    _should_use_direct_path,
)
from app.knowledge_bases import IndexStatus, RetrievalMode


class _FakeStore:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks
        self.calls: list = []

    async def retrieve(self, kb_id, query, top_k=None):  # type: ignore[no-untyped-def]
        self.calls.append((kb_id, query))
        return self._chunks


def _req(store):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(deps=SimpleNamespace(vector_store=store))
        )
    )


def _kb(mode=RetrievalMode.SEMANTIC, status=IndexStatus.READY, kid=7):  # type: ignore[no-untyped-def]
    return SimpleNamespace(id=kid, uuid="u", retrieval_mode=mode, index_status=status)


# --- _retrieve_semantic_chunks ---


async def test_retrieve_returns_chunks_for_ready_semantic_kb() -> None:
    store = _FakeStore([{"text": "T", "score": 0.9, "source": "a.pdf"}])
    out = await _retrieve_semantic_chunks(_req(store), _kb(), "q")
    assert out == [{"text": "T", "score": 0.9, "source": "a.pdf"}]
    assert store.calls == [("u", "q")]  # retrieval keyed on the KB uuid, not the id


async def test_retrieve_empty_when_not_ready() -> None:
    store = _FakeStore([{"text": "T"}])
    out = await _retrieve_semantic_chunks(
        _req(store), _kb(status=IndexStatus.INDEXING), "q"
    )
    assert out == [] and store.calls == []


async def test_retrieve_empty_when_keyword_or_no_store() -> None:
    store = _FakeStore([{"text": "T"}])
    assert (
        await _retrieve_semantic_chunks(
            _req(store), _kb(mode=RetrievalMode.KEYWORD), "q"
        )
        == []
    )
    assert await _retrieve_semantic_chunks(_req(None), _kb(), "q") == []


async def test_retrieve_swallows_errors() -> None:
    class _Boom:
        async def retrieve(self, *a, **k):  # type: ignore[no-untyped-def]
            raise RuntimeError("down")

    out = await _retrieve_semantic_chunks(_req(_Boom()), _kb(), "q")
    assert out == []


async def test_retrieve_tolerates_chunks_missing_keys() -> None:
    """A chunk missing score/source must not raise (which would cancel the sibling
    recall coroutine in the gather); missing keys degrade to None."""
    store = _FakeStore([{"text": "only text"}, {"text": "t2", "score": 0.5}])
    out = await _retrieve_semantic_chunks(_req(store), _kb(), "q")
    assert out == [
        {"text": "only text", "score": None, "source": None},
        {"text": "t2", "score": 0.5, "source": None},
    ]


# --- _build_grounded_context ---


def test_build_grounded_context_formats_chunks_and_sources() -> None:
    ctx = _build_grounded_context(
        [
            {"text": "Alpha", "score": 0.9, "source": "a.pdf"},
            {"text": "Beta", "score": 0.8, "source": "b.pdf"},
        ]
    )
    assert "Alpha" in ctx and "Beta" in ctx
    assert "a.pdf" in ctx and "b.pdf" in ctx
    assert "only" in ctx.lower()


def test_build_grounded_context_empty() -> None:
    assert _build_grounded_context([]) == ""


# --- _assemble_direct_messages ---


def test_assemble_uses_grounded_context_and_recall_for_semantic() -> None:
    msgs = _assemble_direct_messages(
        system_prompt="SYS",
        user_message="where do I live?",
        grounded_context="Excerpts:\n[1] (source: a.pdf)\nAustin",
        recalled="Relevant context:\n- lives in Austin",
    )
    assert msgs[0]["role"] == "system"
    assert "SYS" in msgs[0]["content"]
    assert "Austin" in msgs[0]["content"]
    assert "Relevant context" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "where do I live?"}


def test_assemble_plain_when_no_context() -> None:
    msgs = _assemble_direct_messages("SYS", "hi", grounded_context="", recalled=None)
    assert msgs == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
    ]


# --- _should_use_direct_path ---


def test_direct_path_for_semantic_even_with_agent_model() -> None:
    assert _should_use_direct_path(AGENT_MODEL_NAME, kb_is_semantic_ready=True) is True


def test_agent_path_for_agent_model_keyword_kb() -> None:
    assert (
        _should_use_direct_path(AGENT_MODEL_NAME, kb_is_semantic_ready=False) is False
    )


def test_direct_path_for_non_agent_model() -> None:
    assert (
        _should_use_direct_path("azure/gpt-4o-mini", kb_is_semantic_ready=False) is True
    )


# --- _effective_direct_model ---


def test_agent_model_on_direct_path_falls_back_to_default_llm() -> None:
    # The agent deployment name is not a real LLM catalog model.
    assert _effective_direct_model(AGENT_MODEL_NAME, "azure/gpt-4o-mini") == (
        "azure/gpt-4o-mini"
    )


def test_real_model_on_direct_path_is_kept() -> None:
    assert (
        _effective_direct_model("azure/gpt-4o-mini", "default") == "azure/gpt-4o-mini"
    )


# --- _consume_stream (fast grounded path streams token-by-token) ---


def _chunk(content=None, usage=None, refusal=None, choiceless=False):  # type: ignore[no-untyped-def]
    if choiceless:
        return SimpleNamespace(choices=None, usage=usage)
    delta = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


async def _astream(chunks):  # type: ignore[no-untyped-def]
    for c in chunks:
        yield c


async def test_consume_stream_accumulates_and_emits_partials() -> None:
    from app.api.v1.chat import _consume_stream

    emits: list[str] = []

    async def on_partial(acc: str) -> None:
        emits.append(acc)

    chunks = [
        _chunk("Hello "),
        _chunk("world"),
        _chunk("!", usage={"prompt_tokens": 3, "completion_tokens": 5}),
    ]
    full, usage = await _consume_stream(
        _astream(chunks), emit_chars=3, on_partial=on_partial
    )
    assert full == "Hello world!"
    assert usage == {"prompt_tokens": 3, "completion_tokens": 5}
    # Partials are emitted incrementally as the content grows past the threshold.
    assert emits == ["Hello ", "Hello world"]


async def test_consume_stream_raises_on_refusal_error() -> None:
    import pytest

    from app.api.v1.chat import _consume_stream

    async def on_partial(acc: str) -> None:
        pass

    with pytest.raises(RuntimeError):
        await _consume_stream(
            _astream([_chunk(content="boom", refusal="error")]),
            emit_chars=1,
            on_partial=on_partial,
        )


async def test_consume_stream_ignores_empty_and_choiceless_chunks() -> None:
    from app.api.v1.chat import _consume_stream

    seen: list[str] = []

    async def on_partial(acc: str) -> None:
        seen.append(acc)

    chunks = [
        _chunk(choiceless=True),  # no choices
        _chunk(content=None),  # None content
        _chunk(content=""),  # empty
        _chunk(content="ok"),  # real content
    ]
    full, usage = await _consume_stream(
        _astream(chunks), emit_chars=1, on_partial=on_partial
    )
    assert full == "ok"
    assert usage is None
    assert seen == ["ok"]


# --- _kb_is_semantic_ready (routing gate: agent-model chats to the fast path) ---


def _routing_req(store, body):  # type: ignore[no-untyped-def]
    async def _json():
        return body

    return SimpleNamespace(
        json=_json,
        app=SimpleNamespace(
            state=SimpleNamespace(
                deps=SimpleNamespace(
                    vector_store=store,
                    user_repo=object(),
                    knowledge_base_repo=object(),
                )
            )
        ),
    )


_AUTH = SimpleNamespace(user=SimpleNamespace(id=1))


def _patch_lookups(monkeypatch, kb):  # type: ignore[no-untyped-def]
    async def _user(_repo, uid):  # type: ignore[no-untyped-def]
        return SimpleNamespace(id=uid)

    async def _fetch(**_kw):  # type: ignore[no-untyped-def]
        return kb

    monkeypatch.setattr(chat_mod, "_get_current_user", _user)
    monkeypatch.setattr(chat_mod, "_get_knowledge_base", _fetch)


async def test_kb_is_semantic_ready_true_for_ready_semantic_kb(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_lookups(monkeypatch, _kb())
    req = _routing_req(_FakeStore([]), {"knowledge_base_id": "u"})
    assert await _kb_is_semantic_ready(req, _AUTH) is True


async def test_kb_is_semantic_ready_false_when_indexing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_lookups(monkeypatch, _kb(status=IndexStatus.INDEXING))
    req = _routing_req(_FakeStore([]), {"knowledge_base_id": "u"})
    assert await _kb_is_semantic_ready(req, _AUTH) is False


async def test_kb_is_semantic_ready_false_for_keyword_kb(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_lookups(monkeypatch, _kb(mode=RetrievalMode.KEYWORD))
    req = _routing_req(_FakeStore([]), {"knowledge_base_id": "u"})
    assert await _kb_is_semantic_ready(req, _AUTH) is False


async def test_kb_is_semantic_ready_false_when_no_vector_store(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_lookups(monkeypatch, _kb())
    req = _routing_req(None, {"knowledge_base_id": "u"})
    assert await _kb_is_semantic_ready(req, _AUTH) is False


async def test_kb_is_semantic_ready_false_when_no_kb_id() -> None:
    # No knowledge_base_id in the body: returns before any lookup, so no patching.
    req = _routing_req(_FakeStore([]), {"message": "hi"})
    assert await _kb_is_semantic_ready(req, _AUTH) is False


async def test_kb_is_semantic_ready_false_on_lookup_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def _boom(**_kw):  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")

    async def _user(_repo, uid):  # type: ignore[no-untyped-def]
        return SimpleNamespace(id=uid)

    monkeypatch.setattr(chat_mod, "_get_current_user", _user)
    monkeypatch.setattr(chat_mod, "_get_knowledge_base", _boom)
    req = _routing_req(_FakeStore([]), {"knowledge_base_id": "u"})
    assert await _kb_is_semantic_ready(req, _AUTH) is False
