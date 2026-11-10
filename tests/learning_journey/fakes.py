"""In-memory stand-in for ``LearningJourneyRepository`` — same method signatures,
plain dicts instead of Postgres, so the service/state-machine logic can be tested
fast and without Docker. Content tables are seeded from the exact bundled JSON
(migration 0002's own source), so tests exercise the real dataset shape.

Rows are the real SQLAlchemy model instances from ``learning_journey.models``,
constructed directly and never attached to a session — their ``Mapped``/
``mapped_column`` fields behave as plain attributes when unattached, so this avoids
duplicating every field in a second, parallel set of fake dataclasses.
"""

import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from fordona_connect.learning_journey.content import (
    ChallengeContent,
    JourneyContent,
    MilestoneContent,
    QuestionContent,
)
from fordona_connect.learning_journey.models import (
    LearningJourneyAttempt,
    LearningJourneyAttemptQuestion,
    LearningJourneyIdempotencyRecord,
    LearningJourneyRemediation,
    LearningJourneySession,
    LearningJourneyUserAssignment,
    LearningJourneyUserChallengeProgress,
)

# The retired mock catalogue, kept as a realistic fixture: production content now
# comes from Boost (``learning_journey.boost_content``).
_SEED_PATH = Path(__file__).resolve().parent / "fixtures" / "learning_journey_mock_db.json"


def _row(cls: Any, source: dict[str, Any]) -> Any:
    """Build a content dataclass from a seed row, ignoring the seed's extra fields."""
    fields = set(cls.__dataclass_fields__)
    return cls(**{k: v for k, v in source.items() if k in fields})


