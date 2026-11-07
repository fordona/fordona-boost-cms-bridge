"""learning_journey per-user assignment/progress + dynamic attempt-state tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_journey_user_assignments",
        sa.Column("assignment_id", sa.Text(), primary_key=True),
        sa.Column("app_user_id", sa.Text(), nullable=False),
        sa.Column(
            "journey_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_templates.journey_id"),
            nullable=False,
        ),
        sa.Column("journey_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_user_id", "journey_id"),
    )

    op.create_table(
        "learning_journey_user_challenge_progress",
        sa.Column(
            "assignment_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_user_assignments.assignment_id"),
            primary_key=True,
        ),
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_challenges.challenge_id"),
            primary_key=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_progression_complete", sa.Boolean(), nullable=False),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_attempt_id", sa.Text()),
        sa.Column("active_session_id", sa.Text()),
        sa.Column("remediation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remediation_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("best_full_attempt_score_percentage", sa.Numeric(5, 2)),
    )

    op.create_table(
        "learning_journey_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_user_assignments.assignment_id"),
            nullable=False,
        ),
        sa.Column("app_user_id", sa.Text(), nullable=False),
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_challenges.challenge_id"),
            nullable=False,
        ),
        sa.Column("session_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("remediation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remediation_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "learning_journey_attempts",
        sa.Column("attempt_id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_sessions.session_id"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_user_assignments.assignment_id"),
            nullable=False,
        ),
        sa.Column("app_user_id", sa.Text(), nullable=False),
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_challenges.challenge_id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("challenge_attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempt_type", sa.Text(), nullable=False),
        sa.Column("challenge_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer()),
        sa.Column("incorrect_count", sa.Integer()),
        sa.Column("score_percentage", sa.Numeric(5, 2)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "attempt_number"),
        sa.UniqueConstraint("assignment_id", "challenge_id", "challenge_attempt_number"),
    )

    op.create_table(
        "learning_journey_attempt_questions",
        sa.Column(
            "attempt_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_attempts.attempt_id"),
            primary_key=True,
        ),
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("question_version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("option_order", postgresql.JSONB(), nullable=False),
        sa.Column("answer_key_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("question_content_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_question_id", sa.Text()),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Text(), nullable=False, server_default="UNANSWERED"),
        sa.Column("selected_option_keys", postgresql.JSONB()),
        sa.Column("selected_option_ids", postgresql.JSONB()),
        sa.Column("is_correct", sa.Boolean()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("attempt_id", "position"),
    )

    op.create_table(
        "learning_journey_remediations",
        sa.Column("remediation_id", sa.Text(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_sessions.session_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_attempt_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_attempts.attempt_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "attempt_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_attempts.attempt_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("generation_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "learning_journey_idempotency_records",
        sa.Column("app_user_id", sa.Text(), primary_key=True),
        sa.Column("endpoint", sa.Text(), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column("request_fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learning_journey_idempotency_records")
    op.drop_table("learning_journey_remediations")
    op.drop_table("learning_journey_attempt_questions")
    op.drop_table("learning_journey_attempts")
    op.drop_table("learning_journey_sessions")
    op.drop_table("learning_journey_user_challenge_progress")
    op.drop_table("learning_journey_user_assignments")
