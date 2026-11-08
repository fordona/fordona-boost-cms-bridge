"""All Postgres access for the Learning Journey feature.

Content tables (seeded by migration 0002) are read-only here. Per-user/dynamic tables
are read and written. Every method opens its own session, following
``db/snapshot_repository.py``'s convention: ``async with self._sessionmaker() as
session:`` for reads, ``async with self._sessionmaker() as session, session.begin():``
for writes.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.learning_journey.models import (
    LearningJourneyAttempt,
    LearningJourneyAttemptQuestion,
    LearningJourneyChallenge,
    LearningJourneyChallengeQuestionMembership,
    LearningJourneyIdempotencyRecord,
    LearningJourneyMilestone,
    LearningJourneyQuestion,
    LearningJourneyRemediation,
    LearningJourneySession,
    LearningJourneyTemplate,
    LearningJourneyUserAssignment,
    LearningJourneyUserChallengeProgress,
)


class LearningJourneyRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # --- Content reads (read-only after migration 0002) ---------------------

    async def get_journey_template(self, journey_id: str) -> LearningJourneyTemplate | None:
        async with self._sessionmaker() as session:
            return await session.get(LearningJourneyTemplate, journey_id)

    async def list_milestones(self, journey_id: str) -> Sequence[LearningJourneyMilestone]:
        async with self._sessionmaker() as session:
            stmt = (
                select(LearningJourneyMilestone)
                .where(LearningJourneyMilestone.journey_id == journey_id)
                .order_by(LearningJourneyMilestone.position)
            )
            return (await session.execute(stmt)).scalars().all()

    async def get_milestone(self, milestone_id: str) -> LearningJourneyMilestone | None:
        async with self._sessionmaker() as session:
            return await session.get(LearningJourneyMilestone, milestone_id)

    async def list_challenges_for_milestone(
        self, milestone_id: str
    ) -> Sequence[LearningJourneyChallenge]:
        async with self._sessionmaker() as session:
            stmt = (
                select(LearningJourneyChallenge)
                .where(LearningJourneyChallenge.milestone_id == milestone_id)
                .order_by(LearningJourneyChallenge.position)
            )
            return (await session.execute(stmt)).scalars().all()

    async def get_challenge(self, challenge_id: str) -> LearningJourneyChallenge | None:
        async with self._sessionmaker() as session:
            return await session.get(LearningJourneyChallenge, challenge_id)

    async def list_questions_for_challenge(
        self, challenge_id: str
    ) -> Sequence[tuple[LearningJourneyQuestion, int]]:
        """Questions in membership ``position`` order, paired with that position."""
        async with self._sessionmaker() as session:
            stmt = (
                select(LearningJourneyQuestion, LearningJourneyChallengeQuestionMembership.position)
                .join(
                    LearningJourneyChallengeQuestionMembership,
                    LearningJourneyChallengeQuestionMembership.question_id
                    == LearningJourneyQuestion.question_id,
                )
                .where(LearningJourneyChallengeQuestionMembership.challenge_id == challenge_id)
                .order_by(LearningJourneyChallengeQuestionMembership.position)
            )
            return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]

    async def get_questions_by_ids(
        self, question_ids: Sequence[str]
    ) -> dict[str, LearningJourneyQuestion]:
        if not question_ids:
            return {}
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneyQuestion).where(
                LearningJourneyQuestion.question_id.in_(question_ids)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return {row.question_id: row for row in rows}

    # --- Assignment / progress -----------------------------------------------

    async def ensure_assignment(
        self,
        *,
        app_user_id: str,
        journey_id: str,
        journey_version: int,
        assignment_id: str,
        challenge_ids: Sequence[str],
        now: datetime,
    ) -> LearningJourneyUserAssignment:
        """Idempotent: creates the assignment and every challenge's progress row at
        ``NOT_STARTED`` on first access, no-ops on every subsequent call."""
        async with self._sessionmaker() as session, session.begin():
            insert_assignment = (
                insert(LearningJourneyUserAssignment)
                .values(
                    assignment_id=assignment_id,
                    app_user_id=app_user_id,
                    journey_id=journey_id,
                    journey_version=journey_version,
                    status="IN_PROGRESS",
                    assigned_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["app_user_id", "journey_id"])
            )
            await session.execute(insert_assignment)

            existing = await session.execute(
                select(LearningJourneyUserAssignment).where(
                    LearningJourneyUserAssignment.app_user_id == app_user_id,
                    LearningJourneyUserAssignment.journey_id == journey_id,
                )
            )
            assignment = existing.scalar_one()

            if challenge_ids:
                insert_progress = (
                    insert(LearningJourneyUserChallengeProgress)
                    .values(
                        [
                            {
                                "assignment_id": assignment.assignment_id,
                                "challenge_id": challenge_id,
                                "status": "NOT_STARTED",
                                "is_progression_complete": False,
                                "total_attempts": 0,
                                "remediation_required": False,
                                "remediation_completed": False,
                            }
                            for challenge_id in challenge_ids
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["assignment_id", "challenge_id"])
                )
                await session.execute(insert_progress)

            return assignment

    async def get_assignment(
        self, *, app_user_id: str, journey_id: str
    ) -> LearningJourneyUserAssignment | None:
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneyUserAssignment).where(
                LearningJourneyUserAssignment.app_user_id == app_user_id,
                LearningJourneyUserAssignment.journey_id == journey_id,
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def list_progress(
        self, assignment_id: str
    ) -> dict[str, LearningJourneyUserChallengeProgress]:
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneyUserChallengeProgress).where(
                LearningJourneyUserChallengeProgress.assignment_id == assignment_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            return {row.challenge_id: row for row in rows}

    async def get_progress(
        self, *, assignment_id: str, challenge_id: str
    ) -> LearningJourneyUserChallengeProgress | None:
        async with self._sessionmaker() as session:
            return await session.get(
                LearningJourneyUserChallengeProgress, (assignment_id, challenge_id)
            )

    async def update_progress(
        self, *, assignment_id: str, challenge_id: str, **fields: Any
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneyUserChallengeProgress)
                .where(
                    LearningJourneyUserChallengeProgress.assignment_id == assignment_id,
                    LearningJourneyUserChallengeProgress.challenge_id == challenge_id,
                )
                .values(**fields)
            )

    # --- Sessions / attempts ---------------------------------------------------

    async def get_active_session(
        self, *, assignment_id: str, challenge_id: str, session_type: str
    ) -> LearningJourneySession | None:
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneySession).where(
                LearningJourneySession.assignment_id == assignment_id,
                LearningJourneySession.challenge_id == challenge_id,
                LearningJourneySession.session_type == session_type,
                LearningJourneySession.status == "IN_PROGRESS",
            )
            return (await session.execute(stmt)).scalars().first()

    async def create_session(self, session_row: LearningJourneySession) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(session_row)

    async def complete_session(self, session_id: str, *, now: datetime) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneySession)
                .where(LearningJourneySession.session_id == session_id)
                .values(status="COMPLETED", completed_at=now)
            )

    async def next_challenge_attempt_number(self, *, assignment_id: str, challenge_id: str) -> int:
        """Locks the progress row for the duration of the attempt-create transaction
        so two concurrent starts can't be assigned the same number."""
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                select(LearningJourneyUserChallengeProgress)
                .where(
                    LearningJourneyUserChallengeProgress.assignment_id == assignment_id,
                    LearningJourneyUserChallengeProgress.challenge_id == challenge_id,
                )
                .with_for_update()
            )
            result = await session.execute(
                select(LearningJourneyAttempt.challenge_attempt_number)
                .where(
                    LearningJourneyAttempt.assignment_id == assignment_id,
                    LearningJourneyAttempt.challenge_id == challenge_id,
                )
                .order_by(LearningJourneyAttempt.challenge_attempt_number.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            return (latest or 0) + 1

    async def create_attempt(
        self, attempt: LearningJourneyAttempt, questions: Sequence[LearningJourneyAttemptQuestion]
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(attempt)
            session.add_all(questions)

    async def get_attempt(self, attempt_id: str) -> LearningJourneyAttempt | None:
        async with self._sessionmaker() as session:
            return await session.get(LearningJourneyAttempt, attempt_id)

    async def list_attempt_questions(
        self, attempt_id: str
    ) -> Sequence[LearningJourneyAttemptQuestion]:
        async with self._sessionmaker() as session:
            stmt = (
                select(LearningJourneyAttemptQuestion)
                .where(LearningJourneyAttemptQuestion.attempt_id == attempt_id)
                .order_by(LearningJourneyAttemptQuestion.position)
            )
            return (await session.execute(stmt)).scalars().all()

    async def get_attempt_question(
        self, *, attempt_id: str, question_id: str
    ) -> LearningJourneyAttemptQuestion | None:
        async with self._sessionmaker() as session:
            return await session.get(LearningJourneyAttemptQuestion, (attempt_id, question_id))

    async def grade_attempt_question(
        self,
        *,
        attempt_id: str,
        question_id: str,
        selected_option_keys: list[str],
        selected_option_ids: list[str],
        is_correct: bool,
        duration_ms: int | None,
        now: datetime,
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneyAttemptQuestion)
                .where(
                    LearningJourneyAttemptQuestion.attempt_id == attempt_id,
                    LearningJourneyAttemptQuestion.question_id == question_id,
                )
                .values(
                    response_status="GRADED",
                    selected_option_keys=selected_option_keys,
                    selected_option_ids=selected_option_ids,
                    is_correct=is_correct,
                    duration_ms=duration_ms,
                    answered_at=now,
                )
            )

    async def mark_attempt_submitted(
        self,
        *,
        attempt_id: str,
        correct_count: int,
        incorrect_count: int,
        score_percentage: float,
        duration_ms: int,
        now: datetime,
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneyAttempt)
                .where(LearningJourneyAttempt.attempt_id == attempt_id)
                .values(
                    status="SUBMITTED",
                    correct_count=correct_count,
                    incorrect_count=incorrect_count,
                    score_percentage=score_percentage,
                    duration_ms=duration_ms,
                    submitted_at=now,
                )
            )

    async def list_attempts(
        self, *, assignment_id: str, challenge_id: str, limit: int
    ) -> Sequence[LearningJourneyAttempt]:
        async with self._sessionmaker() as session:
            stmt = (
                select(LearningJourneyAttempt)
                .where(
                    LearningJourneyAttempt.assignment_id == assignment_id,
                    LearningJourneyAttempt.challenge_id == challenge_id,
                )
                .order_by(LearningJourneyAttempt.started_at.desc())
                .limit(limit)
            )
            return (await session.execute(stmt)).scalars().all()

    async def list_submitted_attempts_for_assignment(
        self, assignment_id: str
    ) -> Sequence[LearningJourneyAttempt]:
        """Every submitted attempt across every challenge — the raw material for
        streak/daily-challenge/week-calendar computation, which has no dedicated
        tracking table and is derived entirely from ``submitted_at`` timestamps."""
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneyAttempt).where(
                LearningJourneyAttempt.assignment_id == assignment_id,
                LearningJourneyAttempt.status == "SUBMITTED",
            )
            return (await session.execute(stmt)).scalars().all()

    # --- Remediation -----------------------------------------------------------

    async def get_remediation_by_source_attempt(
        self, source_attempt_id: str
    ) -> LearningJourneyRemediation | None:
        async with self._sessionmaker() as session:
            stmt = select(LearningJourneyRemediation).where(
                LearningJourneyRemediation.source_attempt_id == source_attempt_id
            )
            return (await session.execute(stmt)).scalars().first()

    async def create_remediation(self, remediation: LearningJourneyRemediation) -> None:
        async with self._sessionmaker() as session, session.begin():
            session.add(remediation)

    async def complete_remediation(self, *, attempt_id: str, now: datetime) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneyRemediation)
                .where(LearningJourneyRemediation.attempt_id == attempt_id)
                .values(status="COMPLETED", completed_at=now)
            )

    # --- Idempotency -------------------------------------------------------------

    async def claim_idempotency_key(
        self,
        *,
        app_user_id: str,
        endpoint: str,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
    ) -> LearningJourneyIdempotencyRecord | None:
        """Atomically claims the key. Returns ``None`` when this call claimed it (the
        caller should do the real work and then call ``store_idempotent_response``);
        returns the existing row when someone already claimed it (match the
        fingerprint to replay, or raise ``IdempotencyKeyReusedError`` on mismatch —
        the service layer's job, not this repository's)."""
        async with self._sessionmaker() as session, session.begin():
            stmt = (
                insert(LearningJourneyIdempotencyRecord)
                .values(
                    app_user_id=app_user_id,
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    response_status=0,
                    response_body={},
                    created_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["app_user_id", "endpoint", "idempotency_key"]
                )
                .returning(LearningJourneyIdempotencyRecord)
            )
            claimed = (await session.execute(stmt)).scalar_one_or_none()
            if claimed is not None:
                return None

            existing = await session.get(
                LearningJourneyIdempotencyRecord, (app_user_id, endpoint, idempotency_key)
            )
            return existing

    async def store_idempotent_response(
        self,
        *,
        app_user_id: str,
        endpoint: str,
        idempotency_key: str,
        response_status: int,
        response_body: dict[str, Any],
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(LearningJourneyIdempotencyRecord)
                .where(
                    LearningJourneyIdempotencyRecord.app_user_id == app_user_id,
                    LearningJourneyIdempotencyRecord.endpoint == endpoint,
                    LearningJourneyIdempotencyRecord.idempotency_key == idempotency_key,
                )
                .values(response_status=response_status, response_body=response_body)
            )
