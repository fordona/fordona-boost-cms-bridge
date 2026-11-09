"""Content read model: Boost's published catalogue, as the learning service needs it.

Ids are Boost's own. Display text is stored per locale as JSON (``{"sv-SE": "...",
"en-GB": "..."}``). Membership references to questions and lessons carry no
foreign key: Boost can list an id it does not (yet) publish, and one such id must
not fail the whole sync.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.db.models import Base


class ContentRelease(Base):
    """One row per sync that changed the read model."""

    __tablename__ = "content_release"

    release_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContentUnit(Base):
    """A Boost module."""

    __tablename__ = "content_unit"

    unit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name="ck_content_unit_status"),
    )


class ContentLesson(Base):
    """A Boost lesson ("chapter"). Its theory itself is not stored, only its version."""

    __tablename__ = "content_lesson"

    lesson_id: Mapped[str] = mapped_column(Text, primary_key=True)
    unit_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_unit.unit_id"), nullable=False, index=True
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    current_version: Mapped[str | None] = mapped_column(Text)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name="ck_content_lesson_status"),
    )


class ContentQuestion(Base):
    """A Boost question and its current published version.

    ``EXCLUDED`` questions are never delivered; ``exclusion_reason`` says why.
    """

    __tablename__ = "content_question"

    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    home_lesson_id: Mapped[str | None] = mapped_column(Text, index=True)
    unit_id: Mapped[str | None] = mapped_column(Text, index=True)
    current_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'EXCLUDED')", name="ck_content_question_status"),
    )


class ContentQuestionRevision(Base):
    """One immutable published revision of a question, with its **answer key**.

    Written once, the first time a valid revision is seen, and never updated: a
    published Boost revision does not change. ``correct_option_key`` and
    ``explanation`` are grading data and must never reach a public response.
    """

    __tablename__ = "content_question_revision"

    question_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_question.question_id"), primary_key=True
    )
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    domain_code: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tag: Mapped[str | None] = mapped_column(Text)
    correct_option_key: Mapped[str] = mapped_column(Text, nullable=False)
    option_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    media_kinds: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    # Locale code to explanation, as Boost sends it (block list or text).
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    release_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_release.release_id"), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5", name="ck_content_question_revision_difficulty"
        ),
        CheckConstraint(
            "level IN ('EASY', 'MEDIUM', 'HARD')", name="ck_content_question_revision_level"
        ),
    )


class ContentMockExam(Base):
    __tablename__ = "content_mock_exam"

    mock_exam_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    # The exam's fixed size, per Boost's editorial rules.
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # False when Boost could not serve question_count questions in the default locale.
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    current_version: Mapped[str | None] = mapped_column(Text)


class ContentMockExamQuestion(Base):
    """Ordered membership, in the default locale's order."""

    __tablename__ = "content_mock_exam_question"

    mock_exam_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_mock_exam.mock_exam_id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_content_mock_exam_question_question_id", "question_id"),)


class ContentJourney(Base):
    __tablename__ = "content_journey"

    journey_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    current_version: Mapped[str | None] = mapped_column(Text)


class ContentMilestone(Base):
    __tablename__ = "content_milestone"

    milestone_id: Mapped[str] = mapped_column(Text, primary_key=True)
    journey_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("content_journey.journey_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)


class ContentChallenge(Base):
    __tablename__ = "content_challenge"

    challenge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    milestone_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("content_milestone.milestone_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    # What the learner should be able to do, per locale.
    goal: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)


class ContentChallengeLesson(Base):
    __tablename__ = "content_challenge_lesson"

    challenge_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_challenge.challenge_id", ondelete="CASCADE"), primary_key=True
    )
    lesson_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False)


class ContentChallengeQuestion(Base):
    """A challenge's quiz, in the default locale's order."""

    __tablename__ = "content_challenge_question"

    challenge_id: Mapped[str] = mapped_column(
        Text, ForeignKey("content_challenge.challenge_id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_content_challenge_question_question_id", "question_id"),)
