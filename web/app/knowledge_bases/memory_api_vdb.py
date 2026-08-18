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
"""DataRobot mem0-compatible Memory API clients.

Two clients share one HTTP transport (``_MemoryApiBase``):

* ``MemoryApiVectorStore`` — document retrieval. Chunks are stored verbatim
  (``infer=false``) scoped by ``user_id=kb-<id>`` (KB, for search) AND
  ``run_id=doc-<doc_id>`` (document, for targeted delete), with
  ``metadata={doc_id, source, chunk_index}``. Indexing is incremental and
  non-destructive: the indexer diffs per-document content hashes (tracked in our
  DB, since the service's 50-result cap prevents enumeration) and only
  add/deletes the documents that changed — retrieval stays valid throughout.
  ``delete_kb`` (whole-identity wipe) is used only for KB deletion / empty-KB
  cleanup.
* ``ConversationMemory`` — cross-session agent memory. Turns are stored under the
  app-user identity with fact-extraction (mem0 default) and retrieved by semantic
  search.

Endpoints (reached via the API gateway at ``{base}/{space}/...``):
    POST   /v1/memories/          add (returns results[].id)
    POST   /v1/memories/search/   search (top_k capped at 50 by the service)
    DELETE /v1/memories/          delete all memories matching an identity filter
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, TypedDict

import httpx

logger = logging.getLogger(__name__)

# The service caps search/list ``top_k`` at 50 (schemas.memory.TopKResults);
# a larger value is rejected with 422, so clamp client-side.
_MAX_TOP_K = 50

# Transient failures worth retrying (gateway hiccups, throttling, brief
# unavailability). Everything else (4xx other than 429) fails fast.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 4  # total attempts = 1 + retries
_RETRY_BASE_DELAY = 0.5  # seconds; exponential backoff
_RETRY_MAX_DELAY = 30.0  # cap on an honored Retry-After


class _Retry(Exception):
    """Internal signal that a response's status is transient and retryable.

    Carries the server's Retry-After (seconds), if provided, so the caller can
    honor it instead of blind exponential backoff (the service returns
    Retry-After: 1 on concurrent-write conflicts).
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header (delta-seconds form) into seconds, or None."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None  # HTTP-date form not honored; fall back to backoff


class RetrievedChunk(TypedDict):
    text: str
    score: float | None
    source: str | None
    metadata: dict[str, Any]


