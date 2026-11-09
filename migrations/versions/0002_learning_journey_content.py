"""learning_journey content tables (superseded: content now comes from Boost)

This revision once created seven learning-journey content tables and seeded them
from a bundled mock JSON. Journey content is now authored in Boost and synced
into the ``content_*`` tables (0004), so it creates nothing. It stays in the
chain so existing revision ids keep resolving. No shared database ever applied
the old version; a local one that did keeps seven unused tables, harmless.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
