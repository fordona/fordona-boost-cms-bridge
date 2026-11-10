"""Request/response schemas for the Learning Journey contract (spec v1).

Deliberately **not** ``schemas.common.APIModel``: that base camelCases every field to
match fordona-engine/Boost. This spec's own examples are snake_case
(``journey_id``, ``completion_percentage``, ...) and wrap data in
``{"success": ..., "data"/"error": ...}``, not RFC 7807 — two incompatible
conventions kept isolated on purpose (see package docstring).
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AttemptType = Literal["INITIAL", "REMEDIATION", "VOLUNTARY"]
AttemptStatus = Literal["IN_PROGRESS", "SUBMITTED", "ABANDONED"]
QuestionType = Literal["SINGLE_CHOICE", "TRUE_FALSE", "MULTIPLE_SELECT"]
ResponseStatus = Literal["UNGRADED", "GRADED"]
ChallengeProgressStatus = Literal[
    "NOT_STARTED", "IN_PROGRESS", "REMEDIATION_REQUIRED", "REMEDIATION_IN_PROGRESS", "COMPLETED"
]


class LJModel(BaseModel):
    # populate_by_name only matters for the one field that needs an alias at all
    # (HomeOut.continue_ -> "continue", a Python keyword) — every other field's
    # name already equals its own implicit alias, so this changes nothing for them.
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


# --- Shared fragments --------------------------------------------------------


class AccessState(LJModel):
    is_locked: bool
    reason: str | None = None


class OptionOut(LJModel):
    option_id: str
    option_key: str
    text: str
    image_urls: list[str] = Field(default_factory=list)


class QuestionPreviewOut(LJModel):
    """The shared "delivery shape" (spec §5) — deliberately has no
    ``correct_answer``/``explanation`` fields at all, not even as ``null``."""

    question_id: str
    question_version: int
    position: int
    question_type: QuestionType
    question_text: str
    difficulty: int
    level: str
    image_urls: list[str] = Field(default_factory=list)
    has_image_reference: bool
    options: list[OptionOut]
    connected_chapters: list[str] = Field(default_factory=list)
    cms_row_numbers: list[int] = Field(default_factory=list)


class QuestionResponseOut(LJModel):
    status: ResponseStatus
    selected_option_keys: list[str]
    selected_option_ids: list[str]
    is_correct: bool
    correct_option_ids: list[str]
    explanation: str | None
    duration_ms: int | None


class AttemptQuestionOut(QuestionPreviewOut):
    source_type: str | None = None
    source_question_id: str | None = None
    response: QuestionResponseOut | None = None


# --- Envelope -------------------------------------------------------------------
#
# The error-side shape ({"success": false, "error": {...}}) is built directly by
# ``errors.py``'s exception handler, not a schema here — it's never a route's
# declared return type. ``success_envelope`` is the one success-side builder, used
# directly by every route (GETs) or service.py (the 4 idempotent POSTs).


def success_envelope(data: LJModel, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Used directly by GET routes (which don't need idempotency); POST routes build
    the same shape inline in ``service.py`` alongside their status code."""
    body: dict[str, Any] = {"schema_version": "1.0"}
    if meta:
        body.update(meta)
    return {"success": True, "data": data.model_dump(mode="json", by_alias=True), "meta": body}


# --- GET /v1/learning-journey --------------------------------------------------


class JourneyStats(LJModel):
    milestone_count: int
    challenge_count: int
    question_count: int


class JourneyProgress(LJModel):
    completed_milestones: int
    completed_challenges: int
    total_challenges: int
    completion_percentage: float


class CurrentPosition(LJModel):
    milestone_id: str
    challenge_id: str


class MilestoneProgress(LJModel):
    completed_challenges: int
    total_challenges: int
    completion_percentage: float
    status: ChallengeProgressStatus


class ChallengeProgressSummary(LJModel):
    status: ChallengeProgressStatus
    best_full_attempt_score_percentage: float | None


class ChallengeSummaryOut(LJModel):
    challenge_id: str
    milestone_id: str
    position: int
    display_code: str
    title: str
    description: str | None
    estimated_minutes: int | None
    question_count: int
    difficulty_distribution: dict[str, int]
    progress: ChallengeProgressSummary
    access: AccessState
    # Not in the original spec — added so the client can show "content coming soon".
    # The server no longer blocks starting an attempt on this (see service.py's
    # start_attempt, 2026-11-08) — every ms_001 challenge is permanently
    # MISSING_MEDIA, so enforcing it would make the free tier unattemptable.
    # Independent of `access`: a challenge can be unlocked/entitled and still not
    # content-ready.
    is_content_ready: bool


