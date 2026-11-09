"""ORM tables for learning-journey learner state.

Journey content (milestones, challenges, quizzes) is authored in Boost and read
through ``content.JourneyContentSource``; these tables hold only per-learner state.
Content ids here are Boost's own and carry no foreign key: Boost may retire a
challenge while a learner's history still refers to it.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.db.models import Base

# --- Per-user assignment/progress -------------------------------------------


class LearningJourneyUserAssignment(Base):
    __tablename__ = "learning_journey_user_assignments"

    assignment_id: Mapped[str] = mapped_column(Text, primary_key=True)
    app_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    journey_id: Mapped[str] = mapped_column(Text, nullable=False)
    journey_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("app_user_id", "journey_id"),)


class LearningJourneyUserChallengeProgress(Base):
    __tablename__ = "learning_journey_user_challenge_progress"

    assignment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_user_assignments.assignment_id"), primary_key=True
    )
    challenge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_progression_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_attempt_id: Mapped[str | None] = mapped_column(Text)
    active_session_id: Mapped[str | None] = mapped_column(Text)
    remediation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remediation_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    best_full_attempt_score_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))


# --- Dynamic state -----------------------------------------------------------


class LearningJourneySession(Base):
    __tablename__ = "learning_journey_sessions"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    assignment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_user_assignments.assignment_id"), nullable=False
    )
    app_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remediation_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningJourneyAttempt(Base):
    __tablename__ = "learning_journey_attempts"

    attempt_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_sessions.session_id"), nullable=False
    )
    assignment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_user_assignments.assignment_id"), nullable=False
    )
    app_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_id: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    challenge_attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_type: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    incorrect_count: Mapped[int | None] = mapped_column(Integer)
    score_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("session_id", "attempt_number"),
        UniqueConstraint("assignment_id", "challenge_id", "challenge_attempt_number"),
    )


class LearningJourneyAttemptQuestion(Base):
    __tablename__ = "learning_journey_attempt_questions"

    attempt_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_attempts.attempt_id"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    question_version: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Canonical option_ids in the order actually delivered to this attempt.
    option_order: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    answer_key_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    question_content_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_question_id: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[str] = mapped_column(Text, nullable=False, default="UNANSWERED")
    selected_option_keys: Mapped[list[Any] | None] = mapped_column(JSONB)
    selected_option_ids: Mapped[list[Any] | None] = mapped_column(JSONB)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("attempt_id", "position"),)


class LearningJourneyRemediation(Base):
    __tablename__ = "learning_journey_remediations"

    remediation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_sessions.session_id"), nullable=False, unique=True
    )
    source_attempt_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_attempts.attempt_id"), nullable=False, unique=True
    )
    attempt_id: Mapped[str] = mapped_column(
        Text, ForeignKey("learning_journey_attempts.attempt_id"), nullable=False, unique=True
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningJourneyIdempotencyRecord(Base):
    __tablename__ = "learning_journey_idempotency_records"

    app_user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
