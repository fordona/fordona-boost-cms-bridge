"""Orchestrates the public theory API (Plan §7.3, P6.T5).

One engine call per route (the plan's own call-count table); Boost is touched
only on a body-cache miss, and never at all for a locked lesson (security
invariant #2 — the BFF fetches no theory until the engine says it may).

**Splitting ``AttemptDTO.items`` (a decision, logged in ``PROGRESS__STATUS.md``):**
the engine's ``AttemptDTO`` has one flat ``items`` list, each item tagged with
its own ``phase`` ("LESSON"/"RETRY") — there is no separate ``retry`` field on
the DTO itself, unlike the phase-completion response. The public contract's
own example shows resume splitting these into ``items`` (the lesson phase) and
``retry.items`` (the retry phase) when ``status`` is ``IN_RETRY``, so this
service partitions the flat list by each item's ``phase`` rather than asking
the engine to change shape — the per-item ``phase`` field exists precisely to
make that split possible.
"""

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from fordona_connect.cache.attempt_refs import AttemptRefCache
from fordona_connect.clients.boost.models import BoostQuestion
from fordona_connect.core.errors import (
    ContentNotFoundError,
    ErrorCode,
    TheoryLessonLockedError,
    TheoryModuleLockedError,
)
from fordona_connect.learning.theory_models import (
    TheoryAttempt,
    TheoryAttemptItemRef,
)
from fordona_connect.schemas.theory import (
    AttemptOut,
    HomeOut,
    ItemOut,
    LearningPathOut,
    LessonDetailOut,
    LessonPhaseCompletionOut,
    MockExamDetailOut,
    MockExamSummaryOut,
    ReadinessOut,
    ResponseFeedbackOut,
    RetryOut,
    RetryPhaseCompletionOut,
)
from fordona_connect.services import theory_mappers as mappers
from fordona_connect.services.blocks import render_blocks
from fordona_connect.services.body_cache import BodyCache, QuestionRef
from fordona_connect.services.content_html import html_to_blocks
from fordona_connect.services.media import AssetUrlResolver
from fordona_connect.services.release_prefetch import ReleasePrefetchGate, ReleasePrefetchRunner

if TYPE_CHECKING:
    from fordona_connect.learning.backend import TheoryBackend