class MilestoneSummaryOut(LJModel):
    milestone_id: str
    journey_id: str
    position: int
    title: str
    description: str | None
    challenge_count: int
    question_count: int
    progress: MilestoneProgress
    access: AccessState
    # Same objects as GET /v1/milestones' `challenges`, so the client can render the
    # whole path from this one call.
    challenges: list[ChallengeSummaryOut]


class LearningJourneyOut(LJModel):
    journey_id: str
    assignment_id: str
    version: int
    title: str
    description: str | None
    status: str
    stats: JourneyStats
    progress: JourneyProgress
    current_position: CurrentPosition | None
    milestones: list[MilestoneSummaryOut]
    updated_at: datetime


# --- GET /v1/milestones -------------------------------------------------------


class MilestoneStats(LJModel):
    challenge_count: int
    question_count: int
    difficulty_distribution: dict[str, int]


class MilestoneDetailOut(LJModel):
    milestone_id: str
    journey_id: str
    position: int
    title: str
    description: str | None
    stats: MilestoneStats
    progress: MilestoneProgress
    challenges: list[ChallengeSummaryOut]


# --- GET /v1/challenges -------------------------------------------------------


class RemediationState(LJModel):
    required: bool
    completed: bool
    source_attempt_id: str | None
    incorrect_question_count: int | None


class ChallengeUserState(LJModel):
    status: ChallengeProgressStatus
    is_progression_complete: bool
    can_access_next_challenge: bool
    total_attempts: int
    latest_attempt_id: str | None
    active_session_id: str | None
    remediation: RemediationState | None = None


class ChallengeDetailOut(LJModel):
    challenge_id: str
    journey_id: str
    milestone_id: str
    version: int
    position: int
    display_code: str
    title: str
    description: str | None
    estimated_minutes: int | None
    question_count: int
    difficulty_distribution: dict[str, int]
    questions: list[QuestionPreviewOut]
    user_state: ChallengeUserState
    # See ChallengeSummaryOut's note — same not-in-spec addition, same reason.
    is_content_ready: bool


# --- POST /v1/challenges/attempts, GET .../attempts/{id} ---------------------


class StartAttemptRequest(LJModel):
    challenge_id: str
    mode: Literal["INITIAL", "VOLUNTARY"]


class AttemptDetailOut(LJModel):
    session_id: str
    attempt_id: str
    attempt_number: int
    challenge_attempt_number: int
    attempt_type: AttemptType
    challenge_id: str
    journey_id: str
    milestone_id: str
    challenge_version: int
    status: AttemptStatus
    started_at: datetime
    question_count: int
    answered_count: int
    questions: list[AttemptQuestionOut]


# --- POST /v1/challenges/attempts/{id}/answers --------------------------------


class AnswerRequest(LJModel):
    question_id: str
    selected_option_keys: Annotated[list[str], Field(min_length=1)]
    duration_ms: int | None = None


class AttemptProgress(LJModel):
    answered_count: int
    total_questions: int
    remaining_count: int


class CorrectAnswerOut(LJModel):
    option_ids: list[str]


class AnswerFeedbackOut(LJModel):
    attempt_id: str
    question_id: str
    response_status: ResponseStatus
    selected_option_keys: list[str]
    selected_option_ids: list[str]
    is_correct: bool
    correct_answer: CorrectAnswerOut
    explanation: str | None
    duration_ms: int | None
    attempt_progress: AttemptProgress


# --- POST /v1/challenges/attempts/{id}/submit ---------------------------------


class SubmitRequest(LJModel):
    pass


class SubmitResult(LJModel):
    total_questions: int
    correct_count: int
    incorrect_count: int
    score_percentage: float
    duration_ms: int
    incorrect_question_ids: list[str]


class SubmitRemediationState(LJModel):
    required: bool
    completed: bool
    source_attempt_id: str | None
    incorrect_question_count: int | None = None
    remaining_mandatory_rounds: int
    remaining_incorrect_count: int | None = None


