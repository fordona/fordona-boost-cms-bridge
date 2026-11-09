"""Database access for attempts. Every function runs in the caller's session."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fordona_connect.learning.attempts.models import AttemptItem, LessonAttempt, Mistake
from fordona_connect.learning.content.models import ContentQuestionRevision

Lock = Literal["share", "update"] | None


async def find_by_request(
    session: AsyncSession, learner_id: str, request_id: UUID
) -> LessonAttempt | None:
    return await session.scalar(
        select(LessonAttempt).where(
            LessonAttempt.learner_id == learner_id, LessonAttempt.request_id == request_id
        )
    )


async def find_open(session: AsyncSession, learner_id: str, lesson_id: str) -> LessonAttempt | None:
    return await session.scalar(
        select(LessonAttempt).where(
            LessonAttempt.learner_id == learner_id,
            LessonAttempt.lesson_id == lesson_id,
            LessonAttempt.status != "COMPLETED",
        )
    )


async def count_attempts(session: AsyncSession, learner_id: str, lesson_id: str) -> int:
    count = await session.scalar(
        select(func.count()).where(
            LessonAttempt.learner_id == learner_id, LessonAttempt.lesson_id == lesson_id
        )
    )
    return int(count or 0)


async def completed_lesson_ids(session: AsyncSession, learner_id: str) -> set[str]:
    rows = await session.scalars(
        select(LessonAttempt.lesson_id)
        .where(LessonAttempt.learner_id == learner_id, LessonAttempt.status == "COMPLETED")
        .distinct()
    )
    return set(rows)


async def get_attempt(
    session: AsyncSession, attempt_id: UUID, *, lock: Lock = None
) -> LessonAttempt | None:
    statement = select(LessonAttempt).where(LessonAttempt.attempt_id == attempt_id)
    if lock == "share":
        statement = statement.with_for_update(read=True)
    elif lock == "update":
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def insert_attempt(
    session: AsyncSession, attempt: dict[str, Any], items: Sequence[dict[str, Any]]
) -> None:
    await session.execute(insert(LessonAttempt).values(**attempt))
    if items:
        await session.execute(insert(AttemptItem), list(items))


async def items_of(session: AsyncSession, attempt_id: UUID) -> list[AttemptItem]:
    rows = await session.scalars(
        select(AttemptItem).where(AttemptItem.attempt_id == attempt_id).order_by(AttemptItem.seq)
    )
    return list(rows)


async def item(session: AsyncSession, attempt_id: UUID, seq: int) -> AttemptItem | None:
    return await session.scalar(
        select(AttemptItem).where(AttemptItem.attempt_id == attempt_id, AttemptItem.seq == seq)
    )


async def answer_item(
    session: AsyncSession,
    *,
    attempt_id: UUID,
    seq: int,
    selected_option_key: str,
    is_correct: bool,
    duration_ms: int | None,
    response_id: UUID,
    now: datetime,
) -> int:
    """Answer an unanswered item; 0 rows means it was answered already.

    This one statement is the idempotency check, the already-answered check and
    the write. A ``response_id`` already used on another item violates its
    unique constraint, which the caller turns into a conflict.
    """
    result = await session.execute(
        update(AttemptItem)
        .where(
            AttemptItem.attempt_id == attempt_id,
            AttemptItem.seq == seq,
            AttemptItem.answered_at.is_(None),
        )
        .values(
            selected_option_key=selected_option_key,
            is_correct=is_correct,
            duration_ms=duration_ms,
            response_id=response_id,
            answered_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def load_revision(
    session: AsyncSession, question_id: str, version: str
) -> ContentQuestionRevision | None:
    return await session.get(ContentQuestionRevision, (question_id, version))


async def record_wrong(
    session: AsyncSession,
    *,
    learner_id: str,
    question_id: str,
    home_lesson_id: str,
    unit_id: str,
    now: datetime,
) -> None:
    statement = pg_insert(Mistake).values(
        learner_id=learner_id,
        question_id=question_id,
        home_lesson_id=home_lesson_id,
        unit_id=unit_id,
        status="OPEN",
        times_wrong=1,
        last_wrong_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Mistake.learner_id, Mistake.question_id],
            set_={
                "status": "OPEN",
                "times_wrong": Mistake.times_wrong + 1,
                "last_wrong_at": now,
            },
        )
    )


async def find_mistake(session: AsyncSession, learner_id: str, question_id: str) -> Mistake | None:
    return await session.get(Mistake, (learner_id, question_id))


async def resolve_mistake(
    session: AsyncSession, *, learner_id: str, question_id: str, resolved_via: str, now: datetime
) -> None:
    await session.execute(
        update(Mistake)
        .where(
            Mistake.learner_id == learner_id,
            Mistake.question_id == question_id,
            Mistake.status == "OPEN",
        )
        .values(status="RESOLVED", resolved_via=resolved_via, resolved_at=now)
        .execution_options(synchronize_session=False)
    )
