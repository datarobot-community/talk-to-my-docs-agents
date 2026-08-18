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
"""Tests for the pgvector knowledge-base indexer (vector store + loader mocked)."""

import asyncio
import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import SQLModel, select

from app.db import DBCtx, create_db_ctx
from app.files.models import File
from app.knowledge_bases import IndexStatus, KnowledgeBase
from app.knowledge_bases.indexer import index_knowledge_base

MOD = "app.knowledge_bases.indexer"
# get_or_create_encoded_content is imported inside _build_once from this module:
LOADER = "app.files.contents.get_or_create_encoded_content"


@pytest.fixture
async def db() -> DBCtx:
    ctx = await create_db_ctx("sqlite+aiosqlite:///:memory:")
    async with ctx.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return ctx


async def _seed_kb(db: DBCtx, *, with_file: bool = True) -> KnowledgeBase:
    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        if with_file:
            session.add(
                File(
                    filename="policy.txt",
                    source="local",
                    file_path="/storage/policy.txt",
                    owner_id=1,
                    knowledge_base_id=kb.id,
                )
            )
        await session.commit()
        await session.refresh(kb)
    async with db.session() as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        loaded = result.first()
        assert loaded is not None
        _ = loaded.files
        return loaded


async def _status(db: DBCtx, kb_id: int) -> tuple[str, str | None]:
    async with db.session() as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.first()
        assert kb is not None
        return kb.index_status, kb.last_error


def _store() -> MagicMock:
    store = MagicMock()
    # Real content-hash so the indexer's per-doc diff detects changes correctly.
    store.doc_sha = MagicMock(
        side_effect=lambda content: hashlib.sha256(content.encode()).hexdigest()
    )
    store.add_document = AsyncMock(return_value=3)
    store.delete_document = AsyncMock()
    store.delete_kb = AsyncMock()
    # Real int: the indexer sizes its document fan-out from the store's write budget.
    store.write_concurrency = 6
    return store


async def test_indexer_indexes_and_sets_ready(db: DBCtx) -> None:
    kb = await _seed_kb(db)
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "refund policy text"})):
        await index_knowledge_base(kb, db, store)

    store.add_document.assert_awaited_once()
    identity_arg, doc_id, content, source = store.add_document.call_args.args
    assert identity_arg == str(kb.uuid)  # vector-store identity is the KB uuid
    assert content == "refund policy text"  # extracted text passed through
    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY
    assert last_error is None


async def test_indexer_sets_failed_and_records_error(db: DBCtx) -> None:
    kb = await _seed_kb(db)
    store = _store()
    store.add_document = AsyncMock(side_effect=RuntimeError("kaboom"))
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store)

    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.FAILED
    assert last_error is not None and "kaboom" in last_error


async def test_indexer_failure_clears_doc_shas_for_clean_rebuild(db: DBCtx) -> None:
    """A partial failure clears index_doc_shas/fingerprint so the next rebuild
    re-adds every document instead of diffing against a now-inaccurate map (which
    could leave partially-applied documents missing while marked READY)."""
    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        row.index_status = IndexStatus.READY  # a prior successful build
        row.index_fingerprint = "prior-fp"
        row.index_doc_shas = {"1": "prior-sha"}
        await session.commit()

    store = _store()
    store.add_document = AsyncMock(side_effect=RuntimeError("add failed midway"))
    with patch(LOADER, new=AsyncMock(return_value={1: "new text"})):
        await index_knowledge_base(kb, db, store)

    async with db.session() as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        assert row.index_status == IndexStatus.FAILED
        assert row.index_doc_shas == {}  # cleared -> next rebuild re-adds all
        assert row.index_fingerprint is None


async def test_indexer_empty_kb_deletes_vectors_and_not_indexed(db: DBCtx) -> None:
    """No extractable text -> remove vectors + NOT_INDEXED (no stale retrieval)."""
    kb = await _seed_kb(db)
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value=None)):  # loader yields nothing
        await index_knowledge_base(kb, db, store)

    store.add_document.assert_not_awaited()
    store.delete_kb.assert_awaited_once_with(str(kb.uuid))
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.NOT_INDEXED


