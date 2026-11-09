"""learning progress and retry neighbours

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_neighbour",
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("rank", sa.SmallInteger(), primary_key=True),
        sa.Column("neighbour_id", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("release_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("rank BETWEEN 1 AND 20", name="ck_question_neighbour_rank"),
    )
    op.create_table(
        "lesson_progress",
        sa.Column("learner_id", sa.Text(), primary_key=True),
        sa.Column("lesson_id", sa.Text(), primary_key=True),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("open_attempt_id", postgresql.UUID(as_uuid=True)),
        sa.Column("last_lesson_correct", sa.Integer()),
        sa.Column("last_lesson_total", sa.Integer()),
        sa.Column("best_lesson_correct", sa.Integer()),
        sa.Column("best_accuracy", sa.Numeric(5, 4)),
        sa.Column("first_completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED')", name="ck_lesson_progress_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_lesson_progress_attempts"),
        sa.CheckConstraint(
            "best_accuracy IS NULL OR best_accuracy BETWEEN 0 AND 1",
            name="ck_lesson_progress_best_accuracy",
        ),
    )
    op.create_index("ix_lesson_progress_unit_id", "lesson_progress", ["unit_id"])
    op.create_table(
        "learner_summary",
        sa.Column("learner_id", sa.Text(), primary_key=True),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("progress_version", sa.BigInteger(), nullable=False),
        sa.Column("completed_lessons", sa.Integer(), nullable=False),
        sa.Column("sum_best_accuracy", sa.Numeric(), nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False),
        sa.Column("longest_streak", sa.Integer(), nullable=False),
        sa.Column("last_active_date", sa.Date()),
        sa.CheckConstraint(
            "current_streak >= 0 AND longest_streak >= current_streak",
            name="ck_learner_summary_streak",
        ),
    )
    op.create_table(
        "learner_activity_day",
        sa.Column("learner_id", sa.Text(), primary_key=True),
        sa.Column("local_date", sa.Date(), primary_key=True),
        sa.Column("lessons_completed", sa.Integer(), nullable=False),
    )
    op.create_table(
        "learner_activity_lesson",
        sa.Column("learner_id", sa.Text(), primary_key=True),
        sa.Column("local_date", sa.Date(), primary_key=True),
        sa.Column("lesson_id", sa.Text(), primary_key=True),
    )


def downgrade() -> None:
    for table in (
        "learner_activity_lesson",
        "learner_activity_day",
        "learner_summary",
        "lesson_progress",
        "question_neighbour",
    ):
        op.drop_table(table)
