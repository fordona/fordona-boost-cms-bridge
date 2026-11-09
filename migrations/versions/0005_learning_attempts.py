"""learning attempts: lesson_attempt, attempt_item, mistake, retry_policy

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB()
_UUID = postgresql.UUID(as_uuid=True)

# The engine's seeded defaults (V1_0_18), unchanged.
_GLOBAL_POLICY = {
    "retry_enabled": True,
    "extras_per_wrong": 1.5,
    "extras_min": 2,
    "extras_max": 5,
    "level_drop_allowed": 1,
    "similar_scope": "REACHED",
    "difficulty_level_map": {"1": "EASY", "2": "EASY", "3": "MEDIUM", "4": "HARD", "5": "HARD"},
}


def upgrade() -> None:
    op.create_table(
        "lesson_attempt",
        sa.Column("attempt_id", _UUID, primary_key=True),
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "lesson_id", sa.Text(), sa.ForeignKey("content_lesson.lesson_id"), nullable=False
        ),
        sa.Column("unit_id", sa.Text(), sa.ForeignKey("content_unit.unit_id"), nullable=False),
        sa.Column("challenge_id", sa.Text()),
        sa.Column("lesson_version", sa.Text()),
        sa.Column("selection_strategy", sa.Text(), nullable=False),
        sa.Column("selection_reason", sa.Text()),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("request_id", _UUID, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("policy_snapshot", _JSON, nullable=False),
        sa.Column("lesson_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lesson_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lesson_wrong", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_wrong", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_extras_short", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("learner_id", "request_id", name="uq_lesson_attempt_learner_request"),
        sa.CheckConstraint("kind IN ('LESSON', 'REVIEW')", name="ck_lesson_attempt_kind"),
        sa.CheckConstraint(
            "status IN ('IN_LESSON', 'IN_RETRY', 'COMPLETED')", name="ck_lesson_attempt_status"
        ),
        sa.CheckConstraint("attempt_no > 0", name="ck_lesson_attempt_attempt_no"),
    )
    op.create_index("ix_lesson_attempt_lesson_id", "lesson_attempt", ["lesson_id"])
    # At most one open attempt per learner and lesson: a concurrent second start
    # loses on this index and resumes the winner's attempt.
    op.create_index(
        "uq_lesson_attempt_one_open_per_lesson",
        "lesson_attempt",
        ["learner_id", "lesson_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'COMPLETED'"),
    )

    op.create_table(
        "attempt_item",
        sa.Column(
            "attempt_id",
            _UUID,
            sa.ForeignKey("lesson_attempt.attempt_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("item_source", sa.Text(), nullable=False),
        sa.Column("question_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("challenge_id", sa.Text()),
        sa.Column("origin_question_id", sa.Text()),
        sa.Column("option_order", _JSON, nullable=False),
        sa.Column("domain_code", sa.Text(), nullable=False),
        sa.Column("topic_tag", sa.Text()),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text()),
        sa.Column("similarity_score", sa.Numeric(5, 4)),
        sa.Column("selected_option_key", sa.Text()),
        sa.Column("is_correct", sa.Boolean()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("response_id", _UUID, unique=True),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["question_id", "version"],
            ["content_question_revision.question_id", "content_question_revision.version"],
            name="fk_attempt_item_revision",
        ),
        sa.CheckConstraint("phase IN ('LESSON', 'RETRY')", name="ck_attempt_item_phase"),
        sa.CheckConstraint(
            "item_source IN ('BANK', 'CHALLENGE', 'REPEAT', 'SIMILAR')",
            name="ck_attempt_item_source",
        ),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_attempt_item_difficulty"),
        sa.CheckConstraint("level IN ('EASY', 'MEDIUM', 'HARD')", name="ck_attempt_item_level"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_attempt_item_duration_ms"
        ),
    )
    op.create_index(
        "ix_attempt_item_learner_question", "attempt_item", ["learner_id", "question_id"]
    )
    op.create_index(
        "ix_attempt_item_learner_answered_at", "attempt_item", ["learner_id", "answered_at"]
    )

    op.create_table(
        "mistake",
        sa.Column("learner_id", sa.Text(), primary_key=True),
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("home_lesson_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("times_wrong", sa.Integer(), nullable=False),
        sa.Column("last_wrong_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_via", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_mistake_status"),
        sa.CheckConstraint(
            "resolved_via IS NULL OR resolved_via IN ('REPEAT', 'RETAKE', 'LATER')",
            name="ck_mistake_resolved_via",
        ),
        sa.CheckConstraint("times_wrong > 0", name="ck_mistake_times_wrong"),
    )
    op.create_index(
        "ix_mistake_learner_unit_status", "mistake", ["learner_id", "unit_id", "status"]
    )

    retry_policy = op.create_table(
        "retry_policy",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("key_values", _JSON, nullable=False),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "scope_id", name="uq_retry_policy_scope"),
        sa.CheckConstraint("scope IN ('GLOBAL', 'UNIT', 'LESSON')", name="ck_retry_policy_scope"),
    )
    op.execute(
        retry_policy.insert().values(
            scope="GLOBAL",
            scope_id="GLOBAL",
            key_values=_GLOBAL_POLICY,
            updated_by="system",
            updated_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    for table in ("retry_policy", "mistake", "attempt_item", "lesson_attempt"):
        op.drop_table(table)
