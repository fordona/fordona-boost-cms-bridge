"""Learner attempt state: attempts, their items and the mistake ledger."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.db.models import Base


class LessonAttempt(Base):
    """One learner's attempt at one lesson's quiz.

    At most one open (not ``COMPLETED``) attempt per learner and lesson; a second
    start resumes it. ``request_id`` makes a start idempotent.
    """

    __tablename__ = "lesson_attempt"

    attempt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    learner_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_lesson.lesson_id"), nullable=False, index=True
    )
    unit_id: Mapped[str] = mapped_column(Text, ForeignKey("content_unit.unit_id"), nullable=False)
    # The challenge whose quiz the questions came from, if any. No foreign key:
    # Boost may retire the challenge while the attempt is history.
    challenge_id: Mapped[str | None] = mapped_column(Text)
    lesson_version: Mapped[str | None] = mapped_column(Text)
    selection_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    selection_reason: Mapped[str | None] = mapped_column(Text)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # The retry policy resolved at start: a later policy edit never changes an attempt.
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lesson_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_wrong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_wrong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_extras_short: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("learner_id", "request_id", name="uq_lesson_attempt_learner_request"),
        Index(
            "uq_lesson_attempt_one_open_per_lesson",
            "learner_id",
            "lesson_id",
            unique=True,
            postgresql_where=text("status <> 'COMPLETED'"),
        ),
        CheckConstraint("kind IN ('LESSON', 'REVIEW')", name="ck_lesson_attempt_kind"),
        CheckConstraint(
            "status IN ('IN_LESSON', 'IN_RETRY', 'COMPLETED')", name="ck_lesson_attempt_status"
        ),
        CheckConstraint("attempt_no > 0", name="ck_lesson_attempt_attempt_no"),
    )


class AttemptItem(Base):
    """One question served in an attempt, pinned to the revision it was graded against."""

    __tablename__ = "attempt_item"

    attempt_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lesson_attempt.attempt_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    item_source: Mapped[str] = mapped_column(Text, nullable=False)
    question_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_id: Mapped[str | None] = mapped_column(Text)
    # The wrong lesson item this one is similar to (retry phase, SIMILAR only).
    origin_question_id: Mapped[str | None] = mapped_column(Text)
    # Option keys in the order shown to the learner (shuffled with a CSPRNG).
    option_order: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    domain_code: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tag: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    selected_option_key: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    response_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "version"],
            ["content_question_revision.question_id", "content_question_revision.version"],
            name="fk_attempt_item_revision",
        ),
        Index("ix_attempt_item_learner_question", "learner_id", "question_id"),
        Index("ix_attempt_item_learner_answered_at", "learner_id", "answered_at"),
        CheckConstraint("phase IN ('LESSON', 'RETRY')", name="ck_attempt_item_phase"),
        CheckConstraint(
            "item_source IN ('BANK', 'CHALLENGE', 'REPEAT', 'SIMILAR')",
            name="ck_attempt_item_source",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_attempt_item_difficulty"),
        CheckConstraint("level IN ('EASY', 'MEDIUM', 'HARD')", name="ck_attempt_item_level"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_attempt_item_duration_ms"
        ),
    )


class Mistake(Base):
    """One row per learner and question ever answered wrong; the mistake review reads it."""

    __tablename__ = "mistake"

    learner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    home_lesson_id: Mapped[str] = mapped_column(Text, nullable=False)
    unit_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    times_wrong: Mapped[int] = mapped_column(Integer, nullable=False)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_via: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_mistake_learner_unit_status", "learner_id", "unit_id", "status"),
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_mistake_status"),
        CheckConstraint(
            "resolved_via IS NULL OR resolved_via IN ('REPEAT', 'RETAKE', 'LATER')",
            name="ck_mistake_resolved_via",
        ),
        CheckConstraint("times_wrong > 0", name="ck_mistake_times_wrong"),
    )
