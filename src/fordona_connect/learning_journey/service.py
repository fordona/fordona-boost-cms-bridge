"""Orchestration for the Learning Journey contract: state machine, remediation rules,
idempotency, option shuffling, next-challenge computation.

Depends on ``LearningJourneyRepository`` through plain duck-typing (constructor
injection) so tests can substitute an in-memory fake without a formal interface.

**Entitlement is the one deliberate exception to this feature's BFF-only isolation**:
the free tier is "the first milestone, all its challenges"; everything past it needs
an active subscription, and subscription state lives only in fordona-engine. Rather
than duplicating that state here, ``LearningJourneyService`` calls the engine's own
existing *public* ``GET /v1/theory/subscription/status`` endpoint (forwarding the
learner's own JWT — the same ``forward_learner_token`` pattern already used for
Boost), via the same ``EngineClient`` the theory module already uses. A failed or
unreachable entitlement check **fails closed** (treated as not entitled) — a paywall
that silently opens on an engine hiccup is a worse bug than one that's briefly too
strict.
"""

import hashlib
import json
import random
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.core.errors import AppError
from fordona_connect.core.logging import get_logger
from fordona_connect.learning_journey.errors import (
    ActiveAttemptExistsError,
    AnswerAlreadyFinalizedError,
    AttemptIncompleteError,
    AttemptNotActiveError,
    ChallengeLockedError,
    IdempotencyKeyReusedError,
    NotFoundError,
    RemediationNotEligibleError,
    RemediationRequiredError,
    SubscriptionRequiredError,
    ValidationError,
)
from fordona_connect.learning_journey.models import (
    LearningJourneyAttempt,
    LearningJourneyAttemptQuestion,
    LearningJourneyRemediation,
    LearningJourneySession,
)
from fordona_connect.learning_journey.repository import LearningJourneyRepository
from fordona_connect.learning_journey.schemas import (
    AccessState,
    AnswerFeedbackOut,
    AttemptDetailOut,
    AttemptHistoryOut,
    AttemptProgress,
    AttemptQuestionOut,
    AttemptSummaryOut,
    ChallengeDetailOut,
    ChallengeProgressSummary,
    ChallengeSummaryOut,
    ChallengeUserState,
    ContinueChallenge,
    CorrectAnswerOut,
    CurrentPosition,
    DailyChallenge,
    HomeOut,
    HomeTabs,
    JourneyProgress,
    JourneyStats,
    LearningJourneyOut,
    MilestoneDetailOut,
    MilestoneProgress,
    MilestoneStats,
    MilestoneSummaryOut,
    OptionOut,
    QuestionPreviewOut,
    QuestionResponseOut,
    ReadinessOut,
    RemediationCreateOut,
    RemediationCreateProgression,
    RemediationGeneration,
    RemediationState,
    Streak,
    SubmitProgression,
    SubmitRemediationState,
    SubmitResult,
    SubmitResultOut,
    TabState,
    UpNextChallenge,
    Week,
    WeekDay,
)

_JOURNEY_ID = "journey_001"
_MAX_MANDATORY_REMEDIATION_ROUNDS = 1
# Hardcoded — no daily-challenge configuration exists anywhere; matches the mobile
# mockup's "Complete 3 Lessons" literally. "Lessons" here means challenges.
_DAILY_CHALLENGE_TARGET = 3
# The free tier: this milestone and all its challenges, no subscription needed.
# Confirmed against the seed: every challenge in ms_001 is currently MISSING_MEDIA,
# so the free tier is unattemptable end-to-end until real media lands — a content
# gap, not a bug in this gate.
_FREE_MILESTONE_ID = "ms_001"

