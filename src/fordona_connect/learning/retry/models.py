"""The retry policy table."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.db.models import Base


class RetryPolicyRow(Base):
    """Retry-phase settings overridden at one scope (GLOBAL, a unit or a lesson)."""

    __tablename__ = "retry_policy"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    # "GLOBAL" for the global row; a unit or lesson id otherwise (no foreign key:
    # a stale policy row must never block content from being retired).
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    key_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope", "scope_id", name="uq_retry_policy_scope"),
        CheckConstraint("scope IN ('GLOBAL', 'UNIT', 'LESSON')", name="ck_retry_policy_scope"),
    )
