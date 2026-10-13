"""content_snapshot: last-known-good Boost payloads

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_snapshot",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_content_snapshot_resource_locale", "content_snapshot", ["resource", "locale"]
    )


def downgrade() -> None:
    op.drop_index("ix_content_snapshot_resource_locale", table_name="content_snapshot")
    op.drop_table("content_snapshot")
