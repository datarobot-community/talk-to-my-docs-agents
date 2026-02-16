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

"""add_needs_reauth_to_identity

Revision ID: 450de92b0fac
Revises: d5c7f18c5b9f
Create Date: 2026-01-27 14:10:20.258150

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "450de92b0fac"
down_revision: Union[str, Sequence[str], None] = "d5c7f18c5b9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add needs_reauth column to identity table."""
    with op.batch_alter_table("identity", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "needs_reauth",
                sa.Boolean(),
                nullable=False,
                server_default=sa.sql.expression.false(),
            )
        )


def downgrade() -> None:
    """Remove needs_reauth column from identity table."""
    with op.batch_alter_table("identity", schema=None) as batch_op:
        batch_op.drop_column("needs_reauth")
