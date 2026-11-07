"""Public theory API schemas (Plan §7.3, P6.T5).

Every shape here is the public contract exactly as documented — not a 1:1 copy
of the engine's internal DTOs (``clients/engine/theory.py``). Two fields the
plan's own examples show are not reproduced, by deliberate, logged decision
(``docs/PROGRESS__STATUS.md``, P6.T5):

* **``answered`` is a plain boolean**, not the full feedback object the plan's
  resume example shows. The engine's ``AttemptItemRefDTO`` only exposes a
  boolean on an already-answered item (no selected/correct option, no
  explanation) — reproducing the richer shape needs new engine-side work
  (re-deriving grading output for every already-answered item on resume),
  which is out of this task's BFF-only scope.
* **``displayIndex`` is omitted from the attempt response and ``null`` on the
  lesson theory response.** Neither ``AttemptDTO`` nor ``LessonStateDTO``
  carries it — it's computed by the engine and only surfaced today on the
  home/learning-path DTOs, and calling either of those here would break this
  route's one-engine-call budget (Plan §7.3). The app already has the
  lesson's ``displayIndex`` from the screen it navigated from (home or the
  learning path), both of which it must visit before reaching either of
  these.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from boost_bridge.schemas.common import APIModel
from boost_bridge.schemas.content_blocks import ContentBlockOut

# --- Shared ------------------------------------------------------------------


class OpenAttemptOut(APIModel):
    attempt_id: str
    phase: str


# --- Home (GET /v1/home) ------------------------------------------------------


class HomeUserOut(APIModel):
    initials: str
    first_name: str


class HomeWeekDayOut(APIModel):
    date: str
    status: str
    done: bool | None = None


class HomeWeekOut(APIModel):
    timezone: str
    starts_on: str
    days: list[HomeWeekDayOut] = Field(default_factory=list)


class HomeDailyChallengeOut(APIModel):
    type: str
    target: int
    progress: int
    completed: bool
    resets_at: datetime


class HomeStreakOut(APIModel):
    current: int
    longest: int
    extended_today: bool


class HomeReadinessSummaryOut(APIModel):
    percent: int


class HomeTabStateOut(APIModel):
    locked: bool
    lock_reason: str | None = None


class HomeTabsOut(APIModel):
    learning_path: HomeTabStateOut
    mock_exams: HomeTabStateOut


class HomeContinueOut(APIModel):
    kind: str
    unit_id: str
    unit_display_index: str
    lesson_id: str
    display_index: str
    title: str
    action: str
    open_attempt: OpenAttemptOut | None = None


class HomeUpNextOut(APIModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str


class HomeOut(APIModel):
    user: HomeUserOut
    week: HomeWeekOut | None = None
    daily_challenge: HomeDailyChallengeOut | None = None
    streak: HomeStreakOut | None = None
    readiness: HomeReadinessSummaryOut | None = None
    tabs: HomeTabsOut
    continue_: HomeContinueOut | None = Field(default=None, alias="continue")
    up_next: list[HomeUpNextOut] = Field(default_factory=list)
    learning_path_etag: str


# --- Learning path (GET /v1/learning-path) ------------------------------------


class LessonLastResultOut(APIModel):
    correct: int
    total: int


class LearningPathEntryOut(APIModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    last_result: LessonLastResultOut | None = None
    open_attempt: OpenAttemptOut | None = None


class LearningPathUnitProgressOut(APIModel):
    completed_lessons: int
    total_lessons: int
    percent: int


class LearningPathUnitOut(APIModel):
    unit_id: str
    display_index: str
    title: str
    icon_url: str | None = None
    locked: bool
    lock_reason: str | None = None
    progress: LearningPathUnitProgressOut
    entries: list[LearningPathEntryOut] = Field(default_factory=list)


class LearningPathOut(APIModel):
    units: list[LearningPathUnitOut] = Field(default_factory=list)


# --- Readiness (GET /v1/readiness) --------------------------------------------


class ReadinessUnitOut(APIModel):
    unit_id: str
    display_index: str
    title: str
    percent: int
    completed_lessons: int
    total_lessons: int
    locked: bool


class ReadinessOut(APIModel):
    percent: int
    completed_lessons: int
    total_lessons: int
    average_best_accuracy: float
    units: list[ReadinessUnitOut] = Field(default_factory=list)


# --- Lesson theory (GET /v1/lessons/{lessonId}) -------------------------------


class LessonDetailOut(APIModel):
    lesson_id: str
    display_index: str | None = None
    title: str
    status: str
    estimated_minutes: int
    question_count: int
    open_attempt: OpenAttemptOut | None = None
    theory: list[ContentBlockOut] = Field(default_factory=list)


# --- Attempts ------------------------------------------------------------------


class OptionOut(APIModel):
    key: str
    label: str
    content: list[ContentBlockOut] = Field(default_factory=list)


class ItemOut(APIModel):
    seq: int
    phase: str
    type: Literal["mcq"] = "mcq"
    prompt: list[ContentBlockOut] = Field(default_factory=list)
    options: list[OptionOut] = Field(default_factory=list)
    answered: bool = False


class RetryOut(APIModel):
    total: int
    items: list[ItemOut] = Field(default_factory=list)


# --- Mock exams (read-only browsing, 2026-11-07 — no attempt/session tracking yet) ----------------


class MockExamSummaryOut(APIModel):
    mock_exam_id: str
    name: str
    description: str
    question_count: int
    complete: bool


class MockExamQuestionOut(APIModel):
    prompt: list[ContentBlockOut] = Field(default_factory=list)
    options: list[OptionOut] = Field(default_factory=list)


class MockExamDetailOut(APIModel):
    mock_exam_id: str
    name: str
    description: str
    question_count: int
    complete: bool
    questions: list[MockExamQuestionOut] = Field(default_factory=list)


class AttemptOut(APIModel):
    attempt_id: str
    # Known on start (the lessonId path param); null on GET /v1/attempts/{attemptId}
    # (resume), since neither AttemptDTO nor this route's one-engine-call budget
    # gives a source for it there (see this module's docstring).
    lesson_id: str | None = None
    status: str
    question_count: int
    items: list[ItemOut] = Field(default_factory=list)
    retry: RetryOut | None = None


class CorrectOptionOut(APIModel):
    key: str
    label: str
    content: list[ContentBlockOut] = Field(default_factory=list)


class ResponseFeedbackOut(APIModel):
    seq: int
    is_correct: bool
    selected_option_key: str
    correct_option: CorrectOptionOut
    explanation: list[ContentBlockOut] = Field(default_factory=list)


class PhaseSummaryOut(APIModel):
    total: int
    correct: int
    wrong: int


class CompletionNextOut(APIModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    action: str


class CompletionDailyChallengeOut(APIModel):
    target: int
    progress: int
    completed: bool


class CompletionProgressOut(APIModel):
    streak: HomeStreakOut
    daily_challenge: CompletionDailyChallengeOut
    readiness: HomeReadinessSummaryOut
    learning_path_etag: str


class LessonPhaseCompletionOut(APIModel):
    attempt_id: str
    status: str
    lesson_summary: PhaseSummaryOut | None = None
    retry: RetryOut | None = None
    next: CompletionNextOut | None = None
    progress: CompletionProgressOut | None = None


class RetryPhaseCompletionOut(APIModel):
    attempt_id: str
    status: str
    retry_summary: PhaseSummaryOut | None = None
    next: CompletionNextOut | None = None
    progress: CompletionProgressOut | None = None


# --- Requests --------------------------------------------------------------------


class StartAttemptIn(APIModel):
    request_id: UUID


class AnswerIn(APIModel):
    response_id: UUID
    seq: int = Field(ge=1)
    selected_option_key: str = Field(min_length=1)
    duration_ms: int | None = Field(default=None, ge=0)
