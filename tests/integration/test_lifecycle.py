"""The full attempt lifecycle with progress and screens, against Postgres.

Content is seeded through the real content sync from a fake Boost catalogue.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.learning.attempts.models import AttemptItem
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.content.sync import ContentSyncService
from fordona_connect.learning.errors import (
    MockExamNotFoundError,
    PhaseClosedError,
    PhaseIncompleteError,
)
from fordona_connect.learning.mock_exams import MockExamService
from fordona_connect.learning.progress.recorder import ProgressService
from fordona_connect.learning.progress.screens import LearnerProfile, ProgressScreens
from tests.learning_content.boost_world import BASE, LOCALES, BoostWorld, FakeLesson, FakeQuestion

pytestmark = pytest.mark.integration

LEARNER = "kp_lifecycle"
NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)


class Subscriptions:
    async def is_subscribed(self, learner_id: str) -> bool:
        return False


class Profiles:
    async def profile(self, learner_id: str) -> LearnerProfile:
        return LearnerProfile(first_name="ashen", last_name="priyankara")


def catalogue() -> BoostWorld:
    return BoostWorld(
        modules=["m1", "m2"],
        lessons=[FakeLesson("l1", "m1"), FakeLesson("l2", "m1"), FakeLesson("l3", "m2")],
        questions=[
            FakeQuestion("q1", "l1", "m1"),
            FakeQuestion("q2", "l1", "m1"),
            FakeQuestion("q3", "l1", "m1"),
            FakeQuestion("q4", "l2", "m1"),
            FakeQuestion("q5", "l3", "m2"),
        ],
        mock_exams=[{"id": "e1", "version": "1", "questionCount": 2, "questionIds": ["q4", "q1"]}],
    )


@pytest.fixture
async def sessions(learning_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    maker = async_sessionmaker(learning_engine, expire_on_commit=False)
    async with httpx.AsyncClient(base_url=BASE) as http:
        sync = ContentSyncService(
            maker,
            BoostClient(http, token="svc", grading_token="grading-token", max_retries=0),
            locales=LOCALES,
            default_locale="sv-SE",
            page_size=50,
        )
        with respx.mock(assert_all_called=False) as router:
            catalogue().mount(router)
            await sync.sync()
    return maker


def build(sessions: async_sessionmaker[AsyncSession]) -> tuple[AttemptService, ProgressScreens]:
    snapshots = SnapshotProvider(sessions, freshness_seconds=0)
    screens = ProgressScreens(sessions, snapshots, Subscriptions(), Profiles(), now=lambda: NOW)
    attempts = AttemptService(
        sessions,
        snapshots,
        Subscriptions(),
        progress=ProgressService(sessions, now=lambda: NOW),
        summaries=screens,
        now=lambda: NOW,
    )
    return attempts, screens


async def answer_all(
    attempts: AttemptService,
    attempt_id: str,
    *,
    wrong: set[str] = frozenset(),
    phase: str = "LESSON",
) -> None:
    attempt = await attempts.get(LEARNER, uuid.UUID(attempt_id))
    for item in attempt.items:
        if item.phase != phase or item.answered:
            continue
        await attempts.answer(
            LEARNER,
            uuid.UUID(attempt_id),
            seq=item.seq,
            selected_option_key="b" if item.question_id in wrong else "a",
            response_id=uuid.uuid4(),
            duration_ms=None,
            locale="sv-SE",
        )


async def test_a_perfect_lesson_completes_and_unlocks_the_next(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts, _ = build(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    await answer_all(attempts, attempt.attempt_id)

    result = await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone="Europe/Stockholm"
    )

    assert result.status == "COMPLETED"
    assert result.lesson_summary is not None
    assert (result.lesson_summary.total, result.lesson_summary.correct) == (3, 3)
    assert result.retry is None
    assert result.next is not None
    assert (result.next.lesson_id, result.next.action, result.next.display_index) == (
        "l2",
        "START",
        "1.2",
    )
    assert result.progress is not None
    assert result.progress.streak.current == 1
    assert result.progress.daily_challenge.progress == 1
    assert result.progress.readiness.percent == 33  # 1.0 of 3 lessons

    state = await attempts.lesson_state(LEARNER, "l2")
    assert state.status == "CURRENT"
    replay = await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
    )
    assert replay.status == "COMPLETED"
    assert replay.progress is not None
    assert replay.progress.streak.current == 1  # not counted twice


async def test_mistakes_open_a_retry_phase_that_completes_the_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts, _ = build(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    await answer_all(attempts, attempt.attempt_id, wrong={"q1"})

    with pytest.raises(PhaseClosedError):
        await attempts.complete_retry_phase(
            LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
        )
    lesson_done = await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
    )

    assert lesson_done.status == "IN_RETRY"
    assert lesson_done.retry is not None
    assert [item.question_id for item in lesson_done.retry.items] == ["q1"]
    assert lesson_done.retry.items[0].seq == 4
    assert lesson_done.next is None
    async with sessions() as session:
        sources = (
            await session.scalars(
                select(AttemptItem.item_source).where(AttemptItem.phase == "RETRY")
            )
        ).all()
    assert sources == ["REPEAT"]  # every neighbour is already in the attempt

    with pytest.raises(PhaseIncompleteError):
        await attempts.complete_retry_phase(
            LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
        )
    await answer_all(attempts, attempt.attempt_id, phase="RETRY")
    done = await attempts.complete_retry_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
    )

    assert done.status == "COMPLETED"
    assert done.retry_summary is not None
    assert (done.retry_summary.total, done.retry_summary.correct) == (1, 1)
    assert done.lesson_summary is not None
    assert done.lesson_summary.wrong == 1
    assert done.progress is not None
    # Readiness takes the lesson phase's 2/3, not the retry phase.
    assert done.progress.readiness.percent == 22


async def test_unfinished_lessons_cannot_be_completed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts, _ = build(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())

    with pytest.raises(PhaseIncompleteError):
        await attempts.complete_lesson_phase(
            LEARNER, uuid.UUID(attempt.attempt_id), locale="sv-SE", timezone=None
        )


async def test_screens_follow_progress(sessions: async_sessionmaker[AsyncSession]) -> None:
    attempts, screens = build(sessions)

    fresh = await screens.home(LEARNER, locale="en-GB", timezone="Europe/Stockholm")
    assert fresh.user.initials == "AP"
    assert fresh.continue_ is not None
    assert (fresh.continue_.lesson_id, fresh.continue_.action) == ("l1", "START")
    assert [u.lesson_id for u in fresh.up_next] == ["l2"]
    assert fresh.tabs.mock_exams.locked is False
    assert fresh.week is not None
    assert len(fresh.week.days) == 7

    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    in_progress = await screens.home(LEARNER, locale="en-GB", timezone=None)
    assert in_progress.continue_ is not None
    assert in_progress.continue_.action == "CONTINUE"
    assert in_progress.continue_.open_attempt is not None
    assert in_progress.learning_path_etag != fresh.learning_path_etag

    await answer_all(attempts, attempt.attempt_id)
    await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="en-GB", timezone=None
    )

    path = await screens.learning_path(LEARNER, locale="en-GB")
    entries = {e.lesson_id: e for unit in path.units for e in unit.entries}
    assert entries["l1"].status == "COMPLETED"
    assert entries["l1"].last_result is not None
    assert (entries["l1"].last_result.correct, entries["l1"].last_result.total) == (3, 3)
    assert entries["l1"].open_attempt is None
    assert entries["l2"].status == "CURRENT"
    assert entries["l1"].title == "l1 en-GB"
    assert [unit.locked for unit in path.units] == [False, True]
    assert path.units[1].lock_reason == "SUBSCRIPTION"
    assert path.units[0].progress.completed_lessons == 1

    readiness = await screens.readiness(LEARNER, locale="en-GB")
    assert (readiness.percent, readiness.completed_lessons, readiness.total_lessons) == (33, 1, 3)
    assert readiness.average_best_accuracy == 1.0
    assert await screens.learning_path_etag(LEARNER, locale="en-GB") == (
        (await screens.home(LEARNER, locale="en-GB", timezone=None)).learning_path_etag
    )


async def test_the_mock_exam_catalogue(sessions: async_sessionmaker[AsyncSession]) -> None:
    exams = MockExamService(sessions, SnapshotProvider(sessions, freshness_seconds=0))

    listed = await exams.list(locale="en-GB")
    detail = await exams.detail("e1", locale="en-GB")

    assert [(e.mock_exam_id, e.name, e.question_count) for e in listed] == [("e1", "e1 en-GB", 2)]
    assert [item.question_id for item in detail.items] == ["q4", "q1"]
    with pytest.raises(MockExamNotFoundError):
        await exams.detail("nope", locale="en-GB")