class _MemoryApiBase:
    """Shared transport: HTTP client, URL building, request, and dispose."""

    def __init__(
        self,
        base_url: str,
        space_id: str,
        *,
        token: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._space = space_id
        self._client = client or httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )

    def _path(self, suffix: str) -> str:
        return f"{self._base}/{self._space}{suffix}"

    async def _req(
        self,
        method: str,
        suffix: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self._path(suffix)
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await self._client.request(method, url, json=body, params=params)
                status = getattr(resp, "status_code", 200)
                if status in _RETRY_STATUS and attempt < _MAX_RETRIES:
                    headers = getattr(resp, "headers", {}) or {}
                    raise _Retry(
                        f"HTTP {status}",
                        retry_after=_parse_retry_after(headers.get("Retry-After")),
                    )
                resp.raise_for_status()
                return resp.json() if resp.text else {}
            except (_Retry, httpx.TransportError) as exc:
                if attempt >= _MAX_RETRIES:
                    raise
                # Honor the server's Retry-After when given (the service sends
                # Retry-After: 1 on concurrent-write conflicts); else exponential.
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None:
                    delay = min(retry_after, _RETRY_MAX_DELAY)
                else:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "memory-api: %s %s failed (%s); retry %d/%d in %.1fs",
                    method,
                    suffix,
                    exc,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
        # Unreachable: loop either returns or raises.
        raise RuntimeError("unreachable retry state")

    async def dispose(self) -> None:
        aclose = getattr(self._client, "aclose", None)
        if aclose:
            await aclose()


class MemoryApiVectorStore(_MemoryApiBase):
    """Document-retrieval backend on the Memory API (VectorStore protocol)."""

    def __init__(
        self,
        base_url: str,
        space_id: str,
        *,
        token: str | None = None,
        client: Any | None = None,
        chunk_chars: int = 2000,  # keep in sync with Config.vdb_chunk_chars
        overlap: int = 150,
        top_k: int = 10,
        user_prefix: str = "kb-",
        index_concurrency: int = 6,
        add_batch_size: int = 100,
    ) -> None:
        super().__init__(base_url, space_id, token=token, client=client)
        self._chunk_chars = max(1, chunk_chars)
        # Cap the overlap at half the chunk size. The sliding window advances by
        # (chunk_chars - overlap), so an overlap at or above chunk_chars would step
        # one character at a time and emit ~one chunk PER CHARACTER of an oversized
        # paragraph, each its own embedded HTTP round-trip. Clamping bounds the worst
        # case to roughly 2x the chunk count instead of chunk_chars times it. Sane
        # configs (2000/150) are unaffected.
        max_overlap = self._chunk_chars // 2
        self._overlap = max(0, min(overlap, max_overlap))
        if overlap > max_overlap:
            logger.warning(
                "memory-api: vdb_chunk_overlap_chars=%d is too large for "
                "vdb_chunk_chars=%d; clamping overlap to %d",
                overlap,
                self._chunk_chars,
                self._overlap,
            )
        self._top_k = top_k
        self._prefix = user_prefix
        # Service accepts at most 100 messages per add call.
        self._add_batch_size = max(1, min(add_batch_size, 100))
        # Chunks are added with bounded concurrency: each add is an independent
        # HTTP round-trip that embeds server-side, so a large KB (hundreds of
        # chunks) is dominated by round-trip latency. Fan out, but cap it so we
        # don't overwhelm the service or exhaust the client's connection pool.
        self._index_concurrency = max(1, index_concurrency)
        self._sem: asyncio.Semaphore | None = None

    @property
    def write_concurrency(self) -> int:
        """How many write requests this store will run at once."""
        return self._index_concurrency

    def _write_semaphore(self) -> asyncio.Semaphore:
        """The shared write-concurrency gate for this store.

        Covers every mutating round-trip (chunk adds AND per-document deletes), not
        just adds: callers sync several documents at once, and an ungated delete per
        document would fan out well past the budget.

        One semaphore per store instance, NOT per call: the cap is a budget for the
        whole service, so concurrent work must contend for the same slots. A per-call
        semaphore would let N concurrent documents each run ``index_concurrency``
        requests, and the Memory API 500s under heavy concurrent writes. Created
        lazily so it binds to the running loop.
        """
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._index_concurrency)
        return self._sem

    def _user(self, kb_id: str) -> str:
        # ``kb_id`` is the KB's uuid, not its autoincrement integer PK. The uuid is
        # collision-proof; integer ids restart on a fresh DB, are reused after a
        # delete, and collide across installs sharing one space.
        return f"{self._prefix}{kb_id}"

    def _chunk(self, content: str) -> list[str]:
        paras = re.split(r"\n\s*\n", content)
        chunks: list[str] = []
        buf = ""
        for para in paras:
            para = para.strip()
            if not para:
                continue
            if len(para) > self._chunk_chars:
                if buf:
                    chunks.append(buf)
                    buf = ""
                step = max(1, self._chunk_chars - self._overlap)
                for i in range(0, len(para), step):
                    chunks.append(para[i : i + self._chunk_chars])
            elif len(buf) + len(para) + (2 if buf else 0) <= self._chunk_chars:
                buf = f"{buf}\n\n{para}" if buf else para
            else:
                if buf:
                    chunks.append(buf)
                buf = para
        if buf:
            chunks.append(buf)
        return chunks

    def _doc_run(self, doc_id: str) -> str:
        """Per-document identity scope: search is by kb, delete/add by (kb, doc)."""
        return f"doc-{doc_id}"

    def doc_sha(self, content: str) -> str:
        """Content hash that also varies with the chunking config.

        Used by the indexer to detect per-document changes. Including the chunk
        settings means a chunk_chars/overlap change re-indexes a document even
        when its text is unchanged.
        """
        h = hashlib.sha256()
        h.update(f"{self._chunk_chars}:{self._overlap}:".encode("ascii"))
        h.update(content.encode("utf-8"))
        return h.hexdigest()

    async def add_document(
        self, kb_id: str, doc_id: str, content: str, source: str | None
    ) -> int:
        """Chunk *content* and store it under user_id=kb-<id>, run_id=doc-<doc_id>.

        Chunks are added in batches of up to ``add_batch_size`` messages per
        request (one POST stores each message as a separate memory; request
        metadata applies to the whole batch, so batches never span documents).
        Batches run at bounded concurrency. Returns the number of chunks added.

        This does NOT delete first: callers wanting replace semantics call
        ``delete_document`` beforehand. Search (by user_id) still sees these
        chunks; the run_id only scopes targeted deletes.

        TTL: we intentionally omit ``expiration_date`` so the service applies its
        maximum retention (the longest supported). A knowledge base that must
        outlive that max needs a periodic re-index; a scheduled refresh is out of
        scope here (cross-replica scheduling).
        """
        user_id = self._user(kb_id)
        run_id = self._doc_run(doc_id)
        chunks = self._chunk(content)
        if not chunks:
            return 0

        batch_size = self._add_batch_size
        batches: list[dict[str, Any]] = []
        for i in range(0, len(chunks), batch_size):
            group = chunks[i : i + batch_size]
            batches.append(
                {
                    "user_id": user_id,
                    "run_id": run_id,
                    "messages": [{"role": "user", "content": ch} for ch in group],
                    "infer": False,
                    # chunk_index is the batch's starting offset (request metadata
                    # is per-batch, not per-message), giving coarse doc ordering.
                    "metadata": {
                        "doc_id": doc_id,
                        "source": source,
                        "chunk_index": i,
                    },
                }
            )

        total = len(chunks)
        done = 0
        sem = self._write_semaphore()

        async def _add(body: dict[str, Any]) -> None:
            nonlocal done
            async with sem:
                await self._req("POST", "/v1/memories/", body)
            n = len(body["messages"])
            prev, done = done, done + n
            # A large document is otherwise silent for a while; log per 100 chunks.
            if done == total or done // 100 != prev // 100:
                logger.info(
                    "memory-api: kb_id=%s doc=%s progress %d/%d chunks",
                    kb_id,
                    doc_id,
                    done,
                    total,
                )

        # Wait for every add to settle before propagating a failure. With the
        # default return_exceptions=False, gather raises on the first error but
        # leaves the sibling adds running in the background; because the per-KB
        # lock releases as soon as this build fails, those leaked writers can land
        # in the *next* build's index after it wipes, orphaning chunks. Collect
        # all results, then raise, so no add outlives its build.
        results = await asyncio.gather(
            *(_add(body) for body in batches), return_exceptions=True
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise errors[0]
        return total

    async def delete_document(self, kb_id: str, doc_id: str) -> None:
        """Delete a single document's chunks (identity-filtered by kb + doc).

        Gated by the shared write semaphore: callers sync many documents at once, so
        an ungated delete-per-document would burst past the concurrency budget.
        """
        async with self._write_semaphore():
            await self._req(
                "DELETE",
                "/v1/memories/",
                params={"user_id": self._user(kb_id), "run_id": self._doc_run(doc_id)},
            )

    async def retrieve(
        self, kb_id: str, query: str, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        data = await self._req(
            "POST",
            "/v1/memories/search/",
            {
                "user_id": self._user(kb_id),
                "query": query,
                "top_k": min(top_k or self._top_k, _MAX_TOP_K),
            },
        )
        out: list[RetrievedChunk] = []
        for item in (data or {}).get("results", []) or []:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") or {}
            score = item.get("score")
            out.append(
                RetrievedChunk(
                    text=item.get("memory") or item.get("content") or "",
                    score=float(score) if isinstance(score, (int, float)) else None,
                    source=meta.get("source"),
                    metadata=meta,
                )
            )
        return out

    async def delete_kb(self, kb_id: str) -> None:
        """Delete every memory scoped to this KB in one identity-filtered call."""
        await self._req(
            "DELETE", "/v1/memories/", params={"user_id": self._user(kb_id)}
        )


class ConversationMemory(_MemoryApiBase):
    """Cross-session agent memory on the Memory API, scoped per app user.

    Turns are stored with mem0's default fact-extraction so the service keeps
    durable facts about the user; retrieval is a semantic search over those.
    """

    def __init__(
        self,
        base_url: str,
        space_id: str,
        *,
        token: str | None = None,
        client: Any | None = None,
        top_k: int = 5,
    ) -> None:
        super().__init__(base_url, space_id, token=token, client=client)
        self._top_k = top_k

    async def retrieve(
        self, user_id: str, query: str, top_k: int | None = None
    ) -> list[str]:
        """Relevant remembered facts for *user_id*, most-relevant first."""
        data = await self._req(
            "POST",
            "/v1/memories/search/",
            {
                "user_id": user_id,
                "query": query,
                "top_k": min(top_k or self._top_k, _MAX_TOP_K),
            },
        )
        out: list[str] = []
        for item in (data or {}).get("results", []) or []:
            if isinstance(item, dict):
                text = item.get("memory") or item.get("content") or ""
                if text:
                    out.append(text)
        return out

    async def store(self, user_id: str, content: str) -> None:
        """Persist a user turn (fact-extraction on, mem0 default)."""
        if not content.strip():
            return
        await self._req(
            "POST",
            "/v1/memories/",
            {
                "user_id": user_id,
                "messages": [{"role": "user", "content": content}],
                "metadata": {"kind": "chat"},
            },
        )
