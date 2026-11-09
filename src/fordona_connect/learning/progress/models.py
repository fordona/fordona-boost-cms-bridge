"""Learner progress tables."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.db.models import Base


class LessonProgress(Base):
    """One row per learner and lesson, summarising every attempt at it."""

    __tablename__ = "lesson_progress"

    learner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(Text, primary_key=True)
    unit_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    # The open attempt on this lesson, if any (home's Continue card reads it).
    open_attempt_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    last_lesson_correct: Mapped[int | None] = mapped_column(Integer)
    last_lesson_total: Mapped[int | None] = mapped_column(Integer)
    best_lesson_correct: Mapped[int | None] = mapped_column(Integer)
    # Best lesson-phase correct/total over completed attempts, 0..1; feeds readiness.
    best_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    first_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('IN_PROGRESS', 'COMPLETED')", name="ck_lesson_progress_status"),
        CheckConstraint("attempts >= 0", name="ck_lesson_progress_attempts"),
        CheckConstraint(
            "best_accuracy IS NULL OR best_accuracy BETWEEN 0 AND 1",
            name="ck_lesson_progress_best_accuracy",
        ),
    )


class LearnerSummary(Base):
    """One row per learner: streak, readiness sum and the learning path's ETag input."""

    __tablename__ = "learner_summary"

    learner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    # Bumped on every lesson start and completion: part of the learning path's ETag.
    progress_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_lessons: Mapped[int] = mapped_column(Integer, nullable=False)
    sum_best_accuracy: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    # Local date, in the learner's own timezone, of the last completed lesson.
    last_active_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint(
            "current_streak >= 0 AND longest_streak >= current_streak",
            name="ck_learner_summary_streak",
        ),
    )


class LearnerActivityDay(Base):
    """Distinct lessons completed per learner and local day (weekly view, daily challenge)."""

    __tablename__ = "learner_activity_day"

    learner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    lessons_completed: Mapped[int] = mapped_column(Integer, nullable=False)


class LearnerActivityLesson(Base):
    """Which lessons a learner completed on a local day: a retake the same day counts once."""

    __tablename__ = "learner_activity_lesson"

    learner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(Text, primary_key=True)


Index("ix_lesson_progress_unit_id", LessonProgress.unit_id)
