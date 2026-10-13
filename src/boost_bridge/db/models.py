"""ORM models. Phase 1 holds a single table: the last-known-good content snapshot."""

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ContentSnapshot(Base):
    """Raw Boost payload for one upstream request key.

    It is read only when Boost is unavailable (stale-if-error). Rows are deleted
    when Boost reports the content as gone, so unpublished content cannot come
    back through the fallback.
    """

    __tablename__ = "content_snapshot"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    # When this exact content was first fetched (unchanged refreshes do not write).
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_content_snapshot_resource_locale", "resource", "locale"),)
