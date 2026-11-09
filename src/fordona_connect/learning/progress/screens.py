"""Home, learning path, readiness and completion summaries (ported from the engine).

Every method returns the ``Engine*`` model the public routes already map, so the
routes switch from the engine to this service unchanged.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.core.logging import get_logger
from fordona_connect.learning.content.snapshot import ContentSnapshot, SnapshotProvider
from fordona_connect.learning.entitlement import Entitlement, SubscriptionSource
from fordona_connect.learning.progress import store
from fordona_connect.learning.progress.calendar import (
    displayed_streak,
    local_date,
    next_midnight,
    resolve_timezone,
    week_days,
    week_start,
)
from fordona_connect.learning.progress.models import LessonProgress
from fordona_connect.learning.theory_models import (
    TheoryCompletionNext,
    TheoryCompletionProgress,
    TheoryCompletionProgressDailyChallenge,
    TheoryHome,
    TheoryHomeContinue,
    TheoryHomeDailyChallenge,
    TheoryHomeReadiness,
    TheoryHomeStreak,
    TheoryHomeTabs,
    TheoryHomeTabState,
    TheoryHomeUpNext,
    TheoryHomeUser,
    TheoryHomeWeek,
    TheoryHomeWeekDay,
    TheoryLearningPath,
    TheoryLearningPathEntry,
    TheoryLearningPathUnit,
    TheoryLearningPathUnitProgress,
    TheoryLessonLastResult,
    TheoryLessonOpenAttemptRef,
    TheoryReadiness,
    TheoryReadinessUnit,
)
from fordona_connect.learning.unlock import LessonUnlock, UnlockStatus, resolve_unlocks

log = get_logger(__name__)

_DAILY_CHALLENGE_TYPE = "COMPLETE_LESSONS"
_MOCK_EXAMS_NOT_AVAILABLE = "NOT_AVAILABLE"
_SUBSCRIPTION_LOCK = "SUBSCRIPTION"


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    first_name: str
    last_name: str


class ProfileSource(Protocol):
    """The learner's name, a platform fact (fordona-engine); phase L6 implements it."""

    async def profile(self, learner_id: str) -> LearnerProfile: ...


def title_in(title: Mapping[str, str], locale: str) -> str:
    if not title:
        return ""
    return title.get(locale) or next(iter(title.values()))


def unit_index(snapshot: ContentSnapshot, unit_id: str) -> str:
    for position, unit in enumerate(snapshot.units, start=1):
        if unit.unit_id == unit_id:
            return str(position)
    return ""


def lesson_index(snapshot: ContentSnapshot, unit_id: str, lesson_id: str) -> str:
    unit_position = unit_index(snapshot, unit_id)
    for position, lesson in enumerate(snapshot.lessons_of(unit_id), start=1):
        if lesson.lesson_id == lesson_id:
            return f"{unit_position}.{position}"
    return ""


def readiness_percent(sum_best_accuracy: Decimal, total_lessons: int) -> int:
    if total_lessons == 0:
        return 0
    return round(100.0 * float(sum_best_accuracy) / total_lessons)


def learning_path_etag(
    release_id: int, progress_version: int, subscribed: bool, locale: str
) -> str:
    return f'"{release_id}.{progress_version}.{"sub" if subscribed else "free"}.{locale}"'


@dataclass(frozen=True, slots=True)
class _Continue:
    action: str  # CONTINUE, START or UPGRADE
    target: LessonUnlock
    open_attempt: LessonProgress | None


def _first_incomplete(unlocks: Sequence[LessonUnlock]) -> LessonUnlock | None:
    return next((u for u in unlocks if u.status is not UnlockStatus.COMPLETED), None)


def resolve_continue(
    unlocks: Sequence[LessonUnlock], progress: Sequence[LessonProgress]
) -> _Continue | None:
    """An open attempt (the most recent) wins; otherwise the next lesson to take."""
    open_rows = [row for row in progress if row.open_attempt_id is not None]
    if open_rows:
        row = max(open_rows, key=lambda r: r.updated_at)
        target = next(
            (u for u in unlocks if u.lesson_id == row.lesson_id),
            LessonUnlock(row.lesson_id, row.unit_id, UnlockStatus.COMPLETED),
        )
        return _Continue("CONTINUE", target, row)
    first = _first_incomplete(unlocks)
    if first is None:
        return None
    return _Continue("START" if first.status is UnlockStatus.CURRENT else "UPGRADE", first, None)


