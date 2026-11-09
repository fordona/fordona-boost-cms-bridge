"""learning content read model: Boost catalogue, journeys, mock exams, answer keys

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "content_release",
        sa.Column("release_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "content_unit",
        sa.Column("unit_id", sa.Text(), primary_key=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("title", _JSON, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name="ck_content_unit_status"),
    )
    op.create_table(
        "content_lesson",
        sa.Column("lesson_id", sa.Text(), primary_key=True),
        sa.Column("unit_id", sa.Text(), sa.ForeignKey("content_unit.unit_id"), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("title", _JSON, nullable=False),
        sa.Column("current_version", sa.Text()),
        sa.Column("estimated_minutes", sa.Integer()),
        sa.CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name="ck_content_lesson_status"),
    )
    op.create_index("ix_content_lesson_unit_id", "content_lesson", ["unit_id"])
    op.create_table(
        "content_question",
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("home_lesson_id", sa.Text()),
        sa.Column("unit_id", sa.Text()),
        sa.Column("current_version", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("exclusion_reason", sa.Text()),
        sa.CheckConstraint("status IN ('ACTIVE', 'EXCLUDED')", name="ck_content_question_status"),
    )
    op.create_index("ix_content_question_home_lesson_id", "content_question", ["home_lesson_id"])
    op.create_index("ix_content_question_unit_id", "content_question", ["unit_id"])
    op.create_table(
        "content_question_revision",
        sa.Column(
            "question_id",
            sa.Text(),
            sa.ForeignKey("content_question.question_id"),
            primary_key=True,
        ),
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text()),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("domain_code", sa.Text(), nullable=False),
        sa.Column("topic_tag", sa.Text()),
        sa.Column("correct_option_key", sa.Text(), nullable=False),
        sa.Column("option_keys", _JSON, nullable=False),
        sa.Column("media_kinds", _JSON, nullable=False),
        sa.Column("explanation", _JSON, nullable=False),
        sa.Column(
            "release_id",
            sa.BigInteger(),
            sa.ForeignKey("content_release.release_id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 5", name="ck_content_question_revision_difficulty"
        ),
        sa.CheckConstraint(
            "level IN ('EASY', 'MEDIUM', 'HARD')", name="ck_content_question_revision_level"
        ),
    )
    op.create_index(
        "ix_content_question_revision_release_id", "content_question_revision", ["release_id"]
    )
    op.create_table(
        "content_mock_exam",
        sa.Column("mock_exam_id", sa.Text(), primary_key=True),
        sa.Column("name", _JSON, nullable=False),
        sa.Column("description", _JSON, nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("current_version", sa.Text()),
    )
    op.create_table(
        "content_mock_exam_question",
        sa.Column(
            "mock_exam_id",
            sa.Text(),
            sa.ForeignKey("content_mock_exam.mock_exam_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("sort", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_content_mock_exam_question_question_id", "content_mock_exam_question", ["question_id"]
    )
    op.create_table(
        "content_journey",
        sa.Column("journey_id", sa.Text(), primary_key=True),
        sa.Column("title", _JSON, nullable=False),
        sa.Column("description", _JSON, nullable=False),
        sa.Column("current_version", sa.Text()),
    )
    op.create_table(
        "content_milestone",
        sa.Column("milestone_id", sa.Text(), primary_key=True),
        sa.Column(
            "journey_id",
            sa.Text(),
            sa.ForeignKey("content_journey.journey_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("title", _JSON, nullable=False),
        sa.Column("description", _JSON, nullable=False),
    )
    op.create_index("ix_content_milestone_journey_id", "content_milestone", ["journey_id"])
    op.create_table(
        "content_challenge",
        sa.Column("challenge_id", sa.Text(), primary_key=True),
        sa.Column(
            "milestone_id",
            sa.Text(),
            sa.ForeignKey("content_milestone.milestone_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("title", _JSON, nullable=False),
        sa.Column("goal", _JSON, nullable=False),
    )
    op.create_index("ix_content_challenge_milestone_id", "content_challenge", ["milestone_id"])
    op.create_table(
        "content_challenge_lesson",
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("content_challenge.challenge_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lesson_id", sa.Text(), primary_key=True),
        sa.Column("sort", sa.Integer(), nullable=False),
    )
    op.create_table(
        "content_challenge_question",
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("content_challenge.challenge_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("sort", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_content_challenge_question_question_id", "content_challenge_question", ["question_id"]
    )


def downgrade() -> None:
    for table in (
        "content_challenge_question",
        "content_challenge_lesson",
        "content_challenge",
        "content_milestone",
        "content_journey",
        "content_mock_exam_question",
        "content_mock_exam",
        "content_question_revision",
        "content_question",
        "content_lesson",
        "content_unit",
        "content_release",
    ):
        op.drop_table(table)
