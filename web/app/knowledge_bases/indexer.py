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
"""
Background indexer: (re)builds a knowledge base's vectors via the Memory API.

For each file we extract text (via the shared document loader), then hand the
per-document text to MemoryApiVectorStore, which chunks it and stores each chunk
verbatim in the managed store. A rebuild is a full replace of the KB's identity
(delete-all then re-add), which stays correct regardless of KB size.

Builds run one-at-a-time per knowledge base and coalesce overlapping requests, so
rapid uploads/deletes never race. Called as a fire-and-forget background task.
"""

import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlmodel import select

from app.db import DBCtx
from app.knowledge_bases import IndexStatus, KnowledgeBase, RetrievalMode
from app.knowledge_bases.memory_api_vdb import MemoryApiVectorStore

logger = logging.getLogger(__name__)

# Glob metacharacters that break the shared document loader: it copies files via
# fsspec ``file_system.get()``, which treats these as patterns, so a filename
# like "[APP-6179] Spec.docx" is read as a wildcard and "not found". Until the
# loader is fixed to copy single files literally, we stage any file whose name
# contains one of these into a temp copy with a safe name before extraction.
_GLOB_UNSAFE = re.compile(r"[\[\]\*\?]")


def _fingerprint(doc_shas: dict[str, str]) -> str:
    """Stable KB-level sha256 over the per-document (doc_id, sha) map.

    Order-independent. If this matches a KB's stored fingerprint and the KB is
    already READY, the rebuild is a no-op (nothing changed at all). The per-doc
    shas are config-aware (see MemoryApiVectorStore.doc_sha), so this changes
    when content OR chunking config changes.
    """
    h = hashlib.sha256()
    for doc_id, sha in sorted(doc_shas.items()):
        h.update(doc_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(sha.encode("ascii"))
        h.update(b"\x00")
    return h.hexdigest()


# Indexing guards (defaults; callers pass config-derived values). Protect memory
# from a single huge upload or a runaway file count.
_DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024
_DEFAULT_MAX_FILES = 200

# Ceiling on how many documents a build chunks at once. Each in-flight document
# holds its own chunk list and request bodies in memory, so this bounds peak memory
# independently of vdb_index_concurrency (a request-rate knob ops may raise).
_MAX_DOC_FAN_OUT = 8

# Per-knowledge-base build serialization. A KB can receive several uploads in
# quick succession, each scheduling a re-index; running them concurrently would
# race. We allow only one build per KB at a time and *coalesce* any requests that
# arrive while a build is running into a single follow-up build (latest files).
_kb_locks: dict[int, asyncio.Lock] = {}
_kb_pending: set[int] = set()


def _lock_for(kb_id: int) -> asyncio.Lock:
    lock = _kb_locks.get(kb_id)
    if lock is None:
        lock = asyncio.Lock()
        _kb_locks[kb_id] = lock
    return lock


class _FileRef(NamedTuple):
    id: int | None
    filename: str
    file_path: str | None
    size_bytes: int | None


class _KBSnapshot(NamedTuple):
    retrieval_mode: str
    files: list[_FileRef]
    uuid: str  # vector-store identity (collision-proof), not the integer PK


async def index_knowledge_base(
    knowledge_base: KnowledgeBase,
    db: DBCtx,
    vector_store: MemoryApiVectorStore,
    *,
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
    max_files: int = _DEFAULT_MAX_FILES,
) -> None:
    """(Re)index *knowledge_base* into the DataRobot Memory API.

    Builds run one-at-a-time per knowledge base. If a build is already in flight
    for this KB, this call is coalesced into a single follow-up build that runs
    once the current one finishes (re-reading the latest files), so rapid
    successive uploads/deletes never race.
    """
    kb_id = knowledge_base.id
    if kb_id is None:
        logger.error("index_knowledge_base: knowledge_base has no id, aborting")
        return

    lock = _lock_for(kb_id)
    if lock.locked():
        _kb_pending.add(kb_id)
        logger.info(
            "index_knowledge_base: build already running for kb_id=%s; coalescing",
            kb_id,
        )
        return

    async with lock:
        # Run the initial build plus any builds coalesced while it was running.
        # Guard each build: if one crashes (e.g. the failure handler itself errors),
        # still drain _kb_pending and run the coalesced rebuild rather than silently
        # dropping it when the lock releases.
        first = True
        while first or kb_id in _kb_pending:
            if not first:
                logger.info(
                    "index_knowledge_base: running coalesced rebuild for kb_id=%s",
                    kb_id,
                )
            first = False
            _kb_pending.discard(kb_id)
            try:
                await _build_once(kb_id, db, vector_store, max_file_bytes, max_files)
            except Exception:
                logger.exception(
                    "index_knowledge_base: build crashed for kb_id=%s", kb_id
                )


async def _extract_pages(ref: "_FileRef") -> dict[int, str] | None:
    """Extract page text for a file, working around the loader's glob bug.

    The shared document loader copies files with fsspec ``get()``, which treats
    ``[ ] * ?`` in a path as a glob pattern, so a file like "[APP-6179] Spec.docx"
    fails with FileNotFoundError. When a filename contains such a character, stage
    it into a temp copy with a sanitized name and extract from that instead. Names
    without those characters take the original path unchanged (no extra copy).
    """
    # Imported here to avoid any import cycle at module load.
    from app.files.contents import get_or_create_encoded_content
    from app.files.models import File

    src = ref.file_path
    if not src:
        return None

    load_path = src
    tmpdir: str | None = None
    if _GLOB_UNSAFE.search(os.path.basename(src)):
        tmpdir = tempfile.mkdtemp(prefix="kbindex-")
        load_path = os.path.join(tmpdir, _GLOB_UNSAFE.sub("_", os.path.basename(src)))
        shutil.copyfile(src, load_path)
    try:
        # Transient File (not session-bound) — the loader only needs file_path.
        tmp_file = File(
            filename=ref.filename, source="local", file_path=load_path, owner_id=0
        )
        return await get_or_create_encoded_content(tmp_file)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


async def _build_once(
    kb_id: int,
    db: DBCtx,
    vector_store: MemoryApiVectorStore,
    max_file_bytes: int,
    max_files: int,
) -> None:
    """Re-index a KB from its CURRENT database state.

    1. Re-reads the KB's files from the DB.
    2. Sets index_status -> INDEXING.
    3. Extracts text per file (skipping oversized files, capping count).
    4. Full-replaces this KB's chunks in the Memory API (delete-all then re-add).
    5. Sets index_status -> READY (or FAILED). If the KB is now empty, removes
       its vectors so retrieval can't serve deleted documents.
    """

    snapshot = await _load_snapshot(db, kb_id)
    if snapshot is None:
        logger.error("index_knowledge_base: kb_id=%s no longer exists; aborting", kb_id)
        return

    # Keyword-mode KBs are not indexed (they use the original full-content path).
    # Any existing vectors are left untouched so switching back to semantic is
    # instant.
    if snapshot.retrieval_mode != RetrievalMode.SEMANTIC:
        logger.info(
            "index_knowledge_base: kb_id=%s is in keyword mode; skipping index", kb_id
        )
        return

    # Capture the prior fingerprint + READY state BEFORE flipping to INDEXING,
    # so the no-op-rebuild check below can compare against the last good build.
    async with db.session() as sess:
        prior = (
            await sess.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        ).first()
        prior_fingerprint = prior.index_fingerprint if prior else None
        prior_ready = prior is not None and prior.index_status == IndexStatus.READY
        prior_shas: dict[str, str] = dict(prior.index_doc_shas) if prior else {}

    await _set_status(kb_id, IndexStatus.INDEXING, db)

    try:
        documents: list[tuple[str, str, str | None]] = []
        # Track files the build skips so we can surface them: a build that lands
        # READY while silently dropping files makes chat give confidently
        # incomplete answers (it strips full content once chunks come back), so
        # the status must not claim a completeness the build did not reach.
        skipped_count = 0
        skipped_notes: list[str] = []
        for idx, ref in enumerate(snapshot.files):
            if not ref.file_path:
                continue
            if len(documents) >= max_files:
                remaining = sum(1 for r in snapshot.files[idx:] if r.file_path)
                logger.warning(
                    "index_knowledge_base: kb_id=%s hit max_files=%d; "
                    "%d remaining file(s) not indexed",
                    kb_id,
                    max_files,
                    remaining,
                )
                skipped_count += remaining
                skipped_notes.append(
                    f"{remaining} over the max_files={max_files} limit"
                )
                break
            if ref.size_bytes and ref.size_bytes > max_file_bytes:
                logger.warning(
                    "index_knowledge_base: kb_id=%s skipping oversized file_id=%s "
                    "(%d bytes > %d limit)",
                    kb_id,
                    ref.id,
                    ref.size_bytes,
                    max_file_bytes,
                )
                skipped_count += 1
                skipped_notes.append(
                    f"{ref.filename} (exceeds {max_file_bytes // (1024 * 1024)} MB)"
                )
                continue
            try:
                pages = await _extract_pages(ref)
            except Exception:
                logger.warning(
                    "index_knowledge_base: could not extract text from file_id=%s, "
                    "skipping",
                    ref.id,
                )
                skipped_count += 1
                skipped_notes.append(f"{ref.filename} (extraction failed)")
                continue
            if not pages:
                skipped_count += 1
                skipped_notes.append(f"{ref.filename} (no extractable text)")
                continue
            content = "\n\n".join(pages[k] for k in sorted(pages)).strip()
            if not content:
                skipped_count += 1
                skipped_notes.append(f"{ref.filename} (empty)")
                continue
            documents.append((str(ref.id), content, ref.filename))

        # Surface skipped files (oversized / over max_files / extraction failed /
        # empty) so NO terminal status overstates completeness. Computed once here,
        # before every exit below, because all of them need it: the nothing-indexable
        # path (a KB whose every file was skipped must say why, not report a bare
        # NOT_INDEXED), the no-op fast skip (skipped files don't contribute to
        # current_shas, so the fingerprint can match even when a newly-added file was
        # skipped), and the normal READY path. Truncated to the column width, like
        # the FAILED path's str(exc)[:2000].
        partial_note = (
            (f"{skipped_count} file(s) not indexed: " + "; ".join(skipped_notes[:10]))[
                :2000
            ]
            if skipped_count
            else None
        )

        if not documents:
            # Nothing to index (no files, or none yielded text). Remove any
            # existing vectors so chat/search can't serve removed documents.
            await vector_store.delete_kb(snapshot.uuid)
            await _set_status(
                kb_id,
                IndexStatus.NOT_INDEXED,
                db,
                set_last_error=True,
                last_error=partial_note,
                set_fingerprint=True,
                fingerprint=None,
                doc_shas={},
            )
            logger.info(
                "index_knowledge_base: kb_id=%s has no indexable text (%d skipped)",
                kb_id,
                skipped_count,
            )
            return

        # Per-document content hashes (config-aware) + KB-level fingerprint.
        current_shas = {
            did: vector_store.doc_sha(content) for did, content, _ in documents
        }
        content_by_id = {did: (content, source) for did, content, source in documents}
        fingerprint = _fingerprint(current_shas)

        # KB-level fast skip: nothing changed at all since the last good build.
        if prior_ready and prior_fingerprint == fingerprint:
            await _set_status(
                kb_id,
                IndexStatus.READY,
                db,
                set_last_error=True,
                last_error=partial_note,
                set_fingerprint=True,
                fingerprint=fingerprint,
                doc_shas=current_shas,
            )  # restore READY (we flipped to INDEXING above); refresh indexed_at
            logger.info(
                "index_knowledge_base: kb_id=%s unchanged (fingerprint match); "
                "skipping re-embed",
                kb_id,
            )
            return

        # Incremental, non-destructive diff. Only changed/new/removed documents
        # are touched; the KB is never fully wiped, so retrieval stays valid.
        current_ids = set(current_shas)
        removed = set(prior_shas) - current_ids
        changed = {
            did for did in current_ids if prior_shas.get(did) != current_shas[did]
        }
        # Cold start (empty prior sha map): first index, a post-upgrade re-index
        # (the migration seeds {}), or a rebuild after a cleared failure. Per-doc
        # deletes filter by run_id and cannot clear chunks written by the old code
        # (which had no run_id), so wipe the whole KB identity once before re-adding
        # to avoid orphaned/duplicate chunks. Retrieval is gated on READY, so this
        # brief window is not user-visible.
        cold_start = not prior_shas and bool(current_ids)
        if cold_start:
            await vector_store.delete_kb(snapshot.uuid)
        for did in removed:
            await vector_store.delete_document(snapshot.uuid, did)

        # Bound how many documents are in flight. Documents are synced concurrently
        # because each is dominated by HTTP round-trip latency, so awaiting them in
        # sequence serializes the whole build (a cold start, where every doc is
        # "changed", would be one round-trip at a time). But an unbounded fan-out over
        # up to max_files documents would hold every document's chunk list and request
        # bodies in memory at once: add_document chunks synchronously before its first
        # await, so each started task materializes its text again. Cap the fan-out at
        # the store's write budget, which is exactly enough to keep the request
        # pipeline full while keeping peak memory to a few documents. Also capped by
        # _MAX_DOC_FAN_OUT so raising vdb_index_concurrency (a request-rate knob) can
        # never turn into an unbounded memory commitment.
        doc_sem = asyncio.Semaphore(
            max(1, min(vector_store.write_concurrency, _MAX_DOC_FAN_OUT))
        )

        async def _sync(did: str) -> int:
            async with doc_sem:
                # delete-then-add per doc (no-op delete for brand-new docs). Skipped
                # after a cold-start wipe: the identity is already empty, so these
                # would be N redundant round-trips (200-doc KB = 200 wasted DELETEs).
                if not cold_start:
                    await vector_store.delete_document(snapshot.uuid, did)
                content, source = content_by_id[did]
                return await vector_store.add_document(
                    snapshot.uuid, did, content, source
                )

        # Every mutating request also passes the store's shared write semaphore, so
        # total in-flight writes stay within vdb_index_concurrency regardless of how
        # many documents run here. Ordering within a document (delete before add) is
        # preserved inside _sync. Settle every doc before propagating a failure, for
        # the same reason add_document does: a raised error must not leave sibling
        # writers running into the next build's index.
        synced = await asyncio.gather(
            *(_sync(did) for did in changed), return_exceptions=True
        )
        errors = [r for r in synced if isinstance(r, BaseException)]
        if errors:
            raise errors[0]
        count = sum(r for r in synced if isinstance(r, int))

        await _set_status(
            kb_id,
            IndexStatus.READY,
            db,
            set_last_error=True,
            last_error=partial_note,
            set_fingerprint=True,
            fingerprint=fingerprint,
            doc_shas=current_shas,
        )
        logger.info(
            "index_knowledge_base: kb_id=%s synced - %d changed/new doc(s) "
            "(%d chunk(s)), %d removed, %d unchanged, %d skipped",
            kb_id,
            len(changed),
            count,
            len(removed),
            len(current_ids) - len(changed),
            skipped_count,
        )
    except Exception as exc:
        logger.exception("index_knowledge_base failed for kb_id=%s", kb_id)
        # A partial failure may have deleted/added only some documents, so the
        # prior sha map no longer reflects what is actually in the store. Clear it
        # (and the fingerprint) so the next rebuild treats every document as new
        # and re-adds it, rather than diffing against a stale map and leaving
        # partially-applied documents missing.
        await _set_status(
            kb_id,
            IndexStatus.FAILED,
            db,
            set_last_error=True,
            last_error=str(exc)[:2000],
            set_fingerprint=True,
            fingerprint=None,
            doc_shas={},
        )


async def reset_stuck_indexing(db: DBCtx, stuck_minutes: int = 30) -> int:
    """Reset knowledge bases left in 'indexing' by a crashed/restarted process.

    Indexing runs as an in-process background task, so a deploy or crash mid-build
    would otherwise leave a KB stuck in 'indexing' forever. Called once at startup;
    flips such KBs to 'failed' with an actionable message so users can retry.
    Returns the number reset.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    count = 0
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(
                KnowledgeBase.index_status == IndexStatus.INDEXING
            )
        )
        # .unique() is required because KnowledgeBase joined-eager-loads `files`.
        for kb in result.unique().all():
            updated = kb.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated is None or updated < cutoff:
                kb.index_status = IndexStatus.FAILED
                kb.last_error = (
                    "Indexing was interrupted (service restart). Please retry."
                )
                # A crash mid-build may have partially applied chunks, so the sha
                # map no longer reflects the store. Clear it (and the fingerprint),
                # exactly as the _build_once failure handler does, so the next
                # rebuild re-adds every document instead of diffing against a stale
                # map and leaving partially-applied content behind.
                kb.index_doc_shas = {}
                kb.index_fingerprint = None
                kb.updated_at = datetime.now(timezone.utc)
                count += 1
        await session.commit()
    if count:
        logger.warning(
            "reset_stuck_indexing: reset %d stuck knowledge base(s) to failed", count
        )
    return count


async def _load_snapshot(db: DBCtx, kb_id: int) -> _KBSnapshot | None:
    """Read the KB's current files from the database."""
    async with db.session() as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.first()
        if kb is None:
            return None
        files = [
            _FileRef(
                id=f.id,
                filename=f.filename,
                file_path=f.file_path,
                size_bytes=f.size_bytes,
            )
            for f in kb.files
        ]
        return _KBSnapshot(
            retrieval_mode=kb.retrieval_mode, files=files, uuid=str(kb.uuid)
        )


async def _set_status(
    kb_id: int,
    status: IndexStatus,
    db: DBCtx,
    *,
    set_last_error: bool = False,
    last_error: str | None = None,
    set_fingerprint: bool = False,
    fingerprint: str | None = None,
    doc_shas: dict[str, str] | None = None,
) -> None:
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.first()
        if kb:
            kb.index_status = status
            if set_last_error:
                kb.last_error = last_error
            if set_fingerprint:
                # None is a valid value here (clear to NULL when emptying a KB),
                # so gate on an explicit flag rather than on fingerprint is None.
                kb.index_fingerprint = fingerprint
            if doc_shas is not None:
                kb.index_doc_shas = doc_shas
            if status == IndexStatus.READY:
                kb.indexed_at = datetime.now(timezone.utc)
            kb.updated_at = datetime.now(timezone.utc)
            await session.commit()
