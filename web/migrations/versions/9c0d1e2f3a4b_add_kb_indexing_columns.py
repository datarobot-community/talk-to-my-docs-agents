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

"""add_kb_indexing_columns

Adds the per-knowledge-base indexing/retrieval columns used by semantic
retrieval:

* index_status   - build state (not_indexed/indexing/ready/failed).
* indexed_at     - timestamp of the last successful build.
* last_error     - last indexing error, surfaced to ops/UI on failure.
* retrieval_mode - keyword (original behavior) or semantic. Server default
  'keyword' so EXISTING knowledge bases keep the original behavior until a
  user explicitly switches them.

Revision ID: 9c0d1e2f3a4b
Revises: d7bb78aed242
Create Date: 2026-07-09 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c0d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "d7bb78aed242"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("knowledgebase") as batch_op:
        batch_op.add_column(
            sa.Column(
                "index_status",
                sa.String(length=20),
                nullable=False,
                server_default="not_indexed",
            )
        )
        batch_op.add_column(
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_error", sa.String(length=2000), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "retrieval_mode",
                sa.String(length=16),
                nullable=False,
                server_default="keyword",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledgebase") as batch_op:
        batch_op.drop_column("retrieval_mode")
        batch_op.drop_column("last_error")
        batch_op.drop_column("indexed_at")
        batch_op.drop_column("index_status")
