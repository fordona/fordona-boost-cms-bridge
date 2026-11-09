"""Starting, reading and answering lesson attempts (ported from the engine's AttemptService).

Responses use the same models the engine client parses (``Engine*``), so the
public routes can switch from the engine to this service without other changes.

Concurrency, as in the engine:

* **start** takes no lock. Two unique indexes (one open attempt per learner and
  lesson; one attempt per request id) arbitrate a double start, and the loser
  returns the winner's attempt.
* **answer** holds a shared lock on the attempt while it answers, so phase
  completion (an exclusive lock, phase L3) never counts totals mid-answer. The
  conditional update is the idempotency check.
"""

import secrets
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.clients.engine.theory import (
    EngineAnswerFeedback,
    EngineAttempt,
    EngineAttemptItemRef,
    EngineLessonOpenAttemptRef,
    EngineLessonState,
)
from fordona_connect.core.errors import ErrorCode
from fordona_connect.core.logging import get_logger
from fordona_connect.learning.attempts import store
from fordona_connect.learning.attempts.models import AttemptItem, LessonAttempt
from fordona_connect.learning.content.snapshot import (
    ContentSnapshot,
    SnapshotLesson,
    SnapshotProvider,
)
from fordona_connect.learning.entitlement import Entitlement, SubscriptionSource
from fordona_connect.learning.errors import (
    AttemptNotFoundError,
    ItemNotFoundError,
    LessonNotFoundError,
    OptionInvalidError,
    PhaseClosedError,
    RequestIdConflictError,
    ResponseConflictError,
    TheoryLessonLockedError,
    TheoryModuleLockedError,
)
from fordona_connect.learning.selection import Selection, Strategy, select_questions
from fordona_connect.learning.unlock import UnlockStatus, unlock_status

log = get_logger(__name__)

FALLBACK_LOCALE = "sv-SE"
# Fallback estimate when Boost gives no reading time: 45 s per question.
_SECONDS_PER_QUESTION = 45
_OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_RANDOM = secrets.SystemRandom()


class ProgressRecorder(Protocol):
    """Progress side effects of attempts. Phase L4 provides the real one."""

    async def attempt_started(
        self,
        *,
        learner_id: str,
        lesson_id: str,
        unit_id: str,
        attempt_id: uuid.UUID,
        attempt_no: int,
        started_at: datetime,
    ) -> None: ...


class NoProgress:
    async def attempt_started(self, **_: Any) -> None:
        return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _shuffle(option_keys: Sequence[str]) -> list[str]:
    shuffled = list(option_keys)
    _RANDOM.shuffle(shuffled)
    return shuffled