class SubmitProgression(LJModel):
    status: ChallengeProgressStatus
    is_progression_complete: bool
    can_access_next_challenge: bool
    next_challenge_id: str | None


class SubmitResultOut(LJModel):
    session_id: str
    attempt_id: str
    attempt_number: int
    challenge_attempt_number: int
    attempt_type: AttemptType
    challenge_id: str
    status: AttemptStatus
    result: SubmitResult
    remediation: SubmitRemediationState
    progression: SubmitProgression
    submitted_at: datetime


# --- GET /v1/challenges/attempts (history) ------------------------------------


class AttemptSummaryOut(LJModel):
    session_id: str
    attempt_id: str
    attempt_number: int
    challenge_attempt_number: int
    attempt_type: AttemptType
    status: AttemptStatus
    total_questions: int
    correct_count: int | None
    score_percentage: float | None
    submitted_at: datetime | None


class AttemptHistoryOut(LJModel):
    challenge_id: str
    items: list[AttemptSummaryOut]
    next_cursor: str | None


# --- POST /v1/challenges/remediation -------------------------------------------


class RemediationRequest(LJModel):
    challenge_id: str
    source_attempt_id: str


class RemediationGeneration(LJModel):
    strategy: Literal["INCORRECT_ONLY", "INCORRECT_PLUS_SIMILAR"]
    similarity_enabled: bool
    original_incorrect_count: int
    similar_question_count: int
    total_questions: int
    fallback_used: bool


class RemediationCreateProgression(LJModel):
    status: ChallengeProgressStatus
    can_access_next_challenge: bool
    unlocks_after_submission: bool
    additional_mandatory_rounds: int


class RemediationCreateOut(LJModel):
    remediation_id: str
    session_id: str
    journey_id: str
    milestone_id: str
    challenge_id: str
    source_attempt_id: str
    attempt_id: str
    attempt_number: int
    challenge_attempt_number: int
    attempt_type: Literal["REMEDIATION"]
    status: AttemptStatus
    mandatory: bool
    round_number: int
    max_mandatory_rounds: int
    generation: RemediationGeneration
    questions: list[AttemptQuestionOut]
    progression: RemediationCreateProgression


# --- GET /v1/learning-journey/readiness, /v1/learning-journey/home -------------
# Not in the original spec — new, learning-journey-only endpoints mirroring the
# existing engine-backed /v1/readiness and /v1/home UX, but reading only this
# feature's own data (plus the one already-agreed entitlement check). See
# LearningJourneyService's readiness/home docstrings for the exact derivation of
# every field that isn't a plain read (streak, week, daily challenge).


class BestMockResultOut(LJModel):
    """Always ``null`` today — no mock-exam integration exists for the learning
    journey. The field is modelled so the client has a stable shape to bind to
    whenever that changes, per explicit instruction: add the field, not the
    functionality."""

    correct_count: int
    total_questions: int
    passed: bool


class ReadinessOut(LJModel):
    percentage: float
    completed_challenges: int
    total_challenges: int
    best_mock_result: BestMockResultOut | None


class WeekDay(LJModel):
    date: str  # ISO date, e.g. "2026-11-08"
    status: Literal["missed", "today", "done"]
    done: bool | None


class Week(LJModel):
    timezone: str
    starts_on: Literal["SUNDAY"]
    days: list[WeekDay]


class DailyChallenge(LJModel):
    type: Literal["COMPLETE_LESSONS"]
    target: int
    progress: int
    completed: bool
    resets_at: datetime


class Streak(LJModel):
    current: int
    longest: int
    extended_today: bool


class TabState(LJModel):
    is_locked: bool
    reason: str | None = None


class HomeTabs(LJModel):
    learning_path: TabState
    mock_exams: TabState


class ContinueChallenge(LJModel):
    milestone_id: str
    challenge_id: str
    display_code: str
    title: str
    action: Literal["START", "CONTINUE"]


class UpNextChallenge(LJModel):
    milestone_id: str
    challenge_id: str
    display_code: str
    title: str
    status: Literal["LOCKED", "AVAILABLE"]


class HomeOut(LJModel):
    week: Week
    daily_challenge: DailyChallenge
    streak: Streak
    readiness: ReadinessOut
    tabs: HomeTabs
    continue_: ContinueChallenge | None = Field(alias="continue")
    up_next: list[UpNextChallenge]
