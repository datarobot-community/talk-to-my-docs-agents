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
import json
import uuid as uuidpkg
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence, cast

from sqlalchemy import Column, DateTime, ForeignKey, desc
from sqlmodel import Field, SQLModel, select

from app.db import DBCtx


class Role(str, Enum):
    """Message source role"""

    USER = "user"
    ASSISTANT = "assistant"


class Message(SQLModel, table=True):
    uuid: uuidpkg.UUID = Field(
        default_factory=uuidpkg.uuid4, primary_key=True, unique=True
    )
    chat_id: uuidpkg.UUID | None = Field(
        default=None,
        sa_column=Column(
            "chat_id", ForeignKey("chat.uuid", ondelete="CASCADE"), index=True
        ),
    )
    role: str = Field(default=Role.USER)
    model: str = Field(default="")

    content: str = Field(default="")
    components: str = Field(default="[]")
    in_progress: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    error: str | None = Field(default=None)

    def dump_json_compatible(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.model_dump_json()))


class MessageCreate(SQLModel):
    """
    Schema for creating a new message.
    """

    chat_id: uuidpkg.UUID
    role: str
    model: str
    content: str
    components: str
    error: str | None


class MessageRepository:
    """
    Message repository class to handle message-related database operations.
    """

    def __init__(self, db: DBCtx):
        self._db = db

    async def create_message(self, message_data: MessageCreate) -> Message:
        """
        Add a new message to the database.
        """
        message = Message(**message_data.model_dump())

        async with self._db.session() as session:
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def get_message(self, uuid: uuidpkg.UUID) -> Message | None:
        """
        Retrieve a message by their ID.
        """
        async with self._db.session() as sess:
            response = await sess.exec(
                select(Message).where(Message.uuid == uuid).limit(1)
            )
            return response.one()

    async def get_chat_messages(self, chat_id: uuidpkg.UUID) -> Sequence[Message]:
        """
        Retrieve all messages from the chat.
        """
        async with self._db.session() as sess:
            response = await sess.exec(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at)  # type: ignore[arg-type]
            )
            return response.all()

    async def get_last_messages(
        self, chat_ids: list[uuidpkg.UUID]
    ) -> dict[uuidpkg.UUID, Message]:
        """
        Retrieve last messages from each chat in the list.
        """
        if not chat_ids:
            return {}

        async with self._db.session() as sess:
            result_dict = {}

            # For each chat, get the latest message
            # This approach avoids the GROUP BY error and is compatible with both SQLite and PostgreSQL
            for chat_id in chat_ids:
                response = await sess.exec(
                    select(Message)
                    .where(Message.chat_id == chat_id)
                    .order_by(desc(Message.created_at))  # type: ignore[arg-type]
                    .limit(1)
                )
                message = response.first()
                if message:
                    result_dict[chat_id] = message

            return result_dict
