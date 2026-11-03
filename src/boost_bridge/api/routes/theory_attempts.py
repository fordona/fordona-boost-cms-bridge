"""Lesson attempts: start/resume, answer, phase completion (Plan §7.3).

**Deliberate, logged decision (P6.T5):** ``POST /v1/lessons/{lessonId}/attempts``
always answers 200, never 201. The plan's own example shows "201, or 200 for a
replay or a resumed open attempt", but the engine's ``startAttempt`` controller
method has no ``@ResponseStatus`` and always 200s — it carries no signal (a
"created" flag, or similar) this route could use to tell a fresh attempt from a
replay/resume. Changing that is new engine-side work outside this task's
BFF-only scope; see ``docs/PROGRESS__STATUS.md``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path

from boost_bridge.api.deps import CurrentLearner, Locale, Theory, Timezone
from boost_bridge.api.responses import (
    ATTEMPT_GET_ERRORS,
    ATTEMPT_START_ERRORS,
    PHASE_COMPLETE_ERRORS,
    RESPONSE_ERRORS,
)
from boost_bridge.schemas.common import ID_PATTERN
from boost_bridge.schemas.theory import (
    AnswerIn,
    AttemptOut,
    LessonPhaseCompletionOut,
    ResponseFeedbackOut,
    RetryPhaseCompletionOut,
    StartAttemptIn,
)

router = APIRouter(tags=["theory"])

LessonId = Annotated[str, Path(alias="lessonId", pattern=ID_PATTERN, examples=["12"])]
AttemptId = Annotated[UUID, Path(alias="attemptId")]


@router.post(
    "/lessons/{lessonId}/attempts",
    response_model=AttemptOut,
    responses=ATTEMPT_START_ERRORS,
    summary="Start or resume a lesson attempt — idempotent on requestId",
)
async def start_attempt(
    theory: Theory,
    _: CurrentLearner,
    locale: Locale,
    lesson_id: LessonId,
    body: StartAttemptIn,
) -> AttemptOut:
    return await theory.start_attempt(lesson_id, request_id=body.request_id, locale=locale)


@router.get(
    "/attempts/{attemptId}",
    response_model=AttemptOut,
    responses=ATTEMPT_GET_ERRORS,
    summary="Resume an attempt after the app restarts",
)
async def get_attempt(
    theory: Theory, _: CurrentLearner, locale: Locale, attempt_id: AttemptId
) -> AttemptOut:
    return await theory.get_attempt(attempt_id, locale=locale)


@router.post(
    "/attempts/{attemptId}/responses",
    response_model=ResponseFeedbackOut,
    responses=RESPONSE_ERRORS,
    summary="Check Answer — idempotent on responseId",
)
async def answer(
    theory: Theory,
    _: CurrentLearner,
    locale: Locale,
    attempt_id: AttemptId,
    body: AnswerIn,
) -> ResponseFeedbackOut:
    return await theory.answer(
        attempt_id,
        response_id=body.response_id,
        seq=body.seq,
        selected_option_key=body.selected_option_key,
        duration_ms=body.duration_ms,
        locale=locale,
    )


@router.post(
    "/attempts/{attemptId}/phases/lesson/complete",
    response_model=LessonPhaseCompletionOut,
    responses=PHASE_COMPLETE_ERRORS,
    summary="Complete the lesson phase — starts the retry phase, or completes the attempt",
)
async def complete_lesson_phase(
    theory: Theory, _: CurrentLearner, locale: Locale, timezone: Timezone, attempt_id: AttemptId
) -> LessonPhaseCompletionOut:
    return await theory.complete_lesson_phase(attempt_id, locale=locale, timezone=timezone)


@router.post(
    "/attempts/{attemptId}/phases/retry/complete",
    response_model=RetryPhaseCompletionOut,
    responses=PHASE_COMPLETE_ERRORS,
    summary="Complete the retry phase — the attempt and lesson finish COMPLETED",
)
async def complete_retry_phase(
    theory: Theory, _: CurrentLearner, locale: Locale, timezone: Timezone, attempt_id: AttemptId
) -> RetryPhaseCompletionOut:
    return await theory.complete_retry_phase(attempt_id, locale=locale, timezone=timezone)