class AttemptService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        snapshots: SnapshotProvider,
        subscriptions: SubscriptionSource,
        *,
        strategy: Strategy = Strategy.LESSON_BANK,
        progress: ProgressRecorder | None = None,
        now: Callable[[], datetime] = _utc_now,
        shuffle: Callable[[Sequence[str]], list[str]] = _shuffle,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._snapshots = snapshots
        self._subscriptions = subscriptions
        self._strategy = strategy
        self._progress = progress or NoProgress()
        self._now = now
        self._shuffle = shuffle

    # --- start ------------------------------------------------------------

    async def start(self, learner_id: str, lesson_id: str, request_id: uuid.UUID) -> EngineAttempt:
        async with self._sessionmaker() as session:
            existing = await store.find_by_request(session, learner_id, request_id)
            if existing is not None:
                if existing.lesson_id != lesson_id:
                    raise RequestIdConflictError(
                        f"requestId {request_id} was already used to start a different lesson"
                    )
                return await self._attempt_out(session, existing)
            open_attempt = await store.find_open(session, learner_id, lesson_id)
            if open_attempt is not None:
                return await self._attempt_out(session, open_attempt)

            snapshot = await self._snapshots.get()
            lesson = snapshot.lesson(lesson_id)
            if lesson is None:
                raise LessonNotFoundError(f"Lesson not found: {lesson_id}")
            entitlement = await self._entitlement(snapshot, learner_id)
            await self._check_unlocked(session, snapshot, entitlement, learner_id, lesson)
            attempt_no = await store.count_attempts(session, learner_id, lesson_id) + 1

        selection = select_questions(snapshot, lesson_id, self._strategy)
        if not selection.refs:
            # A visible lesson always has an active question; reaching this means the
            # snapshot and the sync's validation disagree, not something a learner did.
            raise RuntimeError(f"No servable questions for visible lesson {lesson_id}")

        attempt_id = uuid.uuid4()
        started_at = self._now()
        attempt = {
            "attempt_id": attempt_id,
            "learner_id": learner_id,
            "kind": "LESSON",
            "lesson_id": lesson_id,
            "unit_id": lesson.unit_id,
            "challenge_id": selection.refs[0].challenge_id,
            "lesson_version": lesson.current_version,
            "selection_strategy": selection.strategy.value,
            "selection_reason": selection.reason,
            "attempt_no": attempt_no,
            "request_id": request_id,
            "status": "IN_LESSON",
            "policy_snapshot": snapshot.retry_policy_for(lesson.unit_id, lesson_id).to_json(),
            "started_at": started_at,
        }
        items = self._lesson_items(snapshot, attempt_id, learner_id, selection)

        try:
            async with self._sessionmaker() as session, session.begin():
                await store.insert_attempt(session, attempt, items)
        except IntegrityError:
            # A concurrent start won one of the unique indexes: serve its attempt.
            async with self._sessionmaker() as session:
                winner = await store.find_by_request(
                    session, learner_id, request_id
                ) or await store.find_open(session, learner_id, lesson_id)
                if winner is None:
                    raise
                return await self._attempt_out(session, winner)

        await self._progress.attempt_started(
            learner_id=learner_id,
            lesson_id=lesson_id,
            unit_id=lesson.unit_id,
            attempt_id=attempt_id,
            attempt_no=attempt_no,
            started_at=started_at,
        )
        log.info(
            "attempt_started",
            attempt_id=str(attempt_id),
            lesson_id=lesson_id,
            attempt_no=attempt_no,
            strategy=selection.strategy.value,
            questions=len(items),
        )
        return EngineAttempt(
            attempt_id=str(attempt_id),
            status="IN_LESSON",
            attempt_no=attempt_no,
            items=[_item_ref_from_row(row) for row in items],
        )

    # --- read ---------------------------------------------------------------

    async def get(self, learner_id: str, attempt_id: uuid.UUID) -> EngineAttempt:
        async with self._sessionmaker() as session:
            attempt = await store.get_attempt(session, attempt_id)
            if attempt is None or attempt.learner_id != learner_id:
                raise AttemptNotFoundError(f"Attempt not found: {attempt_id}")
            return await self._attempt_out(session, attempt)

    async def lesson_state(self, learner_id: str, lesson_id: str) -> EngineLessonState:
        snapshot = await self._snapshots.get()
        lesson = snapshot.lesson(lesson_id)
        if lesson is None:
            raise LessonNotFoundError(f"Lesson not found: {lesson_id}")
        entitlement = await self._entitlement(snapshot, learner_id)
        async with self._sessionmaker() as session:
            completed = await store.completed_lesson_ids(session, learner_id)
            status = unlock_status(snapshot, lesson_id, completed, entitlement.unit_entitled)
            if status is None:
                raise LessonNotFoundError(f"Lesson not found: {lesson_id}")
            locked = status is UnlockStatus.LOCKED
            lock_reason = None
            if locked:
                lock_reason = (
                    ErrorCode.THEORY_LESSON_LOCKED
                    if entitlement.unit_entitled(lesson.unit_id)
                    else ErrorCode.THEORY_MODULE_LOCKED
                )
            open_attempt = None if locked else await store.find_open(session, learner_id, lesson_id)
            open_ref = None
            if open_attempt is not None:
                open_ref = EngineLessonOpenAttemptRef(
                    attempt_id=str(open_attempt.attempt_id), phase=open_attempt.status
                )
                question_count = sum(
                    1
                    for row in await store.items_of(session, open_attempt.attempt_id)
                    if row.phase == "LESSON"
                )
            elif locked:
                # Never compute anything for a unit the learner may not open.
                question_count = 0
            else:
                question_count = len(select_questions(snapshot, lesson_id, self._strategy).refs)

        return EngineLessonState(
            status=status.value,
            locked=locked,
            lock_reason=lock_reason,
            open_attempt=open_ref,
            question_count=question_count,
            estimated_minutes=_estimated_minutes(lesson, question_count),
            lesson_version=lesson.current_version or "",
        )

    # --- answer -------------------------------------------------------------

    async def answer(
        self,
        learner_id: str,
        attempt_id: uuid.UUID,
        *,
        seq: int,
        selected_option_key: str,
        response_id: uuid.UUID,
        duration_ms: int | None,
        locale: str,
    ) -> EngineAnswerFeedback:
        snapshot = await self._snapshots.get()
        async with self._sessionmaker() as session, session.begin():
            attempt = await store.get_attempt(session, attempt_id, lock="share")
            if attempt is None or attempt.learner_id != learner_id:
                raise AttemptNotFoundError(f"Attempt not found: {attempt_id}")
            if attempt.status == "COMPLETED":
                raise PhaseClosedError("Attempt already completed")
            item = await store.item(session, attempt_id, seq)
            if item is None:
                raise ItemNotFoundError(f"No item at seq={seq} for attempt {attempt_id}")
            expected_phase = "RETRY" if attempt.status == "IN_RETRY" else "LESSON"
            if item.phase != expected_phase:
                raise PhaseClosedError(f"seq={seq} is not in the attempt's current phase")

            revision = await store.load_revision(session, item.question_id, item.version)
            if revision is None:
                raise RuntimeError(f"Pinned revision missing: {item.question_id}:{item.version}")
            if selected_option_key not in revision.option_keys:
                raise OptionInvalidError(
                    f"Not a valid option for this question: {selected_option_key}"
                )
            is_correct = selected_option_key == revision.correct_option_key
            now = self._now()

            try:
                async with session.begin_nested():
                    affected = await store.answer_item(
                        session,
                        attempt_id=attempt_id,
                        seq=seq,
                        selected_option_key=selected_option_key,
                        is_correct=is_correct,
                        duration_ms=duration_ms,
                        response_id=response_id,
                        now=now,
                    )
            except IntegrityError as exc:
                raise ResponseConflictError(
                    f"responseId {response_id} was already used for a different item"
                ) from exc

            if affected == 0:
                # Answered already: by this exact call (a replay) or a different one.
                await session.refresh(item)
                if (
                    item.response_id == response_id
                    and item.selected_option_key == selected_option_key
                ):
                    return _feedback(
                        item, revision.correct_option_key, revision.explanation, locale
                    )
                raise ResponseConflictError(
                    f"seq={seq} was already answered with a different option"
                )

            await self._update_ledger(session, snapshot, learner_id, item, attempt, is_correct, now)
            await session.refresh(item)
            return _feedback(item, revision.correct_option_key, revision.explanation, locale)

    # --- helpers --------------------------------------------------------------

    async def _entitlement(self, snapshot: ContentSnapshot, learner_id: str) -> Entitlement:
        return Entitlement(snapshot, subscribed=await self._subscriptions.is_subscribed(learner_id))

    async def _check_unlocked(
        self,
        session: AsyncSession,
        snapshot: ContentSnapshot,
        entitlement: Entitlement,
        learner_id: str,
        lesson: SnapshotLesson,
    ) -> None:
        completed = await store.completed_lesson_ids(session, learner_id)
        status = unlock_status(snapshot, lesson.lesson_id, completed, entitlement.unit_entitled)
        if status is None:
            raise LessonNotFoundError(f"Lesson not found: {lesson.lesson_id}")
        if status is not UnlockStatus.LOCKED:
            return  # CURRENT, or COMPLETED (a retake)
        if not entitlement.unit_entitled(lesson.unit_id):
            raise TheoryModuleLockedError(f"Unit not entitled: {lesson.unit_id}")
        raise TheoryLessonLockedError(f"Previous lesson not completed: {lesson.lesson_id}")

    def _lesson_items(
        self,
        snapshot: ContentSnapshot,
        attempt_id: uuid.UUID,
        learner_id: str,
        selection: Selection,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for seq, ref in enumerate(selection.refs, start=1):
            question = snapshot.question(ref.question_id)
            if question is None:
                raise RuntimeError(f"Selected question not in snapshot: {ref.question_id}")
            items.append(
                {
                    "attempt_id": attempt_id,
                    "seq": seq,
                    "learner_id": learner_id,
                    "phase": "LESSON",
                    "item_source": "CHALLENGE" if ref.challenge_id else "BANK",
                    "question_id": ref.question_id,
                    "version": ref.version,
                    "challenge_id": ref.challenge_id,
                    "option_order": self._shuffle(question.option_keys),
                    "domain_code": question.domain_code,
                    "topic_tag": question.topic_tag,
                    "difficulty": question.difficulty,
                    "level": question.level,
                }
            )
        return items

    async def _attempt_out(self, session: AsyncSession, attempt: LessonAttempt) -> EngineAttempt:
        items = await store.items_of(session, attempt.attempt_id)
        return EngineAttempt(
            attempt_id=str(attempt.attempt_id),
            status=attempt.status,
            attempt_no=attempt.attempt_no,
            items=[_item_ref(item) for item in items],
        )

    async def _update_ledger(
        self,
        session: AsyncSession,
        snapshot: ContentSnapshot,
        learner_id: str,
        item: AttemptItem,
        attempt: LessonAttempt,
        is_correct: bool,
        now: datetime,
    ) -> None:
        if not is_correct:
            question = snapshot.question(item.question_id)
            home_lesson_id = (question.home_lesson_id if question else None) or attempt.lesson_id
            await store.record_wrong(
                session,
                learner_id=learner_id,
                question_id=item.question_id,
                home_lesson_id=home_lesson_id,
                unit_id=attempt.unit_id,
                now=now,
            )
            return
        mistake = await store.find_mistake(session, learner_id, item.question_id)
        if mistake is None or mistake.status != "OPEN":
            return
        if item.phase == "RETRY":
            resolved_via = "REPEAT"
        elif attempt.lesson_id == mistake.home_lesson_id:
            resolved_via = "RETAKE"
        else:
            resolved_via = "LATER"
        await store.resolve_mistake(
            session,
            learner_id=learner_id,
            question_id=item.question_id,
            resolved_via=resolved_via,
            now=now,
        )


def _item_ref(item: AttemptItem) -> EngineAttemptItemRef:
    return EngineAttemptItemRef(
        seq=item.seq,
        phase=item.phase,
        question_id=item.question_id,
        version=item.version,
        option_order=list(item.option_order),
        answered=item.answered_at is not None,
    )


def _item_ref_from_row(row: dict[str, Any]) -> EngineAttemptItemRef:
    return EngineAttemptItemRef(
        seq=row["seq"],
        phase=row["phase"],
        question_id=row["question_id"],
        version=row["version"],
        option_order=list(row["option_order"]),
        answered=False,
    )


def _feedback(
    item: AttemptItem, correct_key: str, explanation: dict[str, Any], locale: str
) -> EngineAnswerFeedback:
    order = list(item.option_order)
    label = _OPTION_LABELS[order.index(correct_key)] if correct_key in order else ""
    return EngineAnswerFeedback(
        seq=item.seq,
        is_correct=bool(item.is_correct),
        selected_option_key=item.selected_option_key or "",
        correct_option_key=correct_key,
        correct_option_label=label,
        explanation=explanation.get(locale, explanation.get(FALLBACK_LOCALE)),
    )


def _estimated_minutes(lesson: SnapshotLesson, question_count: int) -> int:
    if lesson.estimated_minutes is not None:
        return lesson.estimated_minutes
    return -(-question_count * _SECONDS_PER_QUESTION // 60)
