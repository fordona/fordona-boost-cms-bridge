"""Recording progress when attempts start and lessons complete (ported from ProgressService)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.core.logging import get_logger
from fordona_connect.learning.progress import store
from fordona_connect.learning.progress.calendar import (
    DEFAULT_TIMEZONE,
    local_date,
    next_streak,
    resolve_timezone,
)

log = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProgressService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._now = now

    async def attempt_started(
        self,
        *,
        learner_id: str,
        lesson_id: str,
        unit_id: str,
        attempt_id: uuid.UUID,
        attempt_no: int,
        started_at: datetime,
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await store.on_attempt_start(
                session,
                learner_id=learner_id,
                lesson_id=lesson_id,
                unit_id=unit_id,
                attempts=attempt_no,
                attempt_id=attempt_id,
                now=started_at,
            )
            # The learning path shows open attempts, so its ETag must change.
            await store.bump_progress_version(session, learner_id, DEFAULT_TIMEZONE)

    async def lesson_completed(
        self,
        session: AsyncSession,
        *,
        learner_id: str,
        lesson_id: str,
        unit_id: str,
        correct: int,
        total: int,
        timezone: str | None,
        now: datetime,
    ) -> None:
        """Record a completed lesson inside the caller's transaction (phase completion)."""
        zone = resolve_timezone(timezone)
        accuracy = (
            (Decimal(correct) / Decimal(total)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if total
            else Decimal(0)
        )

        before = await store.lesson_progress(session, learner_id, lesson_id)
        old_best = (
            before.best_accuracy if before and before.best_accuracy is not None else Decimal(0)
        )
        first_completion = before is None or before.first_completed_at is None
        await store.on_lesson_completed(
            session,
            learner_id=learner_id,
            lesson_id=lesson_id,
            unit_id=unit_id,
            correct=correct,
            total=total,
            accuracy=accuracy,
            now=now,
        )

        today = local_date(now, zone)
        newly_counted = await store.count_lesson_on_day(
            session, learner_id=learner_id, day=today, lesson_id=lesson_id
        )
        summary = await store.summary_for_update(session, learner_id, zone.key)
        streak = next_streak(summary.current_streak, summary.last_active_date, today)
        summary.timezone = zone.key
        summary.progress_version += 1
        summary.completed_lessons += 1 if first_completion else 0
        summary.sum_best_accuracy = Decimal(summary.sum_best_accuracy) + max(
            Decimal(0), accuracy - old_best
        )
        summary.current_streak = streak
        summary.longest_streak = max(summary.longest_streak, streak)
        summary.last_active_date = today
        await session.flush()
        log.info(
            "lesson_completion_recorded",
            lesson_id=lesson_id,
            first_completion=first_completion,
            counted_today=newly_counted,
            streak=streak,
        )