async def test_indexer_ready_records_skipped_files(db: DBCtx) -> None:
    """A build that indexes some files but skips others lands READY with the
    skipped files named in last_error, so the status does not overstate that the
    index is complete."""
    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        session.add(
            File(
                filename="good.txt",
                source="local",
                file_path="/storage/good.txt",
                owner_id=1,
                knowledge_base_id=kb.id,
            )
        )
        big = File(
            filename="big.txt",
            source="local",
            file_path="/storage/big.txt",
            owner_id=1,
            knowledge_base_id=kb.id,
        )
        big.size_bytes = 999_999
        session.add(big)
        await session.commit()
        await session.refresh(kb)
        _ = kb.files

    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store, max_file_bytes=10)

    store.add_document.assert_awaited_once()  # the good file was indexed
    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY
    assert last_error is not None
    assert "not indexed" in last_error and "big.txt" in last_error


async def test_indexer_fast_skip_still_records_skipped_files(db: DBCtx) -> None:
    """A no-op rebuild (fingerprint match) that skipped a newly-added oversized
    file must still surface it — skipped files don't change the fingerprint, so the
    fast-skip path must not report a completeness the build did not reach."""
    from app.knowledge_bases.indexer import _fingerprint

    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        good = File(
            filename="good.txt",
            source="local",
            file_path="/storage/good.txt",
            owner_id=1,
            knowledge_base_id=kb.id,
        )
        session.add(good)
        await session.flush()
        big = File(
            filename="big.txt",
            source="local",
            file_path="/storage/big.txt",
            owner_id=1,
            knowledge_base_id=kb.id,
        )
        big.size_bytes = 999_999
        session.add(big)
        # Prior successful build indexed only good.txt; its sha matches what the
        # loader will produce this run, so the fingerprint is unchanged.
        good_sha = hashlib.sha256("text".encode()).hexdigest()
        kb.index_status = IndexStatus.READY
        kb.index_doc_shas = {str(good.id): good_sha}
        kb.index_fingerprint = _fingerprint({str(good.id): good_sha})
        await session.commit()
        await session.refresh(kb)
        _ = kb.files

    store = _store()  # doc_sha = sha256(content)
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store, max_file_bytes=10)

    store.add_document.assert_not_awaited()  # fingerprint match -> no re-embed
    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY
    assert last_error is not None and "big.txt" in last_error


async def test_indexer_empty_kb_clears_stale_fingerprint(db: DBCtx) -> None:
    """Emptying a previously-indexed KB clears index_fingerprint to NULL. None is a
    real 'clear' value here, so it must not be treated as 'leave unchanged'."""
    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        row.index_fingerprint = "stale-fp"
        row.index_status = IndexStatus.READY
        await session.commit()

    store = _store()
    with patch(LOADER, new=AsyncMock(return_value=None)):  # loader yields nothing
        await index_knowledge_base(kb, db, store)

    async with db.session() as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        assert row.index_status == IndexStatus.NOT_INDEXED
        assert row.index_fingerprint is None  # stale fingerprint was cleared


async def test_indexer_upgrade_wipes_orphaned_chunks(db: DBCtx) -> None:
    """A post-upgrade re-index (previously READY, empty doc_shas from the migration)
    wipes the KB identity once so old run_id-less chunks are cleared instead of
    left as permanent duplicates, then re-adds all documents."""
    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        row = (
            await session.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb.id))
        ).first()
        assert row is not None
        row.index_status = IndexStatus.READY  # indexed by the old (pre-run_id) code
        row.index_doc_shas = {}  # migration default: no per-doc map yet
        await session.commit()

    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store)

    store.delete_kb.assert_awaited_once_with(str(kb.uuid))  # orphaned chunks wiped
    store.add_document.assert_awaited()  # documents re-added (now with run_id)
    # The whole-identity wipe already emptied the KB, so no per-doc DELETE is sent.
    store.delete_document.assert_not_awaited()
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY


async def test_indexer_skips_oversized_file(db: DBCtx) -> None:
    kb = await _seed_kb(db)
    # Mark the file oversized.
    async with db.session(writable=True) as session:
        result = await session.exec(select(File).where(File.knowledge_base_id == kb.id))
        f = result.first()
        assert f is not None
        f.size_bytes = 999_999
        await session.commit()
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store, max_file_bytes=10)

    store.add_document.assert_not_awaited()
    store.delete_kb.assert_awaited_once()  # no docs -> empty path
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.NOT_INDEXED


async def test_indexer_not_indexed_records_skipped_files(db: DBCtx) -> None:
    """When every file is skipped, NOT_INDEXED must still say why.

    A bare NOT_INDEXED with last_error=None reads as "empty knowledge base" when the
    build actually ran and skipped every file for a known reason.
    """
    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        result = await session.exec(select(File).where(File.knowledge_base_id == kb.id))
        f = result.first()
        assert f is not None
        f.size_bytes = 999_999  # oversized -> skipped, so documents ends up empty
        await session.commit()

    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store, max_file_bytes=10)

    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.NOT_INDEXED
    assert last_error is not None
    assert "not indexed" in last_error and "policy.txt" in last_error


async def test_indexer_stages_glob_unsafe_filenames(db: DBCtx, tmp_path: Any) -> None:
    """A file whose name has glob metacharacters (e.g. [APP-6179]) is staged to a
    sanitized temp copy before extraction, so the loader's glob-based read works."""
    # Real source file on disk with a bracketed name.
    src = tmp_path / "[APP-6179] Spec.docx"
    src.write_text("dummy content")
    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        session.add(
            File(
                filename="[APP-6179] Spec.docx",
                source="local",
                file_path=str(src),
                owner_id=1,
                knowledge_base_id=kb.id,
            )
        )
        await session.commit()
        await session.refresh(kb)
        _ = kb.files

    store = _store()
    loader = AsyncMock(return_value={1: "extracted text"})
    with patch(LOADER, new=loader):
        await index_knowledge_base(kb, db, store)  # type: ignore[arg-type]

    # The loader was handed a sanitized, glob-free path (a temp copy), not the
    # bracketed original, and indexing succeeded.
    seen_path = loader.await_args.args[0].file_path
    assert not any(ch in seen_path for ch in "[]*?")
    assert seen_path != str(src)
    store.add_document.assert_awaited_once()
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY


async def test_indexer_skips_when_fingerprint_unchanged(db: DBCtx) -> None:
    kb = await _seed_kb(db)
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "same text"})):
        await index_knowledge_base(kb, db, store)  # first build embeds
    assert store.add_document.await_count == 1

    async with db.session() as s:
        kb2 = (
            await s.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb.id))
        ).first()
        assert kb2 is not None
        _ = kb2.files
    with patch(LOADER, new=AsyncMock(return_value={1: "same text"})):
        await index_knowledge_base(kb2, db, store)  # unchanged -> skipped
    assert store.add_document.await_count == 1
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY


async def test_indexer_rebuilds_when_content_changes(db: DBCtx) -> None:
    kb = await _seed_kb(db)
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "v1"})):
        await index_knowledge_base(kb, db, store)
    async with db.session() as s:
        kb2 = (
            await s.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb.id))
        ).first()
        assert kb2 is not None
        _ = kb2.files
    with patch(LOADER, new=AsyncMock(return_value={1: "v2 changed"})):
        await index_knowledge_base(kb2, db, store)  # changed -> re-embed
    assert store.add_document.await_count == 2


