"""Pure mapping: engine DTOs + Boost bodies → the public theory schemas (P6.T5).

No I/O here — every Boost body and resolved URL is already in hand by the time
these functions run. ``TheoryService`` (``services/theory_service.py``) is
what calls Boost/the engine and then calls these.
"""

from string import ascii_uppercase
from typing import Any

from pydantic import TypeAdapter

from boost_bridge.cache.attempt_refs import ItemRef
from boost_bridge.clients.boost.models import BoostQuestion, ContentBlock, QuestionOption
from boost_bridge.clients.engine.theory import (
    EngineAnswerFeedback,
    EngineAttemptItemRef,
    EngineAttemptPhaseCompletion,
    EngineCompletionNext,
    EngineCompletionProgress,
    EngineHome,
    EngineHomeContinue,
    EngineHomeTabs,
    EngineHomeUpNext,
    EngineLearningPath,
    EngineLessonLastResult,
    EngineLessonOpenAttemptRef,
    EngineLessonState,
    EnginePhaseSummary,
    EngineReadiness,
)
from boost_bridge.core.errors import ContentNotFoundError
from boost_bridge.schemas.content_blocks import ContentBlockOut, TextBlockOut
from boost_bridge.schemas.theory import (
    CompletionDailyChallengeOut,
    CompletionNextOut,
    CompletionProgressOut,
    CorrectOptionOut,
    HomeContinueOut,
    HomeDailyChallengeOut,
    HomeOut,
    HomeReadinessSummaryOut,
    HomeStreakOut,
    HomeTabsOut,
    HomeTabStateOut,
    HomeUpNextOut,
    HomeUserOut,
    HomeWeekDayOut,
    HomeWeekOut,
    ItemOut,
    LearningPathEntryOut,
    LearningPathOut,
    LearningPathUnitOut,
    LearningPathUnitProgressOut,
    LessonDetailOut,
    LessonLastResultOut,
    LessonPhaseCompletionOut,
    OpenAttemptOut,
    OptionOut,
    PhaseSummaryOut,
    ReadinessOut,
    ReadinessUnitOut,
    ResponseFeedbackOut,
    RetryOut,
    RetryPhaseCompletionOut,
)
from boost_bridge.services.blocks import render_blocks
from boost_bridge.services.content_html import html_to_blocks, text_block
from boost_bridge.services.media import AssetUrlResolver

_EXPLANATION_ADAPTER: TypeAdapter[list[ContentBlock]] = TypeAdapter(list[ContentBlock])


