"""Database access for progress. Every function runs in the caller's session."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fordona_connect.learning.content.models import ContentMockExam
from fordona_connect.learning.progress.models import (
    LearnerActivityDay,
    LearnerActivityLesson,
    LearnerSummary,
    LessonProgress,
)


async def all_progress(session: AsyncSession, learner_id: str) -> list[LessonProgress]:
    return list(
        await session.scalars(select(LessonProgress).where(LessonProgress.learner_id == learner_id))
    )


async def lesson_progress(
    session: AsyncSession, learner_id: str, lesson_id: str
) -> LessonProgress | None:
    return await session.get(LessonProgress, (learner_id, lesson_id))


async def on_attempt_start(
    session: AsyncSession,
    *,
    learner_id: str,
    lesson_id: str,
    unit_id: str,
    attempts: int,
    attempt_id: UUID,
    now: datetime,
) -> None:
    """A retaken lesson stays COMPLETED; a never-completed one becomes IN_PROGRESS."""
    statement = pg_insert(LessonProgress).values(
        learner_id=learner_id,
        lesson_id=lesson_id,
        unit_id=unit_id,
        status="IN_PROGRESS",
        attempts=attempts,
        open_attempt_id=attempt_id,
        updated_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[LessonProgress.learner_id, LessonProgress.lesson_id],
            set_={
                "status": case(
                    (LessonProgress.status == "COMPLETED", "COMPLETED"), else_="IN_PROGRESS"
                ),
                "attempts": statement.excluded.attempts,
                "open_attempt_id": statement.excluded.open_attempt_id,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )


async def on_lesson_completed(
    session: AsyncSession,
    *,
    learner_id: str,
    lesson_id: str,
    unit_id: str,
    correct: int,
    total: int,
    accuracy: Decimal,
    now: datetime,
) -> None:
    """Best results only ever grow; the first completion time is kept."""
    statement = pg_insert(LessonProgress).values(
        learner_id=learner_id,
        lesson_id=lesson_id,
        unit_id=unit_id,
        status="COMPLETED",
        attempts=0,
        open_attempt_id=None,
        last_lesson_correct=correct,
        last_lesson_total=total,
        best_lesson_correct=correct,
        best_accuracy=accuracy,
        first_completed_at=now,
        updated_at=now,
    )
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[LessonProgress.learner_id, LessonProgress.lesson_id],
            set_={
                "status": "COMPLETED",
                "open_attempt_id": None,
                "last_lesson_correct": excluded.last_lesson_correct,
                "last_lesson_total": excluded.last_lesson_total,
                "best_lesson_correct": func.greatest(
                    LessonProgress.best_lesson_correct, excluded.best_lesson_correct
                ),
                "best_accuracy": func.greatest(
                    LessonProgress.best_accuracy, excluded.best_accuracy
                ),
                "first_completed_at": func.coalesce(
                    LessonProgress.first_completed_at, excluded.first_completed_at
                ),
                "updated_at": excluded.updated_at,
            },
        )
    )


async def count_lesson_on_day(
    session: AsyncSession, *, learner_id: str, day: date, lesson_id: str
) -> bool:
    """Record the lesson as completed on ``day``; ``False`` if it already was."""
    inserted = await session.execute(
        pg_insert(LearnerActivityLesson)
        .values(learner_id=learner_id, local_date=day, lesson_id=lesson_id)
        .on_conflict_do_nothing()
        .returning(LearnerActivityLesson.lesson_id)
    )
    if inserted.first() is None:
        return False
    statement = pg_insert(LearnerActivityDay).values(
        learner_id=learner_id, local_date=day, lessons_completed=1
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[LearnerActivityDay.learner_id, LearnerActivityDay.local_date],
            set_={"lessons_completed": LearnerActivityDay.lessons_completed + 1},
        )
    )
    return True


async def summary_for_update(
    session: AsyncSession, learner_id: str, timezone: str
) -> LearnerSummary:
    """The learner's summary row, created on first contact, locked for this transaction."""
    await session.execute(
        pg_insert(LearnerSummary)
        .values(
            learner_id=learner_id,
            timezone=timezone,
            progress_version=0,
            completed_lessons=0,
            sum_best_accuracy=Decimal(0),
            current_streak=0,
            longest_streak=0,
        )
        .on_conflict_do_nothing()
    )
    summary = await session.scalar(
        select(LearnerSummary)
        .where(LearnerSummary.learner_id == learner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert summary is not None
    return summary


async def summary(session: AsyncSession, learner_id: str) -> LearnerSummary | None:
    return await session.get(LearnerSummary, learner_id)


async def bump_progress_version(session: AsyncSession, learner_id: str, timezone: str) -> None:
    await summary_for_update(session, learner_id, timezone)
    await session.execute(
        update(LearnerSummary)
        .where(LearnerSummary.learner_id == learner_id)
        .values(progress_version=LearnerSummary.progress_version + 1)
        .execution_options(synchronize_session=False)
    )


async def activity_days(
    session: AsyncSession, learner_id: str, start: date, end: date
) -> dict[date, int]:
    rows = await session.execute(
        select(LearnerActivityDay.local_date, LearnerActivityDay.lessons_completed).where(
            LearnerActivityDay.learner_id == learner_id,
            LearnerActivityDay.local_date.between(start, end),
        )
    )
    return {day: count for day, count in rows}


async def any_mock_exam(session: AsyncSession) -> bool:
    return (await session.scalar(select(ContentMockExam.mock_exam_id).limit(1))) is not None
