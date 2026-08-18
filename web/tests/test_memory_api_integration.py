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
"""Live integration test against the DataRobot Memory API on staging.

Skipped unless RUN_MEMORY_INTEGRATION=1. Requires VPN + DATAROBOT_ENDPOINT +
DATAROBOT_API_TOKEN. Self-contained: creates its own memory space, exercises the
real MemoryApiVectorStore (index -> retrieve -> incremental update -> per-doc delete), and deletes
the space in teardown.
"""

import os

import httpx
import pytest

# Captured at import time: the web test suite has an autouse fixture that resets
# os.environ per test, so read the creds here (collection time) before it runs.
_RUN = os.getenv("RUN_MEMORY_INTEGRATION") == "1"
_ENDPOINT = os.getenv("DATAROBOT_ENDPOINT", "").rstrip("/")
_TOKEN = os.getenv("DATAROBOT_API_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not (_RUN and _ENDPOINT and _TOKEN),
    reason="staging integration; needs RUN_MEMORY_INTEGRATION=1 + VPN + DATAROBOT creds",
)


def _root_and_base() -> tuple[str, str, str]:
    root = _ENDPOINT[:-7] if _ENDPOINT.endswith("/api/v2") else _ENDPOINT
    base = f"{root}/api-gw/agentic-memory-api"
    return root, base, _TOKEN


async def test_index_retrieve_incremental_roundtrip() -> None:
    from app.knowledge_bases.memory_api_vdb import MemoryApiVectorStore

    _root, base, token = _root_and_base()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(headers=headers, timeout=60) as raw:
        created = await raw.post(
            f"{base}/new/",
            json={
                "description": "ttmdocs-itest",
                "llm_model_name": "azure/gpt-4o-mini",
            },
        )
        created.raise_for_status()
        space_id = created.json()["memorySpaceId"]

        store = MemoryApiVectorStore(base_url=base, space_id=space_id, token=token)
        kb = 4242
        try:
            # Incremental add of two documents (per-doc run_id scoping).
            await store.add_document(
                kb, "d1", "Q3 revenue was $4.2M, up 18% from Q2.", "q3.txt"
            )
            await store.add_document(
                kb, "d2", "Onboarding requires manager approval.", "hr.txt"
            )

            hits = await store.retrieve(kb, "how much did we make in Q3?", top_k=2)
            assert hits, "expected retrieval hits"
            assert "4.2M" in hits[0]["text"], f"top hit was {hits[0]['text']!r}"

            # Incremental update of ONE doc (delete-then-add just that doc): the
            # other doc's chunks are untouched, and there are no duplicates.
            await store.delete_document(kb, "d1")
            await store.add_document(
                kb, "d1", "Q3 revenue was $4.2M, up 18% from Q2.", "q3.txt"
            )
            hits2 = await store.retrieve(kb, "how much did we make in Q3?", top_k=5)
            assert sum("4.2M" in h["text"] for h in hits2) == 1, "no duplicate chunks"
            # d2 still retrievable (never wiped) -> non-destructive update.
            hits3 = await store.retrieve(kb, "onboarding approval", top_k=5)
            assert any("approval" in h["text"].lower() for h in hits3), "d2 survived"

            # Per-doc delete removes only that doc.
            await store.delete_document(kb, "d1")
            after = await store.retrieve(kb, "Q3 revenue", top_k=5)
            assert not any("4.2M" in h["text"] for h in after), "d1 deleted"

            await store.delete_kb(kb)
            gone = await store.retrieve(kb, "revenue", top_k=2)
            assert gone == []
        finally:
            await store.dispose()
            async with httpx.AsyncClient(headers=headers, timeout=60) as cleanup:
                await cleanup.delete(f"{base}/{space_id}/")
