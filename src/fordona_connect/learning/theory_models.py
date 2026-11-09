"""The theory screens' and attempts' models, returned by ``LocalTheoryBackend``.

Field names follow the engine DTOs these replaced, so the public mappers
(``services/theory_mappers.py``) are unchanged. Mapping them to the public,
answer-free contract is the mappers' job. An already-answered attempt item carries
only a boolean ``answered`` flag, never the selected or correct option.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TheoryModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", alias_generator=to_camel, populate_by_name=True, frozen=True
    )


# --- Shared ------------------------------------------------------------------


class TheoryLessonOpenAttemptRef(TheoryModel):
    attempt_id: str
    phase: str


class TheoryAttemptItemRef(TheoryModel):
    seq: int
    phase: str
    question_id: str
    version: str
    option_order: list[str] = Field(default_factory=list)
    answered: bool | None = None


# --- Home ----------------------------------------------------------------------


class TheoryHomeUser(TheoryModel):
    initials: str
    first_name: str


class TheoryHomeWeekDay(TheoryModel):
    date: str
    status: str
    done: bool | None = None


class TheoryHomeWeek(TheoryModel):
    timezone: str
    starts_on: str
    days: list[TheoryHomeWeekDay] = Field(default_factory=list)


class TheoryHomeDailyChallenge(TheoryModel):
    type: str
    target: int
    progress: int
    completed: bool
    resets_at: str


class TheoryHomeStreak(TheoryModel):
    current: int
    longest: int
    extended_today: bool


class TheoryHomeReadiness(TheoryModel):
    percent: int


class TheoryHomeTabState(TheoryModel):
    locked: bool
    lock_reason: str | None = None


class TheoryHomeTabs(TheoryModel):
    learning_path: TheoryHomeTabState
    mock_exams: TheoryHomeTabState


class TheoryHomeContinue(TheoryModel):
    kind: str
    unit_id: str
    unit_display_index: str
    lesson_id: str
    display_index: str
    title: str
    action: str
    open_attempt: TheoryLessonOpenAttemptRef | None = None


class TheoryHomeUpNext(TheoryModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str


class TheoryHome(TheoryModel):
    user: TheoryHomeUser
    week: TheoryHomeWeek | None = None
    daily_challenge: TheoryHomeDailyChallenge | None = None
    streak: TheoryHomeStreak | None = None
    readiness: TheoryHomeReadiness | None = None
    tabs: TheoryHomeTabs
    # The engine's own Java field is `continueCard`, pushed to the wire as
    # literally "continue" via @JsonProperty (a Java-keyword workaround) — not
    # something `to_camel` would ever produce from a snake_case name, so the
    # alias is set explicitly rather than relying on the model's generator.
    continue_: TheoryHomeContinue | None = Field(default=None, alias="continue")
    up_next: list[TheoryHomeUpNext] = Field(default_factory=list)
    learning_path_etag: str


# --- Learning path -------------------------------------------------------------


class TheoryLessonLastResult(TheoryModel):
    correct: int
    total: int


class TheoryLearningPathEntry(TheoryModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    last_result: TheoryLessonLastResult | None = None
    open_attempt: TheoryLessonOpenAttemptRef | None = None


class TheoryLearningPathUnitProgress(TheoryModel):
    completed_lessons: int
    total_lessons: int
    percent: int


class TheoryLearningPathUnit(TheoryModel):
    unit_id: str
    display_index: str
    title: str
    icon_url: str | None = None
    locked: bool
    lock_reason: str | None = None
    progress: TheoryLearningPathUnitProgress
    entries: list[TheoryLearningPathEntry] = Field(default_factory=list)


class TheoryLearningPath(TheoryModel):
    units: list[TheoryLearningPathUnit] = Field(default_factory=list)


# --- Readiness -------------------------------------------------------------------


class TheoryReadinessUnit(TheoryModel):
    unit_id: str
    display_index: str
    title: str
    percent: int
    completed_lessons: int
    total_lessons: int
    locked: bool


class TheoryReadiness(TheoryModel):
    percent: int
    completed_lessons: int
    total_lessons: int
    average_best_accuracy: float
    units: list[TheoryReadinessUnit] = Field(default_factory=list)


# --- Lesson state ----------------------------------------------------------------


class TheoryLessonState(TheoryModel):
    status: str
    locked: bool
    lock_reason: str | None = None
    open_attempt: TheoryLessonOpenAttemptRef | None = None
    question_count: int
    estimated_minutes: int
    lesson_version: str


# --- Attempts --------------------------------------------------------------------


class TheoryAttempt(TheoryModel):
    attempt_id: str
    status: str
    attempt_no: int
    items: list[TheoryAttemptItemRef] = Field(default_factory=list)


# --- Mock exams (read-only browsing, 2026-11-07 — no attempt/session tracking yet) ----------------


class TheoryMockExamSummary(TheoryModel):
    mock_exam_id: str
    name: str
    description: str
    question_count: int
    complete: bool


class TheoryMockExamQuestionRef(TheoryModel):
    question_id: str
    version: str


class TheoryMockExamDetail(TheoryModel):
    mock_exam_id: str
    name: str
    description: str
    question_count: int
    complete: bool
    items: list[TheoryMockExamQuestionRef] = Field(default_factory=list)


class TheoryAnswerFeedback(TheoryModel):
    seq: int
    is_correct: bool
    selected_option_key: str
    correct_option_key: str
    correct_option_label: str
    # The engine forwards whatever raw shape Boost sent, unnormalized (confirmed
    # 2026-11-06: a plain HTML string for real Boost content, a block list only for
    # the stub's synthetic data) — ``list[Any]`` here would raise ``ValidationError``
    # on the real string case. Left untyped and parsed into ContentBlock by the
    # mapper (``parse_explanation_blocks``), which is where the BFF's block models
    # live and where the string-vs-list branching happens.
    explanation: Any = None


class TheoryPhaseSummary(TheoryModel):
    total: int
    correct: int
    wrong: int


class TheoryRetryPhase(TheoryModel):
    total: int
    items: list[TheoryAttemptItemRef] = Field(default_factory=list)


class TheoryCompletionNext(TheoryModel):
    kind: str
    lesson_id: str
    display_index: str
    title: str
    status: str
    action: str


class TheoryCompletionProgressDailyChallenge(TheoryModel):
    target: int
    progress: int
    completed: bool


class TheoryCompletionProgress(TheoryModel):
    streak: TheoryHomeStreak
    daily_challenge: TheoryCompletionProgressDailyChallenge
    readiness: TheoryHomeReadiness
    learning_path_etag: str


class TheoryAttemptPhaseCompletion(TheoryModel):
    attempt_id: str
    status: str
    lesson_summary: TheoryPhaseSummary | None = None
    retry_summary: TheoryPhaseSummary | None = None
    retry: TheoryRetryPhase | None = None
    next: TheoryCompletionNext | None = None
    progress: TheoryCompletionProgress | None = None
