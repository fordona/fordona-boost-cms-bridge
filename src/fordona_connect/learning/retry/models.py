"""Retry tables: the policy and the precomputed question neighbours."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
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


class QuestionNeighbour(Base):
    """Precomputed similar questions, top 20 per question, rebuilt after each release."""

    __tablename__ = "question_neighbour"

    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    neighbour_id: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # "metadata" now; an embedding model id once the AI layer fills these lists.
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    release_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (CheckConstraint("rank BETWEEN 1 AND 20", name="ck_question_neighbour_rank"),)