def resolve_up_next(unlocks: Sequence[LessonUnlock]) -> LessonUnlock | None:
    first = _first_incomplete(unlocks)
    if first is None:
        return None
    index = unlocks.index(first)
    return unlocks[index + 1] if index + 1 < len(unlocks) else None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ProgressScreens:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        snapshots: SnapshotProvider,
        subscriptions: SubscriptionSource,
        profiles: ProfileSource,
        *,
        week_starts_on: str = "SUNDAY",
        daily_challenge_lessons: int = 3,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._snapshots = snapshots
        self._subscriptions = subscriptions
        self._profiles = profiles
        self._week_starts_on = week_starts_on
        self._daily_target = daily_challenge_lessons
        self._now = now

    async def _context(self, learner_id: str) -> tuple[ContentSnapshot, Entitlement]:
        snapshot = await self._snapshots.get()
        subscribed = await self._subscriptions.is_subscribed(learner_id)
        return snapshot, Entitlement(snapshot, subscribed=subscribed)

    @staticmethod
    def _unlocks(
        snapshot: ContentSnapshot, progress: Sequence[LessonProgress], entitlement: Entitlement
    ) -> list[LessonUnlock]:
        completed = {row.lesson_id for row in progress if row.status == "COMPLETED"}
        return resolve_unlocks(snapshot, completed, entitlement.unit_entitled)

    # --- home -------------------------------------------------------------

    async def home(self, learner_id: str, *, locale: str, timezone: str | None) -> TheoryHome:
        snapshot, entitlement = await self._context(learner_id)
        zone = resolve_timezone(timezone)
        now = self._now()
        today = local_date(now, zone)
        profile = await self._profiles.profile(learner_id)
        initials = "".join(
            name[0].upper() for name in (profile.first_name, profile.last_name) if name
        )

        async with self._sessionmaker() as session:
            progress = await store.all_progress(session, learner_id)
            summary = await store.summary(session, learner_id)
            start = week_start(today, self._week_starts_on)
            lessons_by_date = await store.activity_days(
                session, learner_id, start, today + timedelta(days=6)
            )
            mock_exams = await store.any_mock_exam(session)

        unlocks = self._unlocks(snapshot, progress, entitlement)
        continue_card = None
        resolved = resolve_continue(unlocks, progress)
        if resolved is not None:
            target = resolved.target
            lesson = snapshot.lesson(target.lesson_id)
            continue_card = TheoryHomeContinue(
                kind="lesson",
                unit_id=target.unit_id,
                unit_display_index=unit_index(snapshot, target.unit_id),
                lesson_id=target.lesson_id,
                display_index=lesson_index(snapshot, target.unit_id, target.lesson_id),
                title=title_in(lesson.title, locale) if lesson else "",
                action=resolved.action,
                open_attempt=(
                    TheoryLessonOpenAttemptRef(
                        attempt_id=str(resolved.open_attempt.open_attempt_id),
                        phase=resolved.open_attempt.status,
                    )
                    if resolved.open_attempt is not None
                    else None
                ),
            )
        up_next = []
        if (next_unlock := resolve_up_next(unlocks)) is not None:
            lesson = snapshot.lesson(next_unlock.lesson_id)
            up_next.append(
                TheoryHomeUpNext(
                    kind="lesson",
                    lesson_id=next_unlock.lesson_id,
                    display_index=lesson_index(
                        snapshot, next_unlock.unit_id, next_unlock.lesson_id
                    ),
                    title=title_in(lesson.title, locale) if lesson else "",
                    status=next_unlock.status.value,
                )
            )

        current = summary.current_streak if summary else 0
        longest = summary.longest_streak if summary else 0
        last_active = summary.last_active_date if summary else None
        streak = displayed_streak(current, longest, last_active, today)
        today_count = lessons_by_date.get(today, 0)
        sum_best = Decimal(summary.sum_best_accuracy) if summary else Decimal(0)
        progress_version = summary.progress_version if summary else 0

        return TheoryHome.model_validate(
            {
                "user": TheoryHomeUser(initials=initials, first_name=profile.first_name),
                "week": TheoryHomeWeek(
                    timezone=zone.key,
                    starts_on=self._week_starts_on,
                    days=[
                        TheoryHomeWeekDay(
                            date=day.date.isoformat(), status=day.status, done=day.done
                        )
                        for day in week_days(today, self._week_starts_on, lessons_by_date)
                    ],
                ),
                "daily_challenge": TheoryHomeDailyChallenge(
                    type=_DAILY_CHALLENGE_TYPE,
                    target=self._daily_target,
                    progress=today_count,
                    completed=today_count >= self._daily_target,
                    resets_at=_iso(next_midnight(now, zone)),
                ),
                "streak": TheoryHomeStreak(
                    current=streak.current,
                    longest=streak.longest,
                    extended_today=streak.extended_today,
                ),
                "readiness": TheoryHomeReadiness(
                    percent=readiness_percent(sum_best, snapshot.total_lessons())
                ),
                "tabs": TheoryHomeTabs(
                    learning_path=TheoryHomeTabState(locked=False),
                    mock_exams=TheoryHomeTabState(
                        locked=not mock_exams,
                        lock_reason=None if mock_exams else _MOCK_EXAMS_NOT_AVAILABLE,
                    ),
                ),
                "continue": continue_card,
                "up_next": up_next,
                "learning_path_etag": learning_path_etag(
                    snapshot.release_id, progress_version, entitlement.subscribed, locale
                ),
            }
        )

    # --- learning path ------------------------------------------------------

    async def learning_path_etag(self, learner_id: str, *, locale: str) -> str:
        snapshot, entitlement = await self._context(learner_id)
        async with self._sessionmaker() as session:
            summary = await store.summary(session, learner_id)
        return learning_path_etag(
            snapshot.release_id,
            summary.progress_version if summary else 0,
            entitlement.subscribed,
            locale,
        )

    async def learning_path(self, learner_id: str, *, locale: str) -> TheoryLearningPath:
        snapshot, entitlement = await self._context(learner_id)
        async with self._sessionmaker() as session:
            progress = await store.all_progress(session, learner_id)
        by_lesson = {row.lesson_id: row for row in progress}
        unlock_by_lesson = {u.lesson_id: u for u in self._unlocks(snapshot, progress, entitlement)}

        units = []
        for unit in snapshot.units:
            lessons = snapshot.lessons_of(unit.unit_id)
            entries = []
            completed = 0
            for lesson in lessons:
                unlock = unlock_by_lesson.get(lesson.lesson_id)
                status = unlock.status if unlock else UnlockStatus.LOCKED
                completed += status is UnlockStatus.COMPLETED
                row = by_lesson.get(lesson.lesson_id)
                last_result = None
                if (
                    status is UnlockStatus.COMPLETED
                    and row is not None
                    and row.last_lesson_correct is not None
                    and row.last_lesson_total is not None
                ):
                    last_result = TheoryLessonLastResult(
                        correct=row.last_lesson_correct, total=row.last_lesson_total
                    )
                entries.append(
                    TheoryLearningPathEntry(
                        kind="lesson",
                        lesson_id=lesson.lesson_id,
                        display_index=lesson_index(snapshot, unit.unit_id, lesson.lesson_id),
                        title=title_in(lesson.title, locale),
                        status=status.value,
                        last_result=last_result,
                        open_attempt=(
                            TheoryLessonOpenAttemptRef(
                                attempt_id=str(row.open_attempt_id), phase=row.status
                            )
                            if row is not None and row.open_attempt_id is not None
                            else None
                        ),
                    )
                )
            locked = not entitlement.unit_entitled(unit.unit_id)
            total = len(lessons)
            units.append(
                TheoryLearningPathUnit(
                    unit_id=unit.unit_id,
                    display_index=unit_index(snapshot, unit.unit_id),
                    title=title_in(unit.title, locale),
                    icon_url=None,
                    locked=locked,
                    lock_reason=_SUBSCRIPTION_LOCK if locked else None,
                    progress=TheoryLearningPathUnitProgress(
                        completed_lessons=completed,
                        total_lessons=total,
                        percent=round(100.0 * completed / total) if total else 0,
                    ),
                    entries=entries,
                )
            )
        return TheoryLearningPath(units=units)

    # --- readiness ----------------------------------------------------------

    async def readiness(self, learner_id: str, *, locale: str) -> TheoryReadiness:
        snapshot, entitlement = await self._context(learner_id)
        async with self._sessionmaker() as session:
            by_lesson = {
                row.lesson_id: row for row in await store.all_progress(session, learner_id)
            }

        total_lessons = 0
        completed_lessons = 0
        sum_best = Decimal(0)
        units = []
        for unit in snapshot.units:
            lessons = snapshot.lessons_of(unit.unit_id)
            unit_completed = 0
            unit_sum = Decimal(0)
            for lesson in lessons:
                row = by_lesson.get(lesson.lesson_id)
                if row is not None and row.status == "COMPLETED":
                    unit_completed += 1
                if row is not None and row.best_accuracy is not None:
                    unit_sum += row.best_accuracy
            units.append(
                TheoryReadinessUnit(
                    unit_id=unit.unit_id,
                    display_index=unit_index(snapshot, unit.unit_id),
                    title=title_in(unit.title, locale),
                    percent=readiness_percent(unit_sum, len(lessons)),
                    completed_lessons=unit_completed,
                    total_lessons=len(lessons),
                    locked=not entitlement.unit_entitled(unit.unit_id),
                )
            )
            total_lessons += len(lessons)
            completed_lessons += unit_completed
            sum_best += unit_sum
        average = (
            (sum_best / completed_lessons).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if completed_lessons
            else Decimal(0)
        )
        return TheoryReadiness(
            percent=readiness_percent(sum_best, total_lessons),
            completed_lessons=completed_lessons,
            total_lessons=total_lessons,
            average_best_accuracy=float(average),
            units=units,
        )

    # --- completion summaries ---------------------------------------------

    async def completion_next(self, learner_id: str, *, locale: str) -> TheoryCompletionNext | None:
        """The forward pointer after a completed attempt: never an open retake elsewhere."""
        snapshot, entitlement = await self._context(learner_id)
        async with self._sessionmaker() as session:
            progress = await store.all_progress(session, learner_id)
        resolved = resolve_continue(self._unlocks(snapshot, progress, entitlement), ())
        if resolved is None:
            return None
        target = resolved.target
        lesson = snapshot.lesson(target.lesson_id)
        return TheoryCompletionNext(
            kind="lesson",
            lesson_id=target.lesson_id,
            display_index=lesson_index(snapshot, target.unit_id, target.lesson_id),
            title=title_in(lesson.title, locale) if lesson else "",
            status=target.status.value,
            action=resolved.action,
        )

    async def completion_progress(
        self, learner_id: str, *, locale: str, timezone: str | None
    ) -> TheoryCompletionProgress:
        snapshot, entitlement = await self._context(learner_id)
        zone = resolve_timezone(timezone)
        today = local_date(self._now(), zone)
        async with self._sessionmaker() as session:
            summary = await store.summary(session, learner_id)
            today_count = (await store.activity_days(session, learner_id, today, today)).get(
                today, 0
            )
        streak = displayed_streak(
            summary.current_streak if summary else 0,
            summary.longest_streak if summary else 0,
            summary.last_active_date if summary else None,
            today,
        )
        sum_best = Decimal(summary.sum_best_accuracy) if summary else Decimal(0)
        return TheoryCompletionProgress(
            streak=TheoryHomeStreak(
                current=streak.current, longest=streak.longest, extended_today=streak.extended_today
            ),
            daily_challenge=TheoryCompletionProgressDailyChallenge(
                target=self._daily_target,
                progress=today_count,
                completed=today_count >= self._daily_target,
            ),
            readiness=TheoryHomeReadiness(
                percent=readiness_percent(sum_best, snapshot.total_lessons())
            ),
            learning_path_etag=learning_path_etag(
                snapshot.release_id,
                summary.progress_version if summary else 0,
                entitlement.subscribed,
                locale,
            ),
        )
