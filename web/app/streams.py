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

"""Lightweight in-memory publisher for chat Server-Sent Events.

The intent is to keep the infrastructure footprint small while we stay on a single
FastAPI/Uvicorn worker. Each chat gets a set of subscribers (per browser tab) and
we fan out message events to all of them. We keep a modest queue per subscriber so
one stalled client cannot consume unbounded memory, and we close the stream after a
fixed heartbeat window so zombie connections don't accumulate forever.

This module is intentionally simple: no external broker, no persistence, just
enough guardrails to be safe up to a few hundred concurrent listeners.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class MessageEvent:
    data: dict[str, Any]
    type: str = "message"


@dataclass
class SnapshotEvent:
    data: list[dict[str, Any]]
    type: str = "snapshot"


@dataclass
class HeartbeatEvent:
    timestamp: str
    type: str = "heartbeat"


@dataclass
class TaskProgressEvent:
    data: dict[str, Any]
    type: str = "task_progress"


StreamEvent = MessageEvent | SnapshotEvent | HeartbeatEvent | TaskProgressEvent

_HEARTBEAT_SECONDS = 25  # send a keep-alive event roughly every 25 seconds
# Cap per-subscriber queue so a stalled client cannot build up unbounded events in memory.
_QUEUE_MAXSIZE = 256
# Force a recycle roughly every 50 minutes; browsers reconnect automatically.
_MAX_HEARTBEATS = 120


@dataclass
class _Subscriber:
    queue: asyncio.Queue[StreamEvent | None]
    max_heartbeats: int
    heartbeat_count: int = 0
    should_disconnect: bool = False


class ChatStreamManager:
    """Simple per-chat pub/sub hub."""

    def __init__(self) -> None:
        self._subscribers: Dict[UUID, List[_Subscriber]] = {}
        self._total_connections = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(self, chat_uuid: UUID) -> AsyncIterator[_Subscriber]:
        async with self._lock:
            queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(
                maxsize=_QUEUE_MAXSIZE
            )
            subscriber = _Subscriber(
                queue=queue,
                max_heartbeats=_MAX_HEARTBEATS,
            )
            self._subscribers.setdefault(chat_uuid, []).append(subscriber)
            self._total_connections += 1
            logger.debug(
                "SSE subscribe chat=%s subscribers=%s total=%s",
                chat_uuid,
                len(self._subscribers[chat_uuid]),
                self._total_connections,
            )
        try:
            yield subscriber
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(chat_uuid)
                if subscribers and subscriber in subscribers:
                    subscribers.remove(subscriber)
                    if not subscribers:
                        self._subscribers.pop(chat_uuid, None)
                self._total_connections = max(0, self._total_connections - 1)
                logger.debug(
                    "SSE unsubscribe chat=%s remaining=%s total=%s",
                    chat_uuid,
                    len(self._subscribers.get(chat_uuid, [])),
                    self._total_connections,
                )

    def publish(self, chat_uuid: UUID, event: StreamEvent) -> None:
        subscribers = self._subscribers.get(chat_uuid)
        if not subscribers:
            return

        for subscriber in list(subscribers):
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Disconnecting stalled subscriber for chat %s (queue full)",
                    chat_uuid,
                )
                subscriber.should_disconnect = True
                try:
                    subscriber.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

    async def heartbeat(self) -> AsyncGenerator[StreamEvent, None]:
        while True:
            await asyncio.sleep(_HEARTBEAT_SECONDS)
            yield HeartbeatEvent(timestamp=datetime.now(tz=timezone.utc).isoformat())

    @property
    def total_connections(self) -> int:
        return self._total_connections


def encode_sse_event(event: StreamEvent) -> str:
    return f"data: {json.dumps(asdict(event))}\n\n"
