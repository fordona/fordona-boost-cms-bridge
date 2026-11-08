"""learning_journey content tables + one-time seed from the bundled mock JSON

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fordona_connect"
    / "learning_journey"
    / "seed"
    / "learning_journey_mock_db.json"
)


def upgrade() -> None:
    op.create_table(
        "learning_journey_templates",
        sa.Column("journey_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("stats", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "learning_journey_milestones",
        sa.Column("milestone_id", sa.Text(), primary_key=True),
        sa.Column(
            "journey_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_templates.journey_id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("challenge_count", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("difficulty_distribution", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "learning_journey_assignment_milestones",
        sa.Column(
            "journey_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_templates.journey_id"),
            primary_key=True,
        ),
        sa.Column(
            "milestone_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_milestones.milestone_id"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )

    op.create_table(
        "learning_journey_challenges",
        sa.Column("challenge_id", sa.Text(), primary_key=True),
        sa.Column(
            "milestone_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_milestones.milestone_id"),
            nullable=False,
        ),
        sa.Column(
            "journey_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_templates.journey_id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("display_code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("estimated_minutes", sa.Integer()),
        sa.Column("topics", postgresql.JSONB(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("difficulty_distribution", postgresql.JSONB(), nullable=False),
        sa.Column("content_readiness", postgresql.JSONB(), nullable=False),
        sa.Column("source", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "learning_journey_milestone_challenges",
        sa.Column(
            "milestone_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_milestones.milestone_id"),
            primary_key=True,
        ),
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_challenges.challenge_id"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )

    op.create_table(
        "learning_journey_questions",
        sa.Column("question_id", sa.Text(), primary_key=True),
        sa.Column("question_version", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.Text(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("image_urls", postgresql.JSONB(), nullable=False),
        sa.Column("has_image_reference", sa.Boolean(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("correct_answer", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("connected_chapters", postgresql.JSONB(), nullable=False),
        sa.Column("cms_row_numbers", postgresql.JSONB(), nullable=False),
        sa.Column("content_readiness", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "learning_journey_challenge_question_memberships",
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_challenges.challenge_id"),
            primary_key=True,
        ),
        sa.Column("challenge_version", sa.Integer(), nullable=False),
        sa.Column(
            "question_id",
            sa.Text(),
            sa.ForeignKey("learning_journey_questions.question_id"),
            primary_key=True,
        ),
        sa.Column("question_version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )

    _seed()


def _seed() -> None:
    with _SEED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    op.bulk_insert(
        sa.table(
            "learning_journey_templates",
            sa.column("journey_id"),
            sa.column("version"),
            sa.column("title"),
            sa.column("description"),
            sa.column("stats", postgresql.JSONB()),
        ),
        [
            {
                "journey_id": t["journey_id"],
                "version": t["version"],
                "title": t["title"],
                "description": t["description"],
                "stats": t["stats"],
            }
            for t in data["journey_templates"]
        ],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_milestones",
            sa.column("milestone_id"),
            sa.column("journey_id"),
            sa.column("position"),
            sa.column("title"),
            sa.column("description"),
            sa.column("challenge_count"),
            sa.column("question_count"),
            sa.column("difficulty_distribution", postgresql.JSONB()),
        ),
        [
            {
                "milestone_id": m["milestone_id"],
                "journey_id": m["journey_id"],
                "position": m["position"],
                "title": m["title"],
                "description": m["description"],
                "challenge_count": m["challenge_count"],
                "question_count": m["question_count"],
                "difficulty_distribution": m["difficulty_distribution"],
            }
            for m in data["milestones"]
        ],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_assignment_milestones",
            sa.column("journey_id"),
            sa.column("milestone_id"),
            sa.column("position"),
        ),
        data["assignment_milestones"],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_challenges",
            sa.column("challenge_id"),
            sa.column("milestone_id"),
            sa.column("journey_id"),
            sa.column("version"),
            sa.column("position"),
            sa.column("display_code"),
            sa.column("title"),
            sa.column("description"),
            sa.column("estimated_minutes"),
            sa.column("topics", postgresql.JSONB()),
            sa.column("question_count"),
            sa.column("difficulty_distribution", postgresql.JSONB()),
            sa.column("content_readiness", postgresql.JSONB()),
            sa.column("source", postgresql.JSONB()),
        ),
        [
            {
                "challenge_id": c["challenge_id"],
                "milestone_id": c["milestone_id"],
                "journey_id": c["journey_id"],
                "version": c["version"],
                "position": c["position"],
                "display_code": c["display_code"],
                "title": c["title"],
                "description": c["description"],
                "estimated_minutes": c["estimated_minutes"],
                "topics": c["topics"],
                "question_count": c["question_count"],
                "difficulty_distribution": c["difficulty_distribution"],
                "content_readiness": c["content_readiness"],
                "source": c["source"],
            }
            for c in data["challenges"]
        ],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_milestone_challenges",
            sa.column("milestone_id"),
            sa.column("challenge_id"),
            sa.column("position"),
        ),
        data["milestone_challenges"],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_questions",
            sa.column("question_id"),
            sa.column("question_version"),
            sa.column("question_type"),
            sa.column("question_text"),
            sa.column("difficulty"),
            sa.column("level"),
            sa.column("image_urls", postgresql.JSONB()),
            sa.column("has_image_reference"),
            sa.column("options", postgresql.JSONB()),
            sa.column("correct_answer", postgresql.JSONB()),
            sa.column("explanation"),
            sa.column("connected_chapters", postgresql.JSONB()),
            sa.column("cms_row_numbers", postgresql.JSONB()),
            sa.column("content_readiness", postgresql.JSONB()),
        ),
        [
            {
                "question_id": q["question_id"],
                "question_version": q["question_version"],
                "question_type": q["question_type"],
                "question_text": q["question_text"],
                "difficulty": q["difficulty"],
                "level": q["level"],
                "image_urls": q["image_urls"],
                "has_image_reference": q["has_image_reference"],
                "options": q["options"],
                "correct_answer": q["correct_answer"],
                "explanation": q["explanation"],
                "connected_chapters": q["connected_chapters"],
                "cms_row_numbers": q["cms_row_numbers"],
                "content_readiness": q["content_readiness"],
            }
            for q in data["questions"]
        ],
    )

    op.bulk_insert(
        sa.table(
            "learning_journey_challenge_question_memberships",
            sa.column("challenge_id"),
            sa.column("challenge_version"),
            sa.column("question_id"),
            sa.column("question_version"),
            sa.column("position"),
        ),
        data["challenge_question_memberships"],
    )


def downgrade() -> None:
    op.drop_table("learning_journey_challenge_question_memberships")
    op.drop_table("learning_journey_questions")
    op.drop_table("learning_journey_milestone_challenges")
    op.drop_table("learning_journey_challenges")
    op.drop_table("learning_journey_assignment_milestones")
    op.drop_table("learning_journey_milestones")
    op.drop_table("learning_journey_templates")
