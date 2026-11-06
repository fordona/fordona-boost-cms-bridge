"""Typed calls to fordona-engine's internal theory API (Plan §7.4, P6.T5).

One method per internal endpoint, each returning the engine's own DTO shape
(mirrored here field-for-field from ``io.fordona.engine.learn.theory.api.dto``,
verified against the Java source rather than only the plan prose). Mapping an
engine DTO to the public, answer-free contract is ``services/theory_mappers.py``'s
job, not this client's.

**Deliberate, logged scope-cut (P6.T5):** the engine's own ``AttemptItemRefDTO``
carries only a boolean ``answered`` flag on an already-answered item — no
``selectedOptionKey``/``correctOptionKey``/explanation. Those are stored
server-side (``AttemptItemModel``) but never exposed, and ``correctOptionKey``
isn't stored at all (it's re-derived from the pinned revision only at grading
time). Plan §7.3's own example shows resume returning the full feedback object
for an answered item; reproducing that would need new engine-side work (same
re-derivation ``AttemptService#answer`` already does, run again for every
already-answered item on resume), which is out of P6.T5's BFF-only scope. Owner
decision: ship ``answered`` as a plain boolean for now (see
``docs/PROGRESS__STATUS.md``), revisit if/when the engine adds that field.
"""

from typing import Any

from pydantic import Field

from boost_bridge.clients.engine.client import EngineClient
from boost_bridge.clients.engine.models import EngineModel

# --- Shared ------------------------------------------------------------------


class EngineLessonOpenAttemptRef(EngineModel):
    attempt_id: str
    phase: str


class EngineAttemptItemRef(EngineModel):
    seq: int
    phase: str
    question_id: str
    version: str
    option_order: list[str] = Field(default_factory=list)
    answered: bool | None = None


# --- Home ----------------------------------------------------------------------


class EngineHomeUser(EngineModel):
    initials: str
    first_name: str


class EngineHomeWeekDay(EngineModel):
    date: str
    status: str
    done: bool | None = None


class EngineHomeWeek(EngineModel):
    timezone: str
    starts_on: str
    days: list[EngineHomeWeekDay] = Field(default_factory=list)


class EngineHomeDailyChallenge(EngineModel):
    type: str
    target: int
    progress: int
    completed: bool
    resets_at: str


class EngineHomeStreak(EngineModel):
    current: int
    longest: int
    extended_today: bool


class EngineHomeReadiness(EngineModel):
    percent: int


class EngineHomeTabState(EngineModel):
    locked: bool
    lock_reason: str | None = None


class EngineHomeTabs(EngineModel):
    learning_path: EngineHomeTabState
    mock_exams: EngineHomeTabState


class EngineHomeContinue(EngineModel):
    kind: str
    unit_id: str
    unit_display_index: str
    lesson_id: str
    display_index: str
    title: str
    action: str
    open_attempt: EngineLessonOpenAttemptRef | None = None