def parse_explanation_blocks(raw: Any) -> list[ContentBlock]:
    """The engine's ``explanation`` is untyped JSON (its own ``Object`` field) — it
    forwards whatever shape Boost sent it verbatim (``AttemptService`` stores and
    relays the raw value as-is, never normalizing it).

    Confirmed 2026-11-06: real Boost sends a plain HTML **string** per locale, never
    a block list — the stub's synthetic data is block-list-shaped, which is why this
    went unnoticed until tested against real content. A plain string must be
    HTML-converted here rather than handed to the block ``TypeAdapter`` directly,
    which raises ``ValidationError`` on a ``str`` (Pydantic v2 does not coerce
    ``str`` into ``list[Any]``) — every "Check Answer" response would otherwise 500
    against real Boost content.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        return html_to_blocks(raw, source="explanation")
    return _EXPLANATION_ADAPTER.validate_python(raw)


def map_open_attempt(ref: EngineLessonOpenAttemptRef | None) -> OpenAttemptOut | None:
    if ref is None:
        return None
    return OpenAttemptOut(attempt_id=ref.attempt_id, phase=ref.phase)


# --- Home ----------------------------------------------------------------------


def map_home(engine: EngineHome) -> HomeOut:
    return HomeOut(
        user=HomeUserOut(initials=engine.user.initials, first_name=engine.user.first_name),
        week=HomeWeekOut(
            timezone=engine.week.timezone,
            starts_on=engine.week.starts_on,
            days=[
                HomeWeekDayOut(date=day.date, status=day.status, done=day.done)
                for day in engine.week.days
            ],
        )
        if engine.week is not None
        else None,
        daily_challenge=HomeDailyChallengeOut(
            type=engine.daily_challenge.type,
            target=engine.daily_challenge.target,
            progress=engine.daily_challenge.progress,
            completed=engine.daily_challenge.completed,
            resets_at=engine.daily_challenge.resets_at,
        )
        if engine.daily_challenge is not None
        else None,
        streak=_map_streak(engine.streak) if engine.streak is not None else None,
        readiness=HomeReadinessSummaryOut(percent=engine.readiness.percent)
        if engine.readiness is not None
        else None,
        tabs=_map_tabs(engine.tabs),
        continue_=_map_continue(engine.continue_) if engine.continue_ is not None else None,
        up_next=[_map_up_next(entry) for entry in engine.up_next],
        learning_path_etag=engine.learning_path_etag,
    )


def _map_streak(streak: Any) -> HomeStreakOut:
    return HomeStreakOut(
        current=streak.current, longest=streak.longest, extended_today=streak.extended_today
    )


def _map_tabs(tabs: EngineHomeTabs) -> HomeTabsOut:
    return HomeTabsOut(
        learning_path=HomeTabStateOut(
            locked=tabs.learning_path.locked, lock_reason=tabs.learning_path.lock_reason
        ),
        mock_exams=HomeTabStateOut(
            locked=tabs.mock_exams.locked, lock_reason=tabs.mock_exams.lock_reason
        ),
    )


def _map_continue(card: EngineHomeContinue) -> HomeContinueOut:
    return HomeContinueOut(
        kind=card.kind,
        unit_id=card.unit_id,
        unit_display_index=card.unit_display_index,
        lesson_id=card.lesson_id,
        display_index=card.display_index,
        title=card.title,
        action=card.action,
        open_attempt=map_open_attempt(card.open_attempt),
    )


def _map_up_next(entry: EngineHomeUpNext) -> HomeUpNextOut:
    return HomeUpNextOut(
        kind=entry.kind,
        lesson_id=entry.lesson_id,
        display_index=entry.display_index,
        title=entry.title,
        status=entry.status,
    )


# --- Learning path -------------------------------------------------------------


def map_learning_path(engine: EngineLearningPath) -> LearningPathOut:
    # The engine's own iconUrl is always null today (no icon asset id exists yet
    # on LearningPathUnitDTO for the BFF to resolve) — passed through as-is
    # rather than invented, so there's nothing for this mapper to resolve.
    return LearningPathOut(units=[_map_unit(unit) for unit in engine.units])


def _map_unit(unit: Any) -> LearningPathUnitOut:
    return LearningPathUnitOut(
        unit_id=unit.unit_id,
        display_index=unit.display_index,
        title=unit.title,
        icon_url=unit.icon_url,
        locked=unit.locked,
        lock_reason=unit.lock_reason,
        progress=LearningPathUnitProgressOut(
            completed_lessons=unit.progress.completed_lessons,
            total_lessons=unit.progress.total_lessons,
            percent=unit.progress.percent,
        ),
        entries=[_map_entry(entry) for entry in unit.entries],
    )


def _map_entry(entry: Any) -> LearningPathEntryOut:
    return LearningPathEntryOut(
        kind=entry.kind,
        lesson_id=entry.lesson_id,
        display_index=entry.display_index,
        title=entry.title,
        status=entry.status,
        last_result=_map_last_result(entry.last_result) if entry.last_result is not None else None,
        open_attempt=map_open_attempt(entry.open_attempt),
    )


def _map_last_result(result: EngineLessonLastResult) -> LessonLastResultOut:
    return LessonLastResultOut(correct=result.correct, total=result.total)


# --- Readiness -------------------------------------------------------------------


def map_readiness(engine: EngineReadiness) -> ReadinessOut:
    return ReadinessOut(
        percent=engine.percent,
        completed_lessons=engine.completed_lessons,
        total_lessons=engine.total_lessons,
        average_best_accuracy=engine.average_best_accuracy,
        units=[
            ReadinessUnitOut(
                unit_id=unit.unit_id,
                display_index=unit.display_index,
                title=unit.title,
                percent=unit.percent,
                completed_lessons=unit.completed_lessons,
                total_lessons=unit.total_lessons,
                locked=unit.locked,
            )
            for unit in engine.units
        ],
    )


# --- Lesson theory ---------------------------------------------------------------


def map_lesson_detail(
    state: EngineLessonState, *, lesson_id: str, title: str, theory: list[ContentBlockOut]
) -> LessonDetailOut:
    return LessonDetailOut(
        lesson_id=lesson_id,
        display_index=None,
        title=title,
        status=state.status,
        estimated_minutes=state.estimated_minutes,
        question_count=state.question_count,
        open_attempt=map_open_attempt(state.open_attempt),
        theory=theory,
    )


# --- Attempt item hydration --------------------------------------------------------


def item_refs_by_seq(item_refs: list[EngineAttemptItemRef]) -> dict[int, ItemRef]:
    return {ref.seq: ItemRef(question_id=ref.question_id, version=ref.version) for ref in item_refs}


def hydrate_items(
    item_refs: list[EngineAttemptItemRef],
    questions: dict[str, BoostQuestion],
    resolver: AssetUrlResolver,
) -> list[ItemOut]:
    items: list[ItemOut] = []
    for ref in item_refs:
        question = questions.get(ref.question_id)
        if question is None:
            raise ContentNotFoundError(
                f"No cached body for question {ref.question_id} version {ref.version}"
            )
        unit_id = question.shared.module_id
        translation = question.translation
        prompt_blocks = translation.prompt if translation is not None else []
        if not prompt_blocks and translation is not None and translation.question_text:
            # Real Boost (confirmed 2026-11-06) never sends a block-format prompt,
            # only legacy questionText — wrap it rather than render an empty prompt.
            prompt_blocks = text_block(translation.question_text)
        options_by_id = (
            {option.id: option for option in question.translation.options}
            if question.translation is not None
            else {}
        )
        options: list[OptionOut] = []
        for index, option_id in enumerate(ref.option_order):
            option = options_by_id.get(option_id)
            if option is None:
                raise ContentNotFoundError(
                    f"Option {option_id} not found in cached body for question {ref.question_id}"
                )
            options.append(
                OptionOut(
                    key=option.id,
                    label=ascii_uppercase[index],
                    content=_option_content(option, resolver, unit_id=unit_id),
                )
            )
        items.append(
            ItemOut(
                seq=ref.seq,
                phase=ref.phase,
                prompt=render_blocks(prompt_blocks, resolver, unit_id=unit_id),
                options=options,
                answered=bool(ref.answered),
            )
        )
    return items


def _option_content(
    option: QuestionOption, resolver: AssetUrlResolver, *, unit_id: str | None
) -> list[ContentBlockOut]:
    if option.blocks:
        return render_blocks(option.blocks, resolver, unit_id=unit_id)
    if option.text:
        return [TextBlockOut(markdown=option.text)]
    return []


def correct_option_content(
    question: BoostQuestion, option_key: str, resolver: AssetUrlResolver
) -> list[ContentBlockOut]:
    if question.translation is None:
        raise ContentNotFoundError(f"No translation for question {question.id}")
    for option in question.translation.options:
        if option.id == option_key:
            return _option_content(option, resolver, unit_id=question.shared.module_id)
    raise ContentNotFoundError(f"Option {option_key} not found in question {question.id}")


# --- Answer feedback -----------------------------------------------------------------


def map_answer_feedback(
    engine: EngineAnswerFeedback,
    correct_option_content_blocks: list[ContentBlockOut],
    resolver: AssetUrlResolver,
) -> ResponseFeedbackOut:
    explanation_blocks = parse_explanation_blocks(engine.explanation)
    return ResponseFeedbackOut(
        seq=engine.seq,
        is_correct=engine.is_correct,
        selected_option_key=engine.selected_option_key,
        correct_option=CorrectOptionOut(
            key=engine.correct_option_key,
            label=engine.correct_option_label,
            content=correct_option_content_blocks,
        ),
        explanation=render_blocks(explanation_blocks, resolver, unit_id=None),
    )


# --- Phase completion ------------------------------------------------------------


def _map_phase_summary(summary: EnginePhaseSummary | None) -> PhaseSummaryOut | None:
    if summary is None:
        return None
    return PhaseSummaryOut(total=summary.total, correct=summary.correct, wrong=summary.wrong)


def _map_completion_next(next_: EngineCompletionNext | None) -> CompletionNextOut | None:
    if next_ is None:
        return None
    return CompletionNextOut(
        kind=next_.kind,
        lesson_id=next_.lesson_id,
        display_index=next_.display_index,
        title=next_.title,
        status=next_.status,
        action=next_.action,
    )


def _map_completion_progress(
    progress: EngineCompletionProgress | None,
) -> CompletionProgressOut | None:
    if progress is None:
        return None
    return CompletionProgressOut(
        streak=_map_streak(progress.streak),
        daily_challenge=CompletionDailyChallengeOut(
            target=progress.daily_challenge.target,
            progress=progress.daily_challenge.progress,
            completed=progress.daily_challenge.completed,
        ),
        readiness=HomeReadinessSummaryOut(percent=progress.readiness.percent),
        learning_path_etag=progress.learning_path_etag,
    )


def map_lesson_phase_completion(
    engine: EngineAttemptPhaseCompletion, retry_items: list[ItemOut] | None
) -> LessonPhaseCompletionOut:
    retry = (
        RetryOut(total=engine.retry.total, items=retry_items or [])
        if engine.retry is not None
        else None
    )
    return LessonPhaseCompletionOut(
        attempt_id=engine.attempt_id,
        status=engine.status,
        lesson_summary=_map_phase_summary(engine.lesson_summary),
        retry=retry,
        next=_map_completion_next(engine.next),
        progress=_map_completion_progress(engine.progress),
    )


def map_retry_phase_completion(engine: EngineAttemptPhaseCompletion) -> RetryPhaseCompletionOut:
    return RetryPhaseCompletionOut(
        attempt_id=engine.attempt_id,
        status=engine.status,
        retry_summary=_map_phase_summary(engine.retry_summary),
        next=_map_completion_next(engine.next),
        progress=_map_completion_progress(engine.progress),
    )
