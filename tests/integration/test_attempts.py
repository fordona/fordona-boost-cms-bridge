"""Lesson attempts against Postgres (testcontainers; skips without Docker).

Content is seeded through the real content sync from a fake Boost catalogue.
"""

import asyncio
import uuid
from collections.abc import Sequence

import httpx
import pytest
import respx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.learning.attempts.models import AttemptItem, LessonAttempt, Mistake
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.content.sync import ContentSyncService
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
from fordona_connect.learning.selection import Strategy
from tests.learning_content.boost_world import BASE, LOCALES, BoostWorld, FakeLesson, FakeQuestion

pytestmark = pytest.mark.integration

LEARNER = "kp_learner_1"
OTHER = "kp_learner_2"


class Subscriptions:
    def __init__(self, subscribed: set[str] | None = None) -> None:
        self.subscribed = subscribed or set()

    async def is_subscribed(self, learner_id: str) -> bool:
        return learner_id in self.subscribed


def reverse(option_keys: Sequence[str]) -> list[str]:
    """A deterministic 'shuffle', so labels are predictable."""
    return list(reversed(option_keys))


def catalogue() -> BoostWorld:
    return BoostWorld(
        modules=["m1", "m2"],
        lessons=[FakeLesson("l1", "m1"), FakeLesson("l2", "m1"), FakeLesson("l3", "m2")],
        questions=[
            FakeQuestion("q1", "l1", "m1"),
            FakeQuestion("q2", "l1", "m1", correct="b"),
            FakeQuestion("q3", "l2", "m1"),
            FakeQuestion("q4", "l3", "m2"),
        ],
        journeys=[
            {
                "id": "j1",
                "title": "B",
                "milestones": [
                    {
                        "id": "ms1",
                        "title": "One",
                        "challenges": [
                            {"id": "c1", "chapterIds": ["l1"], "questionIds": ["q2", "q1"]}
                        ],
                    }
                ],
            }
        ],
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


def service(
    sessions: async_sessionmaker[AsyncSession],
    *,
    subscribed: set[str] | None = None,
    strategy: Strategy = Strategy.LESSON_BANK,
) -> AttemptService:
    return AttemptService(
        sessions,
        SnapshotProvider(sessions, freshness_seconds=0),
        Subscriptions(subscribed),
        strategy=strategy,
        shuffle=reverse,
    )


async def complete(sessions: async_sessionmaker[AsyncSession], attempt_id: str) -> None:
    """Mark an attempt completed (phase completion itself arrives in L3)."""
    async with sessions() as session, session.begin():
        await session.execute(
            update(LessonAttempt)
            .where(LessonAttempt.attempt_id == uuid.UUID(attempt_id))
            .values(status="COMPLETED")
        )


# --- start --------------------------------------------------------------------


async def test_start_serves_the_lesson_bank_with_shuffled_options(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await service(sessions).start(LEARNER, "l1", uuid.uuid4())

    assert attempt.status == "IN_LESSON"
    assert attempt.attempt_no == 1
    assert [(item.seq, item.question_id) for item in attempt.items] == [(1, "q1"), (2, "q2")]
    assert attempt.items[0].option_order == ["c", "b", "a"]
    assert all(item.answered is False for item in attempt.items)


async def test_the_same_request_id_returns_the_same_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    request_id = uuid.uuid4()

    first = await attempts.start(LEARNER, "l1", request_id)
    second = await attempts.start(LEARNER, "l1", request_id)

    assert second.attempt_id == first.attempt_id


async def test_a_request_id_reused_for_another_lesson_conflicts(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    request_id = uuid.uuid4()
    await attempts.start(LEARNER, "l1", request_id)

    with pytest.raises(RequestIdConflictError):
        await attempts.start(LEARNER, "l2", request_id)


async def test_a_second_start_resumes_the_open_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    first = await attempts.start(LEARNER, "l1", uuid.uuid4())
    second = await attempts.start(LEARNER, "l1", uuid.uuid4())

    assert second.attempt_id == first.attempt_id


async def test_concurrent_starts_create_one_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)

    results = await asyncio.gather(*(attempts.start(LEARNER, "l1", uuid.uuid4()) for _ in range(5)))

    assert len({result.attempt_id for result in results}) == 1
    async with sessions() as session:
        rows = (await session.scalars(select(LessonAttempt))).all()
    assert len(rows) == 1


async def test_the_next_lesson_is_locked_until_the_previous_is_completed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    with pytest.raises(TheoryLessonLockedError):
        await attempts.start(LEARNER, "l2", uuid.uuid4())

    first = await attempts.start(LEARNER, "l1", uuid.uuid4())
    await complete(sessions, first.attempt_id)
    second = await attempts.start(LEARNER, "l2", uuid.uuid4())

    assert second.items[0].question_id == "q3"


async def test_a_paid_unit_needs_a_subscription(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    for lesson in ("l1", "l2"):
        attempt = await service(sessions).start(LEARNER, lesson, uuid.uuid4())
        await complete(sessions, attempt.attempt_id)

    with pytest.raises(TheoryModuleLockedError):
        await service(sessions).start(LEARNER, "l3", uuid.uuid4())
    paid = await service(sessions, subscribed={LEARNER}).start(LEARNER, "l3", uuid.uuid4())
    assert paid.items[0].question_id == "q4"


async def test_an_unknown_lesson_is_not_found(sessions: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(LessonNotFoundError):
        await service(sessions).start(LEARNER, "nope", uuid.uuid4())


async def test_the_challenge_strategy_serves_the_challenge_quiz(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempt = await service(sessions, strategy=Strategy.CHALLENGE).start(
        LEARNER, "l1", uuid.uuid4()
    )

    assert [item.question_id for item in attempt.items] == ["q2", "q1"]
    async with sessions() as session:
        stored = await session.get(LessonAttempt, uuid.UUID(attempt.attempt_id))
        sources = (await session.scalars(select(AttemptItem.item_source))).all()
    assert stored is not None
    assert stored.challenge_id == "c1"
    assert set(sources) == {"CHALLENGE"}


# --- read ---------------------------------------------------------------------


async def test_an_attempt_is_visible_only_to_its_learner(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())

    assert (await attempts.get(LEARNER, uuid.UUID(attempt.attempt_id))).attempt_id == (
        attempt.attempt_id
    )
    with pytest.raises(AttemptNotFoundError):
        await attempts.get(OTHER, uuid.UUID(attempt.attempt_id))


async def test_lesson_state_previews_and_reports_locks(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)

    current = await attempts.lesson_state(LEARNER, "l1")
    locked = await attempts.lesson_state(LEARNER, "l2")

    assert (current.status, current.locked, current.question_count) == ("CURRENT", False, 2)
    assert current.open_attempt is None
    assert current.estimated_minutes == 5  # Boost's reading time wins over the estimate
    assert (locked.status, locked.lock_reason, locked.question_count) == (
        "LOCKED",
        "THEORY_LESSON_LOCKED",
        0,
    )

    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    resumed = await attempts.lesson_state(LEARNER, "l1")
    assert resumed.open_attempt is not None
    assert resumed.open_attempt.attempt_id == attempt.attempt_id
    assert resumed.open_attempt.phase == "IN_LESSON"


async def test_a_paid_unit_reports_the_module_lock(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    for lesson in ("l1", "l2"):
        attempt = await service(sessions).start(LEARNER, lesson, uuid.uuid4())
        await complete(sessions, attempt.attempt_id)

    state = await service(sessions).lesson_state(LEARNER, "l3")

    assert state.lock_reason == "THEORY_ATTEMPT_MODULE_LOCKED"


# --- answer -------------------------------------------------------------------


async def answer(
    attempts: AttemptService,
    attempt_id: str,
    seq: int,
    key: str,
    *,
    response_id: uuid.UUID | None = None,
    locale: str = "en-GB",
):  # type: ignore[no-untyped-def]
    return await attempts.answer(
        LEARNER,
        uuid.UUID(attempt_id),
        seq=seq,
        selected_option_key=key,
        response_id=response_id or uuid.uuid4(),
        duration_ms=1200,
        locale=locale,
    )


async def test_answers_are_graded_with_the_label_shown_to_the_learner(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())

    right = await answer(attempts, attempt.attempt_id, 1, "a")
    wrong = await answer(attempts, attempt.attempt_id, 2, "a", locale="sv-SE")

    # Options were shown reversed (c, b, a): the correct "a" is label C.
    assert (right.is_correct, right.correct_option_key, right.correct_option_label) == (
        True,
        "a",
        "C",
    )
    assert right.explanation == "why (en-GB)"
    assert (wrong.is_correct, wrong.correct_option_key, wrong.correct_option_label) == (
        False,
        "b",
        "B",
    )
    assert wrong.explanation == "why (sv-SE)"
    reread = await attempts.get(LEARNER, uuid.UUID(attempt.attempt_id))
    assert [item.answered for item in reread.items] == [True, True]


async def test_a_replayed_answer_returns_the_same_feedback(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    response_id = uuid.uuid4()

    first = await answer(attempts, attempt.attempt_id, 1, "b", response_id=response_id)
    replay = await answer(attempts, attempt.attempt_id, 1, "b", response_id=response_id)

    assert replay == first
    async with sessions() as session:
        mistake = await session.get(Mistake, (LEARNER, "q1"))
    assert mistake is not None
    assert mistake.times_wrong == 1  # the replay did not count twice


async def test_answering_again_differently_conflicts(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    await answer(attempts, attempt.attempt_id, 1, "a")

    with pytest.raises(ResponseConflictError):
        await answer(attempts, attempt.attempt_id, 1, "b")


async def test_a_response_id_cannot_answer_two_items(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())
    response_id = uuid.uuid4()
    await answer(attempts, attempt.attempt_id, 1, "a", response_id=response_id)

    with pytest.raises(ResponseConflictError):
        await answer(attempts, attempt.attempt_id, 2, "b", response_id=response_id)
    # The failed answer left item 2 untouched.
    reread = await attempts.get(LEARNER, uuid.UUID(attempt.attempt_id))
    assert reread.items[1].answered is False


async def test_invalid_answers_are_refused(sessions: async_sessionmaker[AsyncSession]) -> None:
    attempts = service(sessions)
    attempt = await attempts.start(LEARNER, "l1", uuid.uuid4())

    with pytest.raises(OptionInvalidError):
        await answer(attempts, attempt.attempt_id, 1, "z")
    with pytest.raises(ItemNotFoundError):
        await answer(attempts, attempt.attempt_id, 9, "a")
    with pytest.raises(AttemptNotFoundError):
        await attempts.answer(
            OTHER,
            uuid.UUID(attempt.attempt_id),
            seq=1,
            selected_option_key="a",
            response_id=uuid.uuid4(),
            duration_ms=None,
            locale="sv-SE",
        )
    await complete(sessions, attempt.attempt_id)
    with pytest.raises(PhaseClosedError):
        await answer(attempts, attempt.attempt_id, 1, "a")


async def test_a_mistake_is_recorded_then_resolved_by_a_retake(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = service(sessions)
    first = await attempts.start(LEARNER, "l1", uuid.uuid4())
    await answer(attempts, first.attempt_id, 1, "c")
    await complete(sessions, first.attempt_id)

    retake = await attempts.start(LEARNER, "l1", uuid.uuid4())
    assert retake.attempt_no == 2
    await answer(attempts, retake.attempt_id, 1, "a")

    async with sessions() as session:
        mistake = await session.get(Mistake, (LEARNER, "q1"))
    assert mistake is not None
    assert (mistake.status, mistake.resolved_via, mistake.home_lesson_id) == (
        "RESOLVED",
        "RETAKE",
        "l1",
    )
