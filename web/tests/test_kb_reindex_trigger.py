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
"""Tests for _schedule_kb_reindex — the upload-path indexing trigger."""

import uuid as uuidpkg
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.files import _schedule_kb_reindex


def _make_request(vector_store: object, kb: object) -> MagicMock:
    request = MagicMock()
    deps = request.app.state.deps
    deps.vector_store = vector_store
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(return_value=kb)
    deps.db = MagicMock()
    return request


async def test_noop_when_no_kb_uuid() -> None:
    request = _make_request(MagicMock(), MagicMock())
    with patch("app.api.v1.files.asyncio.create_task") as create_task:
        await _schedule_kb_reindex(request, None, MagicMock())
    create_task.assert_not_called()


async def test_noop_when_no_vdb_service() -> None:
    request = _make_request(None, MagicMock())
    with patch("app.api.v1.files.asyncio.create_task") as create_task:
        await _schedule_kb_reindex(request, uuidpkg.uuid4(), MagicMock())
    create_task.assert_not_called()


async def test_noop_when_kb_not_found() -> None:
    request = _make_request(MagicMock(), None)
    with patch("app.api.v1.files.asyncio.create_task") as create_task:
        await _schedule_kb_reindex(request, uuidpkg.uuid4(), MagicMock())
    create_task.assert_not_called()


async def test_schedules_index_when_configured() -> None:
    fake_kb = MagicMock()
    request = _make_request(MagicMock(), fake_kb)
    with (
        patch("app.api.v1.files.index_knowledge_base") as index_kb,
        patch("app.api.v1.files.asyncio.create_task") as create_task,
    ):
        index_kb.return_value = MagicMock()
        await _schedule_kb_reindex(request, uuidpkg.uuid4(), MagicMock())
    index_kb.assert_called_once()
    create_task.assert_called_once()


# --- update_file must also rebuild the KB a file was moved away from ---


async def _call_update_file(previous_kb_uuid, body):  # type: ignore[no-untyped-def]
    """Drive update_file with mocked repos.

    *body* is the raw request payload, so a key can be OMITTED (not just set to
    None) — the distinction the endpoint relies on. Returns the reindexed KB uuids
    and the FileUpdate fields actually handed to the repository.
    """
    from app.api.v1.files import FileUpdateRequestSchema, update_file

    file = MagicMock(id=5)
    file.knowledgebase = (
        MagicMock(uuid=previous_kb_uuid) if previous_kb_uuid is not None else None
    )

    request = MagicMock()
    deps = request.app.state.deps
    deps.file_repo.get_file = AsyncMock(return_value=file)
    deps.file_repo.update_file = AsyncMock(return_value=MagicMock())
    deps.user_repo.get_user = AsyncMock(return_value=MagicMock(id=1))
    deps.knowledge_base_repo.get_knowledge_base = AsyncMock(
        return_value=MagicMock(id=9, owner_id=1)
    )

    auth_ctx = MagicMock()
    auth_ctx.user.id = 1
    payload = FileUpdateRequestSchema.model_validate(body)

    with (
        patch("app.api.v1.files._schedule_kb_reindex", new=AsyncMock()) as sched,
        patch("app.api.v1.files.FileSchema.from_file", return_value=MagicMock()),
    ):
        await update_file(request, uuidpkg.uuid4(), payload, auth_ctx)

    reindexed = [call.args[1] for call in sched.await_args_list]
    applied = deps.file_repo.update_file.await_args.args[1].model_dump(
        exclude_unset=True
    )
    return reindexed, applied


async def test_update_file_reindexes_both_kbs_when_file_moves() -> None:
    """Moving a file to another KB must rebuild the old KB too, or its chunks for
    that file keep being served by semantic search."""
    old, new = uuidpkg.uuid4(), uuidpkg.uuid4()
    reindexed, _ = await _call_update_file(
        old, {"filename": "f.txt", "knowledge_base_uuid": new}
    )
    assert new in reindexed and old in reindexed


async def test_update_file_reindexes_old_kb_when_file_detached() -> None:
    """Explicitly detaching a file (knowledge_base_uuid=None) rebuilds the old KB."""
    old = uuidpkg.uuid4()
    reindexed, applied = await _call_update_file(
        old, {"filename": "f.txt", "knowledge_base_uuid": None}
    )
    assert old in reindexed
    assert applied["knowledge_base_id"] is None  # detach still applied


async def test_update_file_reindexes_once_when_kb_unchanged() -> None:
    """Staying in the same KB must not schedule a duplicate rebuild."""
    same = uuidpkg.uuid4()
    reindexed, _ = await _call_update_file(
        same, {"filename": "f.txt", "knowledge_base_uuid": same}
    )
    assert reindexed == [same]


async def test_update_file_rename_keeps_kb_attachment_and_index() -> None:
    """A filename-only update must not detach the file or rebuild anything.

    knowledge_base_uuid is absent from the payload, so knowledge_base_id must be
    left out of the update entirely: writing None would silently pull the file out
    of its KB and the follow-up re-index would drop its chunks.
    """
    old = uuidpkg.uuid4()
    reindexed, applied = await _call_update_file(old, {"filename": "renamed.txt"})
    assert reindexed == []  # nothing re-indexed on a pure rename
    assert applied == {"filename": "renamed.txt"}  # attachment untouched