async def _seed_kb_files(
    db: DBCtx, names: list[str]
) -> tuple[KnowledgeBase, dict[str, str]]:
    """Seed a semantic KB with several files; return (kb, {name: doc_id})."""
    ids: dict[str, str] = {}
    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        for name in names:
            f = File(
                filename=name,
                source="local",
                file_path=f"/storage/{name}",
                owner_id=1,
                knowledge_base_id=kb.id,
            )
            session.add(f)
            await session.flush()
            ids[name] = str(f.id)
        await session.commit()
    async with db.session() as session:
        kb2 = (
            await session.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb.id))
        ).first()
        assert kb2 is not None
        _ = kb2.files
        return kb2, ids


async def _reload_kb(db: DBCtx, kb_id: int) -> KnowledgeBase:
    async with db.session() as session:
        kb = (
            await session.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        ).first()
        assert kb is not None
        _ = kb.files
        return kb


async def test_indexer_incremental_only_touches_changed_docs(db: DBCtx) -> None:
    """Changed docs re-embed, removed docs delete, unchanged untouched, no KB wipe."""
    kb, ids = await _seed_kb_files(db, ["a.txt", "b.txt", "c.txt"])
    contents = {"/storage/a.txt": "A1", "/storage/b.txt": "B1", "/storage/c.txt": "C1"}

    async def loader(file: Any, *a: Any, **k: Any) -> dict[int, str]:
        return {1: contents[file.file_path]}

    store = _store()
    with patch(LOADER, new=AsyncMock(side_effect=loader)):
        await index_knowledge_base(kb, db, store)
    assert store.add_document.await_count == 3  # first build: all three new

    store.add_document.reset_mock()
    store.delete_document.reset_mock()
    store.delete_kb.reset_mock()

    # Change b, remove c (delete its file row), leave a untouched.
    contents["/storage/b.txt"] = "B2"
    async with db.session(writable=True) as session:
        f = (
            await session.exec(select(File).where(File.id == int(ids["c.txt"])))
        ).first()
        assert f is not None
        await session.delete(f)
        await session.commit()

    kb2 = await _reload_kb(db, kb.id)  # type: ignore[arg-type]
    with patch(LOADER, new=AsyncMock(side_effect=loader)):
        await index_knowledge_base(kb2, db, store)

    added = {c.args[1] for c in store.add_document.await_args_list}
    deleted = {c.args[1] for c in store.delete_document.await_args_list}
    assert added == {ids["b.txt"]}  # only the changed doc re-embedded
    assert ids["c.txt"] in deleted  # removed doc deleted
    assert ids["a.txt"] not in added  # unchanged doc untouched
    store.delete_kb.assert_not_awaited()  # non-destructive: KB never wiped
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY


