"""platform event cursor: where fordona-connect is in fordona-engine's outbox

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_event_cursor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_event_id", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_event_cursor")