class EngineHomeUpNext(EngineModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str


class EngineHome(EngineModel):
    user: EngineHomeUser
    week: EngineHomeWeek | None = None
    daily_challenge: EngineHomeDailyChallenge | None = None
    streak: EngineHomeStreak | None = None
    readiness: EngineHomeReadiness | None = None
    tabs: EngineHomeTabs
    # The engine's own Java field is `continueCard`, pushed to the wire as
    # literally "continue" via @JsonProperty (a Java-keyword workaround) — not
    # something `to_camel` would ever produce from a snake_case name, so the
    # alias is set explicitly rather than relying on the model's generator.
    continue_: EngineHomeContinue | None = Field(default=None, alias="continue")
    up_next: list[EngineHomeUpNext] = Field(default_factory=list)
    learning_path_etag: str


# --- Learning path -------------------------------------------------------------


class EngineLessonLastResult(EngineModel):
    correct: int
    total: int


class EngineLearningPathEntry(EngineModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    last_result: EngineLessonLastResult | None = None
    open_attempt: EngineLessonOpenAttemptRef | None = None


class EngineLearningPathUnitProgress(EngineModel):
    completed_lessons: int
    total_lessons: int
    percent: int


class EngineLearningPathUnit(EngineModel):
    unit_id: str
    display_index: str
    title: str
    icon_url: str | None = None
    locked: bool
    lock_reason: str | None = None
    progress: EngineLearningPathUnitProgress
    entries: list[EngineLearningPathEntry] = Field(default_factory=list)


class EngineLearningPath(EngineModel):
    units: list[EngineLearningPathUnit] = Field(default_factory=list)


# --- Readiness -------------------------------------------------------------------


class EngineReadinessUnit(EngineModel):
    unit_id: str
    display_index: str
    title: str
    percent: int
    completed_lessons: int
    total_lessons: int
    locked: bool


class EngineReadiness(EngineModel):
    percent: int
    completed_lessons: int
    total_lessons: int
    average_best_accuracy: float
    units: list[EngineReadinessUnit] = Field(default_factory=list)


# --- Lesson state ----------------------------------------------------------------


class EngineLessonState(EngineModel):
    status: str
    locked: bool
    lock_reason: str | None = None
    open_attempt: EngineLessonOpenAttemptRef | None = None
    question_count: int
    estimated_minutes: int
    lesson_version: str


# --- Attempts --------------------------------------------------------------------


class EngineAttempt(EngineModel):
    attempt_id: str
    status: str
    attempt_no: int
    items: list[EngineAttemptItemRef] = Field(default_factory=list)


class EngineAnswerFeedback(EngineModel):
    seq: int
    is_correct: bool
    selected_option_key: str
    correct_option_key: str
    correct_option_label: str
    # Raw content blocks (asset ids only); List[Any] here, parsed into
    # ContentBlock by the mapper, which is where the BFF's block models live.
    explanation: list[Any] = Field(default_factory=list)


class EnginePhaseSummary(EngineModel):
    total: int
    correct: int
    wrong: int


class EngineRetryPhase(EngineModel):
    total: int
    items: list[EngineAttemptItemRef] = Field(default_factory=list)


class EngineCompletionNext(EngineModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    action: str


class EngineCompletionProgressDailyChallenge(EngineModel):
    target: int
    progress: int
    completed: bool


class EngineCompletionProgress(EngineModel):
    streak: EngineHomeStreak
    daily_challenge: EngineCompletionProgressDailyChallenge
    readiness: EngineHomeReadiness
    learning_path_etag: str


class EngineAttemptPhaseCompletion(EngineModel):
    attempt_id: str
    status: str
    lesson_summary: EnginePhaseSummary | None = None
    retry_summary: EnginePhaseSummary | None = None
    retry: EngineRetryPhase | None = None
    next: EngineCompletionNext | None = None
    progress: EngineCompletionProgress | None = None


class EngineTheoryClient:
    """Typed wrapper over ``EngineClient`` for every ``/internal/theory/v1/**`` call."""

    def __init__(self, client: EngineClient, *, phase_complete_timeout: float) -> None:
        self._client = client
        self._phase_complete_timeout = phase_complete_timeout

    async def get_home(self, *, accept_language: str, timezone: str | None) -> EngineHome:
        response = await self._client.get(
            "/internal/theory/v1/home", accept_language=accept_language, timezone=timezone
        )
        return EngineHome.model_validate(response.data)

    async def get_learning_path(
        self, *, accept_language: str, if_none_match: str | None
    ) -> tuple[EngineLearningPath | None, str | None, bool]:
        """Returns ``(path-or-None-on-304, etag, not_modified)``."""
        response = await self._client.get(
            "/internal/theory/v1/learning-path",
            accept_language=accept_language,
            if_none_match=if_none_match,
        )
        if response.not_modified:
            return None, response.etag, True
        return EngineLearningPath.model_validate(response.data), response.etag, False

    async def get_readiness(self, *, accept_language: str) -> EngineReadiness:
        response = await self._client.get(
            "/internal/theory/v1/readiness", accept_language=accept_language
        )
        return EngineReadiness.model_validate(response.data)

    async def get_lesson_state(self, lesson_id: str) -> EngineLessonState:
        response = await self._client.get(f"/internal/theory/v1/lessons/{lesson_id}")
        return EngineLessonState.model_validate(response.data)

    async def start_attempt(self, lesson_id: str, request_id: str) -> EngineAttempt:
        response = await self._client.post(
            f"/internal/theory/v1/lessons/{lesson_id}/attempts", json={"requestId": request_id}
        )
        return EngineAttempt.model_validate(response.data)

    async def get_attempt(self, attempt_id: str) -> EngineAttempt:
        response = await self._client.get(f"/internal/theory/v1/attempts/{attempt_id}")
        return EngineAttempt.model_validate(response.data)

    async def answer(
        self,
        attempt_id: str,
        *,
        response_id: str,
        seq: int,
        selected_option_key: str,
        duration_ms: int | None,
        accept_language: str,
    ) -> EngineAnswerFeedback:
        response = await self._client.post(
            f"/internal/theory/v1/attempts/{attempt_id}/responses",
            json={
                "responseId": response_id,
                "seq": seq,
                "selectedOptionKey": selected_option_key,
                "durationMs": duration_ms,
            },
            accept_language=accept_language,
        )
        return EngineAnswerFeedback.model_validate(response.data)

    async def complete_lesson_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> EngineAttemptPhaseCompletion:
        response = await self._client.post(
            f"/internal/theory/v1/attempts/{attempt_id}/phases/lesson/complete",
            accept_language=accept_language,
            timezone=timezone,
            timeout_override=self._phase_complete_timeout,
        )
        return EngineAttemptPhaseCompletion.model_validate(response.data)

    async def complete_retry_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> EngineAttemptPhaseCompletion:
        response = await self._client.post(
            f"/internal/theory/v1/attempts/{attempt_id}/phases/retry/complete",
            accept_language=accept_language,
            timezone=timezone,
            timeout_override=self._phase_complete_timeout,
        )
        return EngineAttemptPhaseCompletion.model_validate(response.data)