async def test_indexer_coalesces_concurrent_rebuilds(db: DBCtx) -> None:
    from app.knowledge_bases import indexer as indexer_mod

    indexer_mod._kb_locks.clear()
    indexer_mod._kb_pending.clear()

    kb = await _seed_kb(db)
    release = asyncio.Event()
    calls = 0

    async def _index(*_: Any, **__: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            await release.wait()
        return 1

    store = _store()
    store.add_document = AsyncMock(side_effect=_index)

    # Distinct content per read so the coalesced rebuild has a different
    # fingerprint and actually re-embeds (otherwise the no-op-rebuild skip would
    # correctly short-circuit it, which this test is not exercising).
    _texts = iter([{1: "text v1"}, {1: "text v2"}, {1: "text v3"}])

    async def _loader(*_: Any, **__: Any) -> dict[int, str]:
        return next(_texts)

    with patch(LOADER, new=AsyncMock(side_effect=_loader)):
        first = asyncio.create_task(index_knowledge_base(kb, db, store))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(index_knowledge_base(kb, db, store))
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.gather(first, second)

    assert calls == 2  # in-flight build + one coalesced rebuild


async def test_indexer_drains_pending_even_if_build_crashes(
    db: DBCtx, monkeypatch: Any
) -> None:
    """A build crashing (e.g. the failure handler itself erroring) must not leave a
    coalesced request stuck in _kb_pending; the loop still drains and reruns it."""
    from app.knowledge_bases import indexer as indexer_mod

    indexer_mod._kb_locks.clear()
    indexer_mod._kb_pending.clear()
    kb = await _seed_kb(db)
    calls = 0

    async def _boom(kb_id: int, *_: Any, **__: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            indexer_mod._kb_pending.add(kb_id)  # a request arrived mid-build
            raise RuntimeError("build crashed hard")

    monkeypatch.setattr(indexer_mod, "_build_once", _boom)
    # Must not raise, must run the coalesced rebuild, must drain pending.
    await index_knowledge_base(kb, db, _store())
    assert calls == 2
    assert kb.id not in indexer_mod._kb_pending


async def test_indexer_skips_keyword_mode(db: DBCtx) -> None:
    """A keyword-mode KB is never indexed (original behavior preserved)."""
    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        row.retrieval_mode = "keyword"
        await session.commit()
    store = _store()
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store)

    store.add_document.assert_not_awaited()
    store.delete_kb.assert_not_awaited()  # left untouched (instant switch-back)


async def test_reset_stuck_indexing(db: DBCtx) -> None:
    from app.knowledge_bases.indexer import reset_stuck_indexing

    kb = await _seed_kb(db)
    async with db.session(writable=True) as session:
        result = await session.exec(
            select(KnowledgeBase).where(KnowledgeBase.id == kb.id)
        )
        row = result.first()
        assert row is not None
        row.index_status = IndexStatus.INDEXING
        row.index_fingerprint = "stale-fp"  # from before the interrupted build
        row.index_doc_shas = {"1": "stale-sha"}
        await session.commit()

    n = await reset_stuck_indexing(db, stuck_minutes=0)

    assert n == 1
    async with db.session() as session:
        row = (
            await session.exec(select(KnowledgeBase).where(KnowledgeBase.id == kb.id))
        ).first()
        assert row is not None
        assert row.index_status == IndexStatus.FAILED
        # State cleared so the next rebuild re-adds everything (no stale skip).
        assert row.index_doc_shas == {}
        assert row.index_fingerprint is None


async def test_indexer_syncs_documents_concurrently(db: DBCtx) -> None:
    """Documents are synced in parallel, not one round-trip at a time.

    The old full-replace pooled every batch under one semaphore; the per-document
    rewrite must not silently serialize a cold start (where every doc is "changed").
    """
    async with db.session(writable=True) as session:
        kb = KnowledgeBase(
            title="t", description="d", path="p", owner_id=1, retrieval_mode="semantic"
        )
        session.add(kb)
        await session.flush()
        for i in range(5):
            session.add(
                File(
                    filename=f"f{i}.txt",
                    source="local",
                    file_path=f"/storage/f{i}.txt",
                    owner_id=1,
                    knowledge_base_id=kb.id,
                )
            )
        await session.commit()
        await session.refresh(kb)
        _ = kb.files

    store = _store()
    store.write_concurrency = 2  # documents in flight are bounded by this
    in_flight = 0
    peak = 0

    async def _add(*_a: object, **_k: object) -> int:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)  # yield so siblings can start
        in_flight -= 1
        return 2

    store.add_document = AsyncMock(side_effect=_add)
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store)

    assert store.add_document.await_count == 5
    assert peak > 1  # overlapped rather than strictly sequential
    # ...but bounded: an unbounded gather would run all 5 documents at once, holding
    # every document's chunks in memory. The fan-out must respect the write budget.
    assert peak <= 2
    status, _ = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.READY


async def test_indexer_document_failure_still_marks_failed(db: DBCtx) -> None:
    """A failing document surfaces as FAILED even though docs run concurrently."""
    kb = await _seed_kb(db)
    store = _store()
    store.add_document = AsyncMock(side_effect=RuntimeError("add exploded"))
    with patch(LOADER, new=AsyncMock(return_value={1: "text"})):
        await index_knowledge_base(kb, db, store)

    status, last_error = await _status(db, kb.id)  # type: ignore[arg-type]
    assert status == IndexStatus.FAILED
    assert last_error is not None and "add exploded" in last_error