class FakeLearningJourneyRepository:
    def __init__(self) -> None:
        data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))

        self.templates: dict[str, JourneyContent] = {
            t["journey_id"]: _row(JourneyContent, t) for t in data["journey_templates"]
        }
        self.milestones: dict[str, MilestoneContent] = {
            m["milestone_id"]: _row(MilestoneContent, m) for m in data["milestones"]
        }
        self.challenges: dict[str, ChallengeContent] = {
            c["challenge_id"]: _row(ChallengeContent, c) for c in data["challenges"]
        }
        self.questions: dict[str, QuestionContent] = {
            q["question_id"]: _row(QuestionContent, q) for q in data["questions"]
        }
        # challenge_id -> [(question_id, position), ...] ordered
        self.memberships: dict[str, list[tuple[str, int]]] = {}
        for row in data["challenge_question_memberships"]:
            self.memberships.setdefault(row["challenge_id"], []).append(
                (row["question_id"], row["position"])
            )
        for rows in self.memberships.values():
            rows.sort(key=lambda r: r[1])

        self.assignments: dict[tuple[str, str], LearningJourneyUserAssignment] = {}
        self.progress: dict[tuple[str, str], LearningJourneyUserChallengeProgress] = {}
        self.sessions: dict[str, LearningJourneySession] = {}
        self.attempts: dict[str, LearningJourneyAttempt] = {}
        self.attempt_questions: dict[tuple[str, str], LearningJourneyAttemptQuestion] = {}
        self.remediations: dict[str, LearningJourneyRemediation] = {}
        self.idempotency: dict[tuple[str, str, str], LearningJourneyIdempotencyRecord] = {}

    # --- Content (also the service's content source) ---------------------------

    async def journey_id(self) -> str | None:
        return next(iter(self.templates), None)

    async def free_milestone_id(self) -> str | None:
        journey_id = await self.journey_id()
        milestones = await self.list_milestones(journey_id) if journey_id else []
        return milestones[0].milestone_id if milestones else None

    async def get_journey_template(self, journey_id: str) -> JourneyContent | None:
        return self.templates.get(journey_id)

    async def list_milestones(self, journey_id: str) -> Sequence[MilestoneContent]:
        rows = [m for m in self.milestones.values() if m.journey_id == journey_id]
        return sorted(rows, key=lambda m: m.position)

    async def get_milestone(self, milestone_id: str) -> MilestoneContent | None:
        return self.milestones.get(milestone_id)

    async def list_challenges_for_milestone(self, milestone_id: str) -> Sequence[ChallengeContent]:
        rows = [c for c in self.challenges.values() if c.milestone_id == milestone_id]
        return sorted(rows, key=lambda c: c.position)

    async def get_challenge(self, challenge_id: str) -> ChallengeContent | None:
        return self.challenges.get(challenge_id)

    async def list_questions_for_challenge(
        self, challenge_id: str
    ) -> Sequence[tuple[QuestionContent, int]]:
        return [
            (self.questions[question_id], position)
            for question_id, position in self.memberships.get(challenge_id, [])
        ]

    async def get_questions_by_ids(self, question_ids: Sequence[str]) -> dict[str, QuestionContent]:
        return {qid: self.questions[qid] for qid in question_ids if qid in self.questions}

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
        key = (app_user_id, journey_id)
        if key not in self.assignments:
            # Mirror the table's primary key: Postgres rejects a reused assignment_id
            # even though ON CONFLICT targets (app_user_id, journey_id).
            if any(a.assignment_id == assignment_id for a in self.assignments.values()):
                raise ValueError(f"duplicate assignment_id {assignment_id}")
            self.assignments[key] = LearningJourneyUserAssignment(
                assignment_id=assignment_id,
                app_user_id=app_user_id,
                journey_id=journey_id,
                journey_version=journey_version,
                status="IN_PROGRESS",
                assigned_at=now,
                updated_at=now,
            )
            for challenge_id in challenge_ids:
                self.progress[(assignment_id, challenge_id)] = LearningJourneyUserChallengeProgress(
                    assignment_id=assignment_id,
                    challenge_id=challenge_id,
                    status="NOT_STARTED",
                    is_progression_complete=False,
                    total_attempts=0,
                    remediation_required=False,
                    remediation_completed=False,
                )
        return self.assignments[key]

    async def get_assignment(
        self, *, app_user_id: str, journey_id: str
    ) -> LearningJourneyUserAssignment | None:
        return self.assignments.get((app_user_id, journey_id))

    async def list_progress(
        self, assignment_id: str
    ) -> dict[str, LearningJourneyUserChallengeProgress]:
        return {
            challenge_id: row
            for (aid, challenge_id), row in self.progress.items()
            if aid == assignment_id
        }

    async def get_progress(
        self, *, assignment_id: str, challenge_id: str
    ) -> LearningJourneyUserChallengeProgress | None:
        return self.progress.get((assignment_id, challenge_id))

    async def update_progress(
        self, *, assignment_id: str, challenge_id: str, **fields: Any
    ) -> None:
        row = self.progress[(assignment_id, challenge_id)]
        for key, value in fields.items():
            setattr(row, key, value)

    # --- Sessions / attempts ---------------------------------------------------

    async def get_active_session(
        self, *, assignment_id: str, challenge_id: str, session_type: str
    ) -> LearningJourneySession | None:
        for session in self.sessions.values():
            if (
                session.assignment_id == assignment_id
                and session.challenge_id == challenge_id
                and session.session_type == session_type
                and session.status == "IN_PROGRESS"
            ):
                return session
        return None

    async def create_session(self, session_row: LearningJourneySession) -> None:
        self.sessions[session_row.session_id] = session_row

    async def complete_session(self, session_id: str, *, now: datetime) -> None:
        session = self.sessions[session_id]
        session.status = "COMPLETED"
        session.completed_at = now

    async def next_challenge_attempt_number(self, *, assignment_id: str, challenge_id: str) -> int:
        numbers = [
            a.challenge_attempt_number
            for a in self.attempts.values()
            if a.assignment_id == assignment_id and a.challenge_id == challenge_id
        ]
        return (max(numbers) if numbers else 0) + 1

    async def create_attempt(
        self, attempt: LearningJourneyAttempt, questions: Sequence[LearningJourneyAttemptQuestion]
    ) -> None:
        self.attempts[attempt.attempt_id] = attempt
        for question in questions:
            self.attempt_questions[(question.attempt_id, question.question_id)] = question

    async def get_attempt(self, attempt_id: str) -> LearningJourneyAttempt | None:
        return self.attempts.get(attempt_id)

    async def list_attempt_questions(
        self, attempt_id: str
    ) -> Sequence[LearningJourneyAttemptQuestion]:
        rows = [v for (aid, _), v in self.attempt_questions.items() if aid == attempt_id]
        return sorted(rows, key=lambda r: r.position)

    async def get_attempt_question(
        self, *, attempt_id: str, question_id: str
    ) -> LearningJourneyAttemptQuestion | None:
        return self.attempt_questions.get((attempt_id, question_id))

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
        row = self.attempt_questions[(attempt_id, question_id)]
        row.response_status = "GRADED"
        row.selected_option_keys = selected_option_keys
        row.selected_option_ids = selected_option_ids
        row.is_correct = is_correct
        row.duration_ms = duration_ms
        row.answered_at = now

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
        attempt = self.attempts[attempt_id]
        attempt.status = "SUBMITTED"
        attempt.correct_count = correct_count
        attempt.incorrect_count = incorrect_count
        attempt.score_percentage = score_percentage
        attempt.duration_ms = duration_ms
        attempt.submitted_at = now

    async def list_attempts(
        self, *, assignment_id: str, challenge_id: str, limit: int
    ) -> Sequence[LearningJourneyAttempt]:
        rows = [
            a
            for a in self.attempts.values()
            if a.assignment_id == assignment_id and a.challenge_id == challenge_id
        ]
        rows.sort(key=lambda a: a.started_at, reverse=True)
        return rows[:limit]

    async def list_submitted_attempts_for_assignment(
        self, assignment_id: str
    ) -> Sequence[LearningJourneyAttempt]:
        return [
            a
            for a in self.attempts.values()
            if a.assignment_id == assignment_id and a.status == "SUBMITTED"
        ]

    # --- Remediation -----------------------------------------------------------

    async def get_remediation_by_source_attempt(
        self, source_attempt_id: str
    ) -> LearningJourneyRemediation | None:
        for remediation in self.remediations.values():
            if remediation.source_attempt_id == source_attempt_id:
                return remediation
        return None

    async def create_remediation(self, remediation: LearningJourneyRemediation) -> None:
        self.remediations[remediation.remediation_id] = remediation

    async def complete_remediation(self, *, attempt_id: str, now: datetime) -> None:
        for remediation in self.remediations.values():
            if remediation.attempt_id == attempt_id:
                remediation.status = "COMPLETED"
                remediation.completed_at = now

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
        key = (app_user_id, endpoint, idempotency_key)
        if key in self.idempotency:
            return self.idempotency[key]
        self.idempotency[key] = LearningJourneyIdempotencyRecord(
            app_user_id=app_user_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            response_status=0,
            response_body={},
            created_at=now,
        )
        return None

    async def store_idempotent_response(
        self,
        *,
        app_user_id: str,
        endpoint: str,
        idempotency_key: str,
        response_status: int,
        response_body: dict[str, Any],
    ) -> None:
        record = self.idempotency[(app_user_id, endpoint, idempotency_key)]
        record.response_status = response_status
        record.response_body = deepcopy(response_body)


class FakeSubscriptions:
    """A ``SubscriptionSource``: ``subscribed=True`` by default so tests that are not
    about the paywall (most of them) need not care about it."""

    def __init__(self, *, subscribed: bool = True) -> None:
        self.subscribed = subscribed
        self.calls: list[str] = []

    async def is_subscribed(self, learner_id: str) -> bool:
        self.calls.append(learner_id)
        return self.subscribed