log = get_logger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _fingerprint(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LearningJourneyService:
    def __init__(
        self,
        repository: LearningJourneyRepository,
        engine_client: EngineClient,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._engine = engine_client
        self._now = now_fn or (lambda: datetime.now(UTC))

    @staticmethod
    def _is_content_ready(challenge: Any) -> bool:
        return bool(challenge.content_readiness.get("status") == "READY")

    # --- Entitlement -----------------------------------------------------------

    @staticmethod
    def _is_free_milestone(milestone_id: str) -> bool:
        return milestone_id == _FREE_MILESTONE_ID

    async def _is_subscribed(self, app_user_id: str) -> bool:
        try:
            response = await self._engine.get("/v1/theory/subscription/status")
        except AppError as exc:
            log.warning(
                "learning_journey_entitlement_check_failed_closed",
                app_user_id=app_user_id,
                error=repr(exc),
            )
            return False
        return bool(response.data.get("isActive", False))

    async def _assert_entitled(self, app_user_id: str, milestone_id: str) -> None:
        if self._is_free_milestone(milestone_id):
            return
        if not await self._is_subscribed(app_user_id):
            raise SubscriptionRequiredError()

    # --- Assignment bootstrap ------------------------------------------------

    async def _ensure_assignment(self, app_user_id: str) -> str:
        template = await self._repo.get_journey_template(_JOURNEY_ID)
        if template is None:  # pragma: no cover - seed always present
            raise NotFoundError("No learning journey is configured.")
        milestones = await self._repo.list_milestones(_JOURNEY_ID)
        challenge_ids: list[str] = []
        for milestone in milestones:
            challenges = await self._repo.list_challenges_for_milestone(milestone.milestone_id)
            challenge_ids.extend(c.challenge_id for c in challenges)

        assignment = await self._repo.ensure_assignment(
            app_user_id=app_user_id,
            journey_id=_JOURNEY_ID,
            journey_version=template.version,
            assignment_id=f"assignment_{hashlib.sha256(app_user_id.encode()).hexdigest()[:24]}",
            challenge_ids=challenge_ids,
            now=self._now(),
        )
        return assignment.assignment_id

    # --- Idempotency -----------------------------------------------------------

    async def _with_idempotency(
        self,
        *,
        app_user_id: str,
        endpoint: str,
        idempotency_key: str,
        request_body: dict[str, Any],
        compute: Callable[[], Any],
    ) -> tuple[int, dict[str, Any]]:
        fingerprint = _fingerprint(request_body)
        existing = await self._repo.claim_idempotency_key(
            app_user_id=app_user_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            now=self._now(),
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError()
            if existing.response_status != 0:
                return existing.response_status, existing.response_body
            # A previous call claimed this key but crashed before storing a result
            # (known limitation — see repository docstring). Recompute and overwrite
            # rather than leaving the caller stuck forever.

        status, body = await compute()
        await self._repo.store_idempotent_response(
            app_user_id=app_user_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            response_status=status,
            response_body=body,
        )
        return status, body

    # --- GET /v1/learning-journey ------------------------------------------------

    async def get_learning_journey(self, app_user_id: str) -> LearningJourneyOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        template = await self._repo.get_journey_template(_JOURNEY_ID)
        assert template is not None
        milestones = await self._repo.list_milestones(_JOURNEY_ID)
        progress_by_challenge = await self._repo.list_progress(assignment_id)
        subscribed = await self._is_subscribed(app_user_id)

        milestone_outs: list[MilestoneSummaryOut] = []
        completed_milestones = 0
        completed_challenges_total = 0
        total_challenges_total = 0
        current_position: CurrentPosition | None = None
        previous_milestone_complete = True

        for milestone in milestones:
            challenges = await self._repo.list_challenges_for_milestone(milestone.milestone_id)
            completed = sum(
                1 for c in challenges if progress_by_challenge[c.challenge_id].status == "COMPLETED"
            )
            total = len(challenges)
            pct = round((completed / total) * 100, 2) if total else 0.0
            status = (
                "COMPLETED"
                if completed == total and total > 0
                else ("IN_PROGRESS" if completed > 0 else "NOT_STARTED")
            )
            not_entitled = not subscribed and not self._is_free_milestone(milestone.milestone_id)
            is_locked = not_entitled or not previous_milestone_complete
            if not_entitled:
                reason = "SUBSCRIPTION_REQUIRED"
            elif is_locked:
                reason = "PREREQUISITE_NOT_MET"
            else:
                reason = None
            milestone_outs.append(
                MilestoneSummaryOut(
                    milestone_id=milestone.milestone_id,
                    journey_id=milestone.journey_id,
                    position=milestone.position,
                    title=milestone.title,
                    description=milestone.description,
                    challenge_count=milestone.challenge_count,
                    question_count=milestone.question_count,
                    progress=MilestoneProgress(
                        completed_challenges=completed,
                        total_challenges=total,
                        completion_percentage=pct,
                        status=status,
                    ),
                    access=AccessState(is_locked=is_locked, reason=reason),
                )
            )
            if status == "COMPLETED":
                completed_milestones += 1
            completed_challenges_total += completed
            total_challenges_total += total
            previous_milestone_complete = status == "COMPLETED"

            if current_position is None:
                for challenge in challenges:
                    if progress_by_challenge[challenge.challenge_id].status != "COMPLETED":
                        current_position = CurrentPosition(
                            milestone_id=milestone.milestone_id, challenge_id=challenge.challenge_id
                        )
                        break

        overall_pct = (
            round((completed_challenges_total / total_challenges_total) * 100, 2)
            if total_challenges_total
            else 0.0
        )

        return LearningJourneyOut(
            journey_id=template.journey_id,
            assignment_id=assignment_id,
            version=template.version,
            title=template.title,
            description=template.description,
            status="IN_PROGRESS" if current_position else "COMPLETED",
            stats=JourneyStats(**template.stats),
            progress=JourneyProgress(
                completed_milestones=completed_milestones,
                completed_challenges=completed_challenges_total,
                total_challenges=total_challenges_total,
                completion_percentage=overall_pct,
            ),
            current_position=current_position,
            milestones=milestone_outs,
            updated_at=self._now(),
        )

    # --- GET /v1/milestones -------------------------------------------------------

    async def get_milestone_detail(self, app_user_id: str, milestone_id: str) -> MilestoneDetailOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        milestone = await self._repo.get_milestone(milestone_id)
        if milestone is None or milestone.journey_id != _JOURNEY_ID:
            raise NotFoundError("Milestone not found.")

        progress_by_challenge = await self._repo.list_progress(assignment_id)
        challenges = await self._repo.list_challenges_for_milestone(milestone_id)
        not_entitled = not self._is_free_milestone(milestone_id) and not await self._is_subscribed(
            app_user_id
        )

        challenge_outs: list[ChallengeSummaryOut] = []
        previous_complete = True
        completed = 0
        for challenge in challenges:
            progress = progress_by_challenge[challenge.challenge_id]
            is_locked = not_entitled or not previous_complete
            reason = (
                "SUBSCRIPTION_REQUIRED"
                if not_entitled
                else ("PREREQUISITE_NOT_MET" if is_locked else None)
            )
            challenge_outs.append(
                ChallengeSummaryOut(
                    challenge_id=challenge.challenge_id,
                    milestone_id=challenge.milestone_id,
                    position=challenge.position,
                    display_code=challenge.display_code,
                    title=challenge.title,
                    description=challenge.description,
                    estimated_minutes=challenge.estimated_minutes,
                    question_count=challenge.question_count,
                    difficulty_distribution=challenge.difficulty_distribution,
                    progress=ChallengeProgressSummary(
                        status=progress.status,
                        best_full_attempt_score_percentage=(
                            float(progress.best_full_attempt_score_percentage)
                            if progress.best_full_attempt_score_percentage is not None
                            else None
                        ),
                    ),
                    access=AccessState(is_locked=is_locked, reason=reason),
                    is_content_ready=self._is_content_ready(challenge),
                )
            )
            if progress.status == "COMPLETED":
                completed += 1
            previous_complete = progress.status == "COMPLETED"

        total = len(challenges)
        pct = round((completed / total) * 100, 2) if total else 0.0
        milestone_status = (
            "COMPLETED"
            if completed == total and total > 0
            else ("IN_PROGRESS" if completed > 0 else "NOT_STARTED")
        )

        return MilestoneDetailOut(
            milestone_id=milestone.milestone_id,
            journey_id=milestone.journey_id,
            position=milestone.position,
            title=milestone.title,
            description=milestone.description,
            stats=MilestoneStats(
                challenge_count=milestone.challenge_count,
                question_count=milestone.question_count,
                difficulty_distribution=milestone.difficulty_distribution,
            ),
            progress=MilestoneProgress(
                completed_challenges=completed,
                total_challenges=total,
                completion_percentage=pct,
                status=milestone_status,
            ),
            challenges=challenge_outs,
        )

    # --- GET /v1/challenges -------------------------------------------------------

    def _question_preview(self, question: Any, position: int) -> QuestionPreviewOut:
        options = [
            OptionOut(
                option_id=opt["option_id"],
                option_key=chr(ord("A") + idx),
                text=opt["text"],
                image_urls=opt.get("image_urls", []),
            )
            for idx, opt in enumerate(question.options)
        ]
        return QuestionPreviewOut(
            question_id=question.question_id,
            question_version=question.question_version,
            position=position,
            question_type=question.question_type,
            question_text=question.question_text,
            difficulty=question.difficulty,
            level=question.level,
            image_urls=question.image_urls,
            has_image_reference=question.has_image_reference,
            options=options,
            connected_chapters=question.connected_chapters,
            cms_row_numbers=question.cms_row_numbers,
        )

    async def _assert_challenge_unlocked(self, assignment_id: str, challenge: Any) -> None:
        if challenge.position <= 1:
            return
        siblings = await self._repo.list_challenges_for_milestone(challenge.milestone_id)
        previous = next((c for c in siblings if c.position == challenge.position - 1), None)
        if previous is None:
            return
        progress = await self._repo.get_progress(
            assignment_id=assignment_id, challenge_id=previous.challenge_id
        )
        if progress is None or progress.status != "COMPLETED":
            raise ChallengeLockedError()

    async def get_challenge_detail(self, app_user_id: str, challenge_id: str) -> ChallengeDetailOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        challenge = await self._repo.get_challenge(challenge_id)
        if challenge is None:
            raise NotFoundError("Challenge not found.")
        await self._assert_challenge_unlocked(assignment_id, challenge)
        await self._assert_entitled(app_user_id, challenge.milestone_id)

        questions = await self._repo.list_questions_for_challenge(challenge_id)
        progress = await self._repo.get_progress(
            assignment_id=assignment_id, challenge_id=challenge_id
        )
        assert progress is not None

        remediation_state: RemediationState | None = None
        if progress.remediation_required or progress.remediation_completed:
            remediation_row = None
            if progress.latest_attempt_id:
                remediation_row = await self._repo.get_remediation_by_source_attempt(
                    progress.latest_attempt_id
                )
            remediation_state = RemediationState(
                required=progress.remediation_required,
                completed=progress.remediation_completed,
                source_attempt_id=progress.latest_attempt_id,
                incorrect_question_count=(
                    remediation_row.generation_metadata.get("original_incorrect_count")
                    if remediation_row
                    else None
                ),
            )

        return ChallengeDetailOut(
            challenge_id=challenge.challenge_id,
            journey_id=challenge.journey_id,
            milestone_id=challenge.milestone_id,
            version=challenge.version,
            position=challenge.position,
            display_code=challenge.display_code,
            title=challenge.title,
            description=challenge.description,
            estimated_minutes=challenge.estimated_minutes,
            question_count=challenge.question_count,
            difficulty_distribution=challenge.difficulty_distribution,
            questions=[self._question_preview(q, pos) for q, pos in questions],
            user_state=ChallengeUserState(
                status=progress.status,
                is_progression_complete=progress.is_progression_complete,
                can_access_next_challenge=progress.is_progression_complete,
                total_attempts=progress.total_attempts,
                latest_attempt_id=progress.latest_attempt_id,
                active_session_id=progress.active_session_id,
                remediation=remediation_state,
            ),
            is_content_ready=self._is_content_ready(challenge),
        )

    # --- Freezing a question set (shared by start-attempt and remediation) -------

    def _freeze_questions(
        self,
        attempt_id: str,
        questions_with_position: list[tuple[Any, int]],
        *,
        source_type: str | None,
        rng: random.Random,
    ) -> tuple[list[LearningJourneyAttemptQuestion], list[AttemptQuestionOut]]:
        rows: list[LearningJourneyAttemptQuestion] = []
        outs: list[AttemptQuestionOut] = []
        for question, position in questions_with_position:
            shuffled = list(question.options)
            rng.shuffle(shuffled)
            option_order = [opt["option_id"] for opt in shuffled]
            labelled = [
                OptionOut(
                    option_id=opt["option_id"],
                    option_key=chr(ord("A") + idx),
                    text=opt["text"],
                    image_urls=opt.get("image_urls", []),
                )
                for idx, opt in enumerate(shuffled)
            ]
            rows.append(
                LearningJourneyAttemptQuestion(
                    attempt_id=attempt_id,
                    question_id=question.question_id,
                    question_version=question.question_version,
                    position=position,
                    option_order=option_order,
                    answer_key_snapshot=question.correct_answer,
                    question_content_snapshot={
                        "question_text": question.question_text,
                        "question_type": question.question_type,
                        "options": question.options,
                        "image_urls": question.image_urls,
                        "has_image_reference": question.has_image_reference,
                        "connected_chapters": question.connected_chapters,
                        "cms_row_numbers": question.cms_row_numbers,
                    },
                    source_type=source_type or "ORIGINAL",
                    source_question_id=question.question_id if source_type else None,
                    difficulty=question.difficulty,
                    level=question.level,
                    response_status="UNANSWERED",
                )
            )
            outs.append(
                AttemptQuestionOut(
                    question_id=question.question_id,
                    question_version=question.question_version,
                    position=position,
                    question_type=question.question_type,
                    question_text=question.question_text,
                    difficulty=question.difficulty,
                    level=question.level,
                    image_urls=question.image_urls,
                    has_image_reference=question.has_image_reference,
                    options=labelled,
                    connected_chapters=question.connected_chapters,
                    cms_row_numbers=question.cms_row_numbers,
                    source_type=source_type,
                    source_question_id=question.question_id if source_type else None,
                    response=None,
                )
            )
        return rows, outs

    # --- POST /v1/challenges/attempts ---------------------------------------------

    async def start_attempt(
        self,
        app_user_id: str,
        *,
        challenge_id: str,
        mode: str,
        idempotency_key: str,
        request_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        async def compute() -> tuple[int, dict[str, Any]]:
            assignment_id = await self._ensure_assignment(app_user_id)
            challenge = await self._repo.get_challenge(challenge_id)
            if challenge is None:
                raise NotFoundError("Challenge not found.")
            await self._assert_challenge_unlocked(assignment_id, challenge)
            await self._assert_entitled(app_user_id, challenge.milestone_id)
            # Readiness gate intentionally removed (2026-11-08): every ms_001 (free-tier)
            # challenge is permanently MISSING_MEDIA — the referenced images were never
            # captured/uploaded — so enforcing this would make the free tier unattemptable
            # end-to-end. `is_content_ready` is still surfaced to clients (see schemas.py)
            # so they can decide how to render a question whose images are absent.

            progress = await self._repo.get_progress(
                assignment_id=assignment_id, challenge_id=challenge_id
            )
            assert progress is not None

            if mode == "INITIAL":
                if progress.remediation_required and not progress.remediation_completed:
                    raise RemediationRequiredError()
                if progress.active_session_id is not None:
                    active = await self._repo.get_active_session(
                        assignment_id=assignment_id,
                        challenge_id=challenge_id,
                        session_type="PROGRESSION",
                    )
                    if active is not None:
                        raise ActiveAttemptExistsError()
            elif mode == "VOLUNTARY":
                if not progress.is_progression_complete:
                    raise ValidationError(
                        "Voluntary reattempts are only available after the challenge is completed."
                    )
            else:  # pragma: no cover - schema already restricts the literal
                raise ValidationError(f"Unknown mode {mode!r}.")

            questions = await self._repo.list_questions_for_challenge(challenge_id)
            now = self._now()
            attempt_id = _new_id("att")
            session_type = "PROGRESSION" if mode == "INITIAL" else "PRACTICE"

            session_row: LearningJourneySession | None = None
            if mode == "INITIAL":
                session_row = await self._repo.get_active_session(
                    assignment_id=assignment_id,
                    challenge_id=challenge_id,
                    session_type="PROGRESSION",
                )
            if session_row is None:
                session_id = _new_id("cs")
                session_row = LearningJourneySession(
                    session_id=session_id,
                    assignment_id=assignment_id,
                    app_user_id=app_user_id,
                    challenge_id=challenge_id,
                    session_type=session_type,
                    status="IN_PROGRESS",
                    started_at=now,
                )
                await self._repo.create_session(session_row)
            session_id = session_row.session_id

            challenge_attempt_number = await self._repo.next_challenge_attempt_number(
                assignment_id=assignment_id, challenge_id=challenge_id
            )
            attempt_rows, attempt_outs = self._freeze_questions(
                attempt_id,
                list(questions),
                source_type=None,
                rng=random.Random(),  # noqa: S311 - shuffling MCQ options, not a secret
            )
            attempt = LearningJourneyAttempt(
                attempt_id=attempt_id,
                session_id=session_id,
                assignment_id=assignment_id,
                app_user_id=app_user_id,
                challenge_id=challenge_id,
                attempt_number=1,
                challenge_attempt_number=challenge_attempt_number,
                attempt_type=mode,
                challenge_version=challenge.version,
                status="IN_PROGRESS",
                total_questions=len(attempt_rows),
                started_at=now,
            )
            await self._repo.create_attempt(attempt, attempt_rows)
            await self._repo.update_progress(
                assignment_id=assignment_id,
                challenge_id=challenge_id,
                status="IN_PROGRESS" if progress.status == "NOT_STARTED" else progress.status,
                active_session_id=session_id,
                latest_attempt_id=attempt_id,
                total_attempts=progress.total_attempts + 1,
            )

            out = AttemptDetailOut(
                session_id=session_id,
                attempt_id=attempt_id,
                attempt_number=1,
                challenge_attempt_number=challenge_attempt_number,
                attempt_type=mode,
                challenge_id=challenge_id,
                journey_id=challenge.journey_id,
                milestone_id=challenge.milestone_id,
                challenge_version=challenge.version,
                status="IN_PROGRESS",
                started_at=now,
                question_count=len(attempt_outs),
                answered_count=0,
                questions=attempt_outs,
            )
            envelope = {
                "success": True,
                "data": out.model_dump(mode="json", by_alias=True),
                "meta": {"schema_version": "1.0"},
            }
            return 201, envelope

        return await self._with_idempotency(
            app_user_id=app_user_id,
            endpoint="POST /v1/challenges/attempts",
            idempotency_key=idempotency_key,
            request_body=request_body,
            compute=compute,
        )

    # --- Reconstructing an already-frozen attempt from storage --------------------

    @staticmethod
    def _hydrate_attempt_question(row: LearningJourneyAttemptQuestion) -> AttemptQuestionOut:
        """Rebuilds the delivered shape from a persisted row's own frozen
        ``option_order``/``question_content_snapshot`` — never reshuffles. Used by
        both ``get_attempt`` and the "return existing remediation" path, so a repeat
        read always shows the exact order originally delivered (spec §7's own
        invariant: "a repeated GET must return the same order, not shuffle again")."""
        options = [
            OptionOut(
                option_id=option_id,
                option_key=chr(ord("A") + idx),
                text=next(
                    o["text"]
                    for o in row.question_content_snapshot["options"]
                    if o["option_id"] == option_id
                ),
                image_urls=next(
                    (
                        o.get("image_urls", [])
                        for o in row.question_content_snapshot["options"]
                        if o["option_id"] == option_id
                    ),
                    [],
                ),
            )
            for idx, option_id in enumerate(row.option_order)
        ]
        response = None
        if row.response_status == "GRADED":
            response = QuestionResponseOut(
                status="GRADED",
                selected_option_keys=row.selected_option_keys or [],
                selected_option_ids=row.selected_option_ids or [],
                is_correct=bool(row.is_correct),
                correct_option_ids=row.answer_key_snapshot["option_ids"],
                explanation=None,
                duration_ms=row.duration_ms,
            )
        snapshot = row.question_content_snapshot
        return AttemptQuestionOut(
            question_id=row.question_id,
            question_version=row.question_version,
            position=row.position,
            question_type=snapshot["question_type"],
            question_text=snapshot["question_text"],
            difficulty=row.difficulty,
            level=row.level,
            image_urls=snapshot.get("image_urls", []),
            has_image_reference=snapshot.get("has_image_reference", False),
            options=options,
            connected_chapters=snapshot.get("connected_chapters", []),
            cms_row_numbers=snapshot.get("cms_row_numbers", []),
            source_type=row.source_type,
            source_question_id=row.source_question_id,
            response=response,
        )

    # --- GET /v1/challenges/attempts/{id} ------------------------------------------

    async def get_attempt(self, app_user_id: str, attempt_id: str) -> AttemptDetailOut:
        attempt = await self._repo.get_attempt(attempt_id)
        if attempt is None or attempt.app_user_id != app_user_id:
            raise NotFoundError("Attempt not found.")
        challenge = await self._repo.get_challenge(attempt.challenge_id)
        assert challenge is not None
        rows = await self._repo.list_attempt_questions(attempt_id)

        outs = [self._hydrate_attempt_question(row) for row in rows]
        answered = sum(1 for row in rows if row.response_status == "GRADED")

        return AttemptDetailOut(
            session_id=attempt.session_id,
            attempt_id=attempt.attempt_id,
            attempt_number=attempt.attempt_number,
            challenge_attempt_number=attempt.challenge_attempt_number,
            attempt_type=attempt.attempt_type,
            challenge_id=attempt.challenge_id,
            journey_id=challenge.journey_id,
            milestone_id=challenge.milestone_id,
            challenge_version=attempt.challenge_version,
            status=attempt.status,
            started_at=attempt.started_at,
            question_count=attempt.total_questions,
            answered_count=answered,
            questions=outs,
        )

    # --- POST /v1/challenges/attempts/{id}/answers ---------------------------------

    async def answer(
        self,
        app_user_id: str,
        attempt_id: str,
        *,
        question_id: str,
        selected_option_keys: list[str],
        duration_ms: int | None,
        idempotency_key: str,
        request_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        async def compute() -> tuple[int, dict[str, Any]]:
            attempt = await self._repo.get_attempt(attempt_id)
            if attempt is None or attempt.app_user_id != app_user_id:
                raise NotFoundError("Attempt not found.")
            if attempt.status != "IN_PROGRESS":
                raise AttemptNotActiveError()
            row = await self._repo.get_attempt_question(
                attempt_id=attempt_id, question_id=question_id
            )
            if row is None:
                raise NotFoundError("Question not found in this attempt.")
            if row.response_status == "GRADED":
                raise AnswerAlreadyFinalizedError()

            option_by_key = dict(
                zip(
                    (chr(ord("A") + i) for i in range(len(row.option_order))),
                    row.option_order,
                    strict=False,
                )
            )
            selected_option_ids = [option_by_key[key] for key in selected_option_keys]
            correct_ids = set(row.answer_key_snapshot["option_ids"])
            is_correct = set(selected_option_ids) == correct_ids
            now = self._now()

            await self._repo.grade_attempt_question(
                attempt_id=attempt_id,
                question_id=question_id,
                selected_option_keys=selected_option_keys,
                selected_option_ids=selected_option_ids,
                is_correct=is_correct,
                duration_ms=duration_ms,
                now=now,
            )

            rows = await self._repo.list_attempt_questions(attempt_id)
            answered_count = sum(
                1 for r in rows if r.question_id == question_id or r.response_status == "GRADED"
            )
            total = len(rows)

            out = AnswerFeedbackOut(
                attempt_id=attempt_id,
                question_id=question_id,
                response_status="GRADED",
                selected_option_keys=selected_option_keys,
                selected_option_ids=selected_option_ids,
                is_correct=is_correct,
                correct_answer=CorrectAnswerOut(option_ids=list(correct_ids)),
                explanation=None,
                duration_ms=duration_ms,
                attempt_progress=AttemptProgress(
                    answered_count=answered_count,
                    total_questions=total,
                    remaining_count=total - answered_count,
                ),
            )
            envelope = {
                "success": True,
                "data": out.model_dump(mode="json", by_alias=True),
                "meta": {"schema_version": "1.0"},
            }
            return 200, envelope

        return await self._with_idempotency(
            app_user_id=app_user_id,
            endpoint=f"POST /v1/challenges/attempts/{attempt_id}/answers",
            idempotency_key=idempotency_key,
            request_body=request_body,
            compute=compute,
        )

    # --- POST /v1/challenges/attempts/{id}/submit -----------------------------------

    async def _compute_next_challenge_id(self, challenge: Any) -> str | None:
        siblings = await self._repo.list_challenges_for_milestone(challenge.milestone_id)
        same_milestone_next = next(
            (c for c in siblings if c.position == challenge.position + 1), None
        )
        if same_milestone_next is not None:
            return same_milestone_next.challenge_id
        milestone = await self._repo.get_milestone(challenge.milestone_id)
        assert milestone is not None
        all_milestones = await self._repo.list_milestones(milestone.journey_id)
        next_milestone = next(
            (m for m in all_milestones if m.position == milestone.position + 1), None
        )
        if next_milestone is None:
            return None
        next_challenges = await self._repo.list_challenges_for_milestone(
            next_milestone.milestone_id
        )
        first = next((c for c in next_challenges if c.position == 1), None)
        return first.challenge_id if first else None

    async def submit(
        self,
        app_user_id: str,
        attempt_id: str,
        *,
        idempotency_key: str,
        request_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        async def compute() -> tuple[int, dict[str, Any]]:
            attempt = await self._repo.get_attempt(attempt_id)
            if attempt is None or attempt.app_user_id != app_user_id:
                raise NotFoundError("Attempt not found.")
            if attempt.status != "IN_PROGRESS":
                raise AttemptNotActiveError()
            rows = await self._repo.list_attempt_questions(attempt_id)
            if any(r.response_status != "GRADED" for r in rows):
                raise AttemptIncompleteError()

            correct_count = sum(1 for r in rows if r.is_correct)
            incorrect_count = len(rows) - correct_count
            total = len(rows)
            score_pct = round((correct_count / total) * 100, 2) if total else 0.0
            # Attempt-level duration is the sum of each question's own duration_ms
            # (matches the spec's example numbers; flagged in the plan as an
            # assumption if a different formula was intended).
            duration_ms = sum(r.duration_ms or 0 for r in rows)
            incorrect_ids = [r.question_id for r in rows if not r.is_correct]
            now = self._now()

            await self._repo.mark_attempt_submitted(
                attempt_id=attempt_id,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                score_percentage=score_pct,
                duration_ms=duration_ms,
                now=now,
            )

            challenge = await self._repo.get_challenge(attempt.challenge_id)
            assert challenge is not None
            progress = await self._repo.get_progress(
                assignment_id=attempt.assignment_id, challenge_id=attempt.challenge_id
            )
            assert progress is not None

            remediation_required = False
            remediation_completed = progress.remediation_completed
            is_complete = progress.is_progression_complete
            status: str

            if attempt.attempt_type == "INITIAL":
                if correct_count == total:
                    status = "COMPLETED"
                    is_complete = True
                else:
                    status = "REMEDIATION_REQUIRED"
                    remediation_required = True
            elif attempt.attempt_type == "REMEDIATION":
                status = "COMPLETED"
                is_complete = True
                remediation_completed = True
                remediation_required = False
                await self._repo.complete_remediation(attempt_id=attempt_id, now=now)
            else:  # VOLUNTARY
                status = "COMPLETED"
                is_complete = True
                remediation_required = False
                best = progress.best_full_attempt_score_percentage
                if best is None or score_pct > float(best):
                    await self._repo.update_progress(
                        assignment_id=attempt.assignment_id,
                        challenge_id=attempt.challenge_id,
                        best_full_attempt_score_percentage=score_pct,
                    )

            if attempt.attempt_type != "VOLUNTARY":
                best = progress.best_full_attempt_score_percentage
                update_fields: dict[str, Any] = {
                    "status": status,
                    "is_progression_complete": is_complete,
                    "remediation_required": remediation_required,
                    "remediation_completed": remediation_completed,
                }
                if attempt.attempt_type == "INITIAL" and (best is None or score_pct > float(best)):
                    update_fields["best_full_attempt_score_percentage"] = score_pct
                await self._repo.update_progress(
                    assignment_id=attempt.assignment_id,
                    challenge_id=attempt.challenge_id,
                    **update_fields,
                )

            if status == "COMPLETED":
                await self._repo.complete_session(attempt.session_id, now=now)

            next_challenge_id = (
                await self._compute_next_challenge_id(challenge) if is_complete else None
            )

            out = SubmitResultOut(
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                attempt_number=attempt.attempt_number,
                challenge_attempt_number=attempt.challenge_attempt_number,
                attempt_type=attempt.attempt_type,
                challenge_id=attempt.challenge_id,
                status="SUBMITTED",
                result=SubmitResult(
                    total_questions=total,
                    correct_count=correct_count,
                    incorrect_count=incorrect_count,
                    score_percentage=score_pct,
                    duration_ms=duration_ms,
                    incorrect_question_ids=incorrect_ids,
                ),
                remediation=SubmitRemediationState(
                    required=remediation_required,
                    completed=remediation_completed,
                    source_attempt_id=attempt.attempt_id if remediation_required else None,
                    incorrect_question_count=len(incorrect_ids) if remediation_required else None,
                    remaining_mandatory_rounds=(
                        _MAX_MANDATORY_REMEDIATION_ROUNDS if remediation_required else 0
                    ),
                ),
                progression=SubmitProgression(
                    status=status,
                    is_progression_complete=is_complete,
                    can_access_next_challenge=is_complete,
                    next_challenge_id=next_challenge_id,
                ),
                submitted_at=now,
            )
            envelope = {
                "success": True,
                "data": out.model_dump(mode="json", by_alias=True),
                "meta": {"schema_version": "1.0"},
            }
            return 200, envelope

        return await self._with_idempotency(
            app_user_id=app_user_id,
            endpoint=f"POST /v1/challenges/attempts/{attempt_id}/submit",
            idempotency_key=idempotency_key,
            request_body=request_body,
            compute=compute,
        )

    # --- GET /v1/challenges/attempts (history) --------------------------------------

    async def list_attempts(
        self, app_user_id: str, *, challenge_id: str, limit: int
    ) -> AttemptHistoryOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        attempts = await self._repo.list_attempts(
            assignment_id=assignment_id, challenge_id=challenge_id, limit=limit
        )
        items = [
            AttemptSummaryOut(
                session_id=a.session_id,
                attempt_id=a.attempt_id,
                attempt_number=a.attempt_number,
                challenge_attempt_number=a.challenge_attempt_number,
                attempt_type=a.attempt_type,
                status=a.status,
                total_questions=a.total_questions,
                correct_count=a.correct_count,
                score_percentage=(
                    float(a.score_percentage) if a.score_percentage is not None else None
                ),
                submitted_at=a.submitted_at,
            )
            for a in attempts
        ]
        return AttemptHistoryOut(challenge_id=challenge_id, items=items, next_cursor=None)

    # --- POST /v1/challenges/remediation ----------------------------------------------

    async def create_remediation(
        self,
        app_user_id: str,
        *,
        challenge_id: str,
        source_attempt_id: str,
        idempotency_key: str,
        request_body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        async def compute() -> tuple[int, dict[str, Any]]:
            source = await self._repo.get_attempt(source_attempt_id)
            if (
                source is None
                or source.app_user_id != app_user_id
                or source.challenge_id != challenge_id
            ):
                raise NotFoundError("Source attempt not found.")
            if source.attempt_type != "INITIAL" or source.status != "SUBMITTED":
                raise ValidationError("The source attempt is not eligible for remediation.")
            if not source.incorrect_count:
                raise ValidationError("The source attempt has no incorrect questions.")

            challenge = await self._repo.get_challenge(challenge_id)
            assert challenge is not None

            existing = await self._repo.get_remediation_by_source_attempt(source_attempt_id)
            if existing is not None:
                if existing.status != "IN_PROGRESS":
                    raise RemediationNotEligibleError()
                attempt = await self._repo.get_attempt(existing.attempt_id)
                assert attempt is not None
                rows = await self._repo.list_attempt_questions(existing.attempt_id)
                outs = [self._hydrate_attempt_question(row) for row in rows]
                return 200, self._remediation_envelope(
                    existing, attempt, outs, challenge_id, challenge.milestone_id
                )

            source_rows = await self._repo.list_attempt_questions(source_attempt_id)
            incorrect_rows = [r for r in source_rows if not r.is_correct]
            questions_by_id = await self._repo.get_questions_by_ids(
                [r.question_id for r in incorrect_rows]
            )
            questions_with_position = [
                (questions_by_id[r.question_id], idx + 1) for idx, r in enumerate(incorrect_rows)
            ]

            now = self._now()
            attempt_id = _new_id("att")
            remediation_id = _new_id("rem")
            attempt_rows, outs = self._freeze_questions(
                attempt_id,
                questions_with_position,
                source_type="ORIGINAL_INCORRECT",
                rng=random.Random(),  # noqa: S311 - shuffling MCQ options, not a secret
            )
            challenge_attempt_number = await self._repo.next_challenge_attempt_number(
                assignment_id=source.assignment_id, challenge_id=challenge_id
            )
            attempt = LearningJourneyAttempt(
                attempt_id=attempt_id,
                session_id=source.session_id,
                assignment_id=source.assignment_id,
                app_user_id=app_user_id,
                challenge_id=challenge_id,
                attempt_number=2,
                challenge_attempt_number=challenge_attempt_number,
                attempt_type="REMEDIATION",
                challenge_version=source.challenge_version,
                status="IN_PROGRESS",
                total_questions=len(attempt_rows),
                started_at=now,
            )
            await self._repo.create_attempt(attempt, attempt_rows)
            remediation = LearningJourneyRemediation(
                remediation_id=remediation_id,
                session_id=source.session_id,
                source_attempt_id=source_attempt_id,
                attempt_id=attempt_id,
                strategy="INCORRECT_ONLY",
                generation_metadata={
                    "strategy": "INCORRECT_ONLY",
                    "similarity_enabled": False,
                    "original_incorrect_count": len(incorrect_rows),
                    "similar_question_count": 0,
                    "total_questions": len(incorrect_rows),
                    "fallback_used": False,
                },
                status="IN_PROGRESS",
                created_at=now,
            )
            await self._repo.create_remediation(remediation)
            await self._repo.update_progress(
                assignment_id=source.assignment_id,
                challenge_id=challenge_id,
                active_session_id=source.session_id,
                latest_attempt_id=attempt_id,
            )

            return 201, self._remediation_envelope(
                remediation, attempt, outs, challenge_id, challenge.milestone_id
            )

        return await self._with_idempotency(
            app_user_id=app_user_id,
            endpoint="POST /v1/challenges/remediation",
            idempotency_key=idempotency_key,
            request_body=request_body,
            compute=compute,
        )

    def _remediation_envelope(
        self,
        remediation: LearningJourneyRemediation,
        attempt: LearningJourneyAttempt,
        questions: list[AttemptQuestionOut],
        challenge_id: str,
        milestone_id: str,
    ) -> dict[str, Any]:
        meta = remediation.generation_metadata
        out = RemediationCreateOut(
            remediation_id=remediation.remediation_id,
            session_id=remediation.session_id,
            journey_id=_JOURNEY_ID,
            milestone_id=milestone_id,
            challenge_id=challenge_id,
            source_attempt_id=remediation.source_attempt_id,
            attempt_id=remediation.attempt_id,
            attempt_number=attempt.attempt_number,
            challenge_attempt_number=attempt.challenge_attempt_number,
            attempt_type="REMEDIATION",
            status=attempt.status,
            mandatory=True,
            round_number=1,
            max_mandatory_rounds=_MAX_MANDATORY_REMEDIATION_ROUNDS,
            generation=RemediationGeneration(**meta),
            questions=questions,
            progression=RemediationCreateProgression(
                status="REMEDIATION_IN_PROGRESS",
                can_access_next_challenge=False,
                unlocks_after_submission=True,
                additional_mandatory_rounds=0,
            ),
        )
        return {
            "success": True,
            "data": out.model_dump(mode="json", by_alias=True),
            "meta": {"schema_version": "1.0"},
        }

    # --- GET /v1/learning-journey/readiness, /v1/learning-journey/home ---------
    #
    # Not in the original spec — new, learning-journey-only endpoints (see
    # schemas.py's own section header for the full rationale). Streak/week/daily
    # challenge have no dedicated tracking: they're derived entirely from
    # ``learning_journey_attempts.submitted_at``, converted into the caller's
    # timezone (``timezone`` is the same raw ``X-Timezone`` string the rest of this
    # BFF already forwards verbatim — unvalidated, same as api/deps.py's own
    # ``get_timezone``).

    async def _compute_readiness(self, assignment_id: str) -> ReadinessOut:
        progress_by_challenge = await self._repo.list_progress(assignment_id)
        total = len(progress_by_challenge)
        completed = sum(1 for p in progress_by_challenge.values() if p.status == "COMPLETED")
        percentage = round((completed / total) * 100, 2) if total else 0.0
        return ReadinessOut(
            percentage=percentage,
            completed_challenges=completed,
            total_challenges=total,
            # Always null — see BestMockResultOut's own docstring.
            best_mock_result=None,
        )

    async def get_readiness(self, app_user_id: str) -> ReadinessOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        return await self._compute_readiness(assignment_id)

    @staticmethod
    def _resolve_zone(timezone: str | None) -> ZoneInfo:
        if not timezone:
            return ZoneInfo("UTC")
        try:
            return ZoneInfo(timezone)
        except Exception:  # an invalid/unknown IANA name falls back to UTC
            return ZoneInfo("UTC")

    @staticmethod
    def _current_streak(active_dates: set[date], today: date) -> tuple[int, int, bool]:
        extended_today = today in active_dates
        cursor = today if extended_today else today - timedelta(days=1)
        current = 0
        while cursor in active_dates:
            current += 1
            cursor -= timedelta(days=1)

        longest = 0
        for day in active_dates:
            if day - timedelta(days=1) in active_dates:
                continue  # not the start of a run
            run = 0
            cursor = day
            while cursor in active_dates:
                run += 1
                cursor += timedelta(days=1)
            longest = max(longest, run)
        longest = max(longest, current)
        return current, longest, extended_today

    async def _find_current_and_next(
        self, assignment_id: str
    ) -> tuple[Any | None, Any | None, dict[str, Any]]:
        """Returns (current_challenge, next_challenge, progress_by_challenge_id) —
        the first not-COMPLETED challenge in journey order, and the one right
        after it, across the whole journey (not just one milestone)."""
        milestones = await self._repo.list_milestones(_JOURNEY_ID)
        progress_by_challenge = await self._repo.list_progress(assignment_id)
        sequence: list[Any] = []
        for milestone in milestones:
            sequence.extend(await self._repo.list_challenges_for_milestone(milestone.milestone_id))

        current = None
        current_index = None
        for index, challenge in enumerate(sequence):
            if progress_by_challenge[challenge.challenge_id].status != "COMPLETED":
                current = challenge
                current_index = index
                break
        next_challenge = (
            sequence[current_index + 1]
            if current_index is not None and current_index + 1 < len(sequence)
            else None
        )
        return current, next_challenge, progress_by_challenge

    async def get_home(self, app_user_id: str, timezone: str | None) -> HomeOut:
        assignment_id = await self._ensure_assignment(app_user_id)
        zone = self._resolve_zone(timezone)
        now = self._now().astimezone(zone)
        today = now.date()

        attempts = await self._repo.list_submitted_attempts_for_assignment(assignment_id)
        active_dates = {a.submitted_at.astimezone(zone).date() for a in attempts if a.submitted_at}
        current_streak, longest_streak, extended_today = self._current_streak(active_dates, today)

        week_start = today - timedelta(days=(today.weekday() + 1) % 7)  # most recent Sunday
        week_days = []
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            if day == today:
                week_days.append(
                    WeekDay(date=day.isoformat(), status="today", done=day in active_dates)
                )
            elif day < today:
                done = day in active_dates
                week_days.append(
                    WeekDay(date=day.isoformat(), status="done" if done else "missed", done=done)
                )
            else:
                week_days.append(WeekDay(date=day.isoformat(), status="missed", done=None))

        today_challenge_ids = {
            a.challenge_id
            for a in attempts
            if a.submitted_at and a.submitted_at.astimezone(zone).date() == today
        }
        daily_progress = min(len(today_challenge_ids), _DAILY_CHALLENGE_TARGET)
        tomorrow_midnight = datetime.combine(
            today + timedelta(days=1), datetime.min.time(), tzinfo=zone
        )

        readiness = await self._compute_readiness(assignment_id)

        current, next_challenge, _ = await self._find_current_and_next(assignment_id)
        continue_out = None
        if current is not None:
            progress = await self._repo.get_progress(
                assignment_id=assignment_id, challenge_id=current.challenge_id
            )
            continue_out = ContinueChallenge(
                milestone_id=current.milestone_id,
                challenge_id=current.challenge_id,
                display_code=current.display_code,
                title=current.title,
                action="CONTINUE" if progress and progress.total_attempts > 0 else "START",
            )
        up_next = (
            [
                UpNextChallenge(
                    milestone_id=next_challenge.milestone_id,
                    challenge_id=next_challenge.challenge_id,
                    display_code=next_challenge.display_code,
                    title=next_challenge.title,
                    status="LOCKED",
                )
            ]
            if next_challenge is not None
            else []
        )

        return HomeOut(
            week=Week(timezone=str(zone), starts_on="SUNDAY", days=week_days),
            daily_challenge=DailyChallenge(
                type="COMPLETE_LESSONS",
                target=_DAILY_CHALLENGE_TARGET,
                progress=daily_progress,
                completed=daily_progress >= _DAILY_CHALLENGE_TARGET,
                resets_at=tomorrow_midnight.astimezone(UTC),
            ),
            streak=Streak(
                current=current_streak, longest=longest_streak, extended_today=extended_today
            ),
            readiness=readiness,
            tabs=HomeTabs(
                learning_path=TabState(is_locked=False),
                mock_exams=TabState(is_locked=True, reason="NOT_AVAILABLE"),
            ),
            continue_=continue_out,
            up_next=up_next,
        )