class TheoryService:
    def __init__(
        self,
        backend: "TheoryBackend",
        body_cache: BodyCache,
        attempt_refs: AttemptRefCache,
        resolver: AssetUrlResolver,
        *,
        prefetch_gate: ReleasePrefetchGate | None = None,
        prefetch_runner: ReleasePrefetchRunner | None = None,
    ) -> None:
        self._backend = backend
        self._bodies = body_cache
        self._attempt_refs = attempt_refs
        self._resolver = resolver
        # Both None unless CONTENT_PREFETCH_ON_RELEASE=true (Plan §9.1/§9.4, P6.T7) —
        # kept as a pair rather than one "enabled" flag so a disabled feature costs
        # this service nothing beyond the None check below, no Redis call included.
        self._prefetch_gate = prefetch_gate
        self._prefetch_runner = prefetch_runner
        self._prefetch_tasks: set[asyncio.Task[None]] = set()

    # --- Home, learning path, readiness ----------------------------------------

    async def home(self, *, locale: str, timezone: str | None) -> HomeOut:
        engine_home = await self._backend.get_home(accept_language=locale, timezone=timezone)
        await self._maybe_prefetch(engine_home.learning_path_etag)
        return mappers.map_home(engine_home)

    async def learning_path(
        self, *, locale: str, if_none_match: str | None
    ) -> tuple[LearningPathOut | None, str | None, bool]:
        path, etag, not_modified = await self._backend.get_learning_path(
            accept_language=locale, if_none_match=if_none_match
        )
        if etag:
            await self._maybe_prefetch(etag)
        if not_modified or path is None:
            return None, etag, True
        return mappers.map_learning_path(path), etag, False

    async def readiness(self, *, locale: str) -> ReadinessOut:
        engine_readiness = await self._backend.get_readiness(accept_language=locale)
        return mappers.map_readiness(engine_readiness)

    # --- Mock exams (read-only browsing, 2026-11-07) ------------------------------

    async def list_mock_exams(self, *, locale: str) -> list[MockExamSummaryOut]:
        exams = await self._backend.list_mock_exams(accept_language=locale)
        return [mappers.map_mock_exam_summary(exam) for exam in exams]

    async def mock_exam_detail(self, mock_exam_id: str, *, locale: str) -> MockExamDetailOut:
        exam = await self._backend.get_mock_exam(mock_exam_id, accept_language=locale)
        refs = [QuestionRef(id=item.question_id, version=item.version) for item in exam.items]
        found, missing = await self._bodies.get_question_revisions(refs, locale)
        if missing:
            raise ContentNotFoundError(
                f"Missing cached bodies for {len(missing)} question(s) in mock exam {mock_exam_id}"
            )
        questions = mappers.hydrate_mock_exam_questions(exam.items, found, self._resolver)
        return mappers.map_mock_exam_detail(exam, questions)

    # --- Lesson theory -----------------------------------------------------------

    async def lesson_detail(self, lesson_id: str, *, locale: str) -> LessonDetailOut:
        state = await self._backend.get_lesson_state(lesson_id)
        if state.locked:
            if state.lock_reason == ErrorCode.THEORY_LESSON_LOCKED:
                raise TheoryLessonLockedError()
            raise TheoryModuleLockedError()

        lesson = await self._bodies.get_lesson_revision(lesson_id, state.lesson_version, locale)
        blocks = lesson.translation.blocks if lesson.translation is not None else []
        if not blocks and lesson.translation is not None and lesson.translation.content_html:
            # Real Boost (confirmed 2026-11-06) never sends block-format lesson theory,
            # only legacy contentHtml — convert it rather than render nothing.
            blocks = html_to_blocks(lesson.translation.content_html, source=f"lesson:{lesson_id}")
        theory = render_blocks(blocks, self._resolver, unit_id=lesson.shared.module_id)
        title = (
            lesson.translation.title
            if lesson.translation is not None and lesson.translation.title
            else ""
        )
        return mappers.map_lesson_detail(state, lesson_id=lesson_id, title=title, theory=theory)

    # --- Attempts ------------------------------------------------------------------

    async def start_attempt(self, lesson_id: str, *, request_id: UUID, locale: str) -> AttemptOut:
        attempt = await self._backend.start_attempt(lesson_id, str(request_id))
        return await self._build_attempt_out(attempt, lesson_id=lesson_id, locale=locale)

    async def get_attempt(self, attempt_id: UUID, *, locale: str) -> AttemptOut:
        attempt = await self._backend.get_attempt(str(attempt_id))
        # lessonId has no source here (see schemas/theory.py's module docstring):
        # neither AttemptDTO nor a second engine call this route's budget allows.
        return await self._build_attempt_out(attempt, lesson_id=None, locale=locale)

    async def answer(
        self,
        attempt_id: UUID,
        *,
        response_id: UUID,
        seq: int,
        selected_option_key: str,
        duration_ms: int | None,
        locale: str,
    ) -> ResponseFeedbackOut:
        feedback = await self._backend.answer(
            str(attempt_id),
            response_id=str(response_id),
            seq=seq,
            selected_option_key=selected_option_key,
            duration_ms=duration_ms,
            accept_language=locale,
        )
        ref = await self._attempt_refs.get(str(attempt_id), feedback.seq)
        if ref is None:
            # Cold cache (eviction, or a restart between hydrating this attempt and
            # answering): one extra engine call repopulates the mapping rather than
            # ever answering against the wrong question's cached body.
            attempt = await self._backend.get_attempt(str(attempt_id))
            await self._attempt_refs.remember(
                str(attempt_id), mappers.item_refs_by_seq(attempt.items)
            )
            ref = await self._attempt_refs.get(str(attempt_id), feedback.seq)
        if ref is None:
            raise ContentNotFoundError(
                f"No question reference found for attempt {attempt_id} seq {feedback.seq}"
            )

        found, missing = await self._bodies.get_question_revisions(
            [QuestionRef(id=ref.question_id, version=ref.version)], locale
        )
        if missing or ref.question_id not in found:
            raise ContentNotFoundError(
                f"No cached body for question {ref.question_id} version {ref.version}"
            )
        content = mappers.correct_option_content(
            found[ref.question_id], feedback.correct_option_key, self._resolver
        )
        return mappers.map_answer_feedback(feedback, content, self._resolver)

    async def complete_lesson_phase(
        self, attempt_id: UUID, *, locale: str, timezone: str | None
    ) -> LessonPhaseCompletionOut:
        completion = await self._backend.complete_lesson_phase(
            str(attempt_id), accept_language=locale, timezone=timezone
        )
        retry_items_out: list[ItemOut] | None = None
        if completion.retry is not None and completion.retry.items:
            questions = await self._hydrate_questions(
                completion.retry.items, locale=locale, attempt_id=str(attempt_id)
            )
            retry_items_out = mappers.hydrate_items(
                completion.retry.items, questions, self._resolver
            )
        return mappers.map_lesson_phase_completion(completion, retry_items_out)

    async def complete_retry_phase(
        self, attempt_id: UUID, *, locale: str, timezone: str | None
    ) -> RetryPhaseCompletionOut:
        completion = await self._backend.complete_retry_phase(
            str(attempt_id), accept_language=locale, timezone=timezone
        )
        return mappers.map_retry_phase_completion(completion)

    # --- internals -----------------------------------------------------------------

    async def _maybe_prefetch(self, etag: str) -> None:
        if self._prefetch_gate is None or self._prefetch_runner is None:
            return
        release_id = await self._prefetch_gate.claim(etag)
        if release_id is None:
            return
        task = asyncio.create_task(self._prefetch_runner.run(release_id))
        self._prefetch_tasks.add(task)
        task.add_done_callback(self._prefetch_tasks.discard)

    async def _build_attempt_out(
        self, attempt: TheoryAttempt, *, lesson_id: str | None, locale: str
    ) -> AttemptOut:
        lesson_items = [item for item in attempt.items if item.phase == "LESSON"]
        retry_items = [item for item in attempt.items if item.phase == "RETRY"]

        questions = await self._hydrate_questions(
            lesson_items + retry_items, locale=locale, attempt_id=attempt.attempt_id
        )
        hydrated_lesson = mappers.hydrate_items(lesson_items, questions, self._resolver)
        hydrated_retry = (
            mappers.hydrate_items(retry_items, questions, self._resolver) if retry_items else []
        )
        retry_out = RetryOut(total=len(retry_items), items=hydrated_retry) if retry_items else None

        return AttemptOut(
            attempt_id=attempt.attempt_id,
            lesson_id=lesson_id,
            status=attempt.status,
            question_count=len(lesson_items),
            items=hydrated_lesson,
            retry=retry_out,
        )

    async def _hydrate_questions(
        self, item_refs: list[TheoryAttemptItemRef], *, locale: str, attempt_id: str
    ) -> dict[str, BoostQuestion]:
        if not item_refs:
            return {}
        refs = [QuestionRef(id=item.question_id, version=item.version) for item in item_refs]
        found, missing = await self._bodies.get_question_revisions(refs, locale)
        if missing:
            raise ContentNotFoundError(
                f"Missing cached bodies for {len(missing)} question(s) in attempt {attempt_id}"
            )
        await self._attempt_refs.remember(attempt_id, mappers.item_refs_by_seq(item_refs))
        return found
