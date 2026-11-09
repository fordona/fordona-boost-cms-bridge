"""fordona-connect's learning pipeline over the real Boost dev catalogue (captured fixture).

Syncs every published module, chapter and question plus learning journey 3, then takes
a lesson and a journey challenge end to end. Postgres via testcontainers (skips without
Docker); Boost and the engine are faked with respx.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis, FakeServer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.cache.redis_cache import RedisCache
from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentLesson,
    ContentQuestion,
    ContentQuestionRevision,
)
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.content.sync import ContentSyncService
from fordona_connect.learning.progress.recorder import ProgressService
from fordona_connect.learning.retry.models import QuestionNeighbour
from fordona_connect.learning_journey.boost_content import BoostJourneyContent
from fordona_connect.learning_journey.repository import LearningJourneyRepository
from fordona_connect.learning_journey.service import LearningJourneyService
from fordona_connect.services.body_cache import BodyCache
from tests.learning_content.boost_dev import BASE, BoostDev

pytestmark = pytest.mark.integration

LEARNER = "kp_boost_dev"


class Subscribed:
    async def is_subscribed(self, learner_id: str) -> bool:
        return True


@pytest.fixture
async def world(
    learning_engine: AsyncEngine,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], BoostDev, BoostClient]]:
    sessions = async_sessionmaker(learning_engine, expire_on_commit=False)
    boost = BoostDev()
    async with httpx.AsyncClient(base_url=BASE) as http:
        client = BoostClient(http, token="svc", grading_token="grading", max_retries=0)
        with respx.mock(assert_all_called=False) as router:
            boost.mount(router)
            await ContentSyncService(
                sessions, client, locales=("sv-SE", "en-GB"), default_locale="sv-SE", page_size=5
            ).sync()
            yield sessions, boost, client


async def count(sessions: async_sessionmaker[AsyncSession], statement) -> int:  # type: ignore[no-untyped-def]
    async with sessions() as session:
        return int(await session.scalar(statement) or 0)


async def test_the_whole_catalogue_syncs_and_is_deliverable(world) -> None:  # type: ignore[no-untyped-def]
    sessions, boost, _ = world

    assert boost.grading_calls == 18
    assert await count(sessions, select(func.count()).where(ContentLesson.status == "VISIBLE")) == 6
    assert (
        await count(sessions, select(func.count()).where(ContentQuestion.status == "ACTIVE")) == 18
    )
    assert await count(sessions, select(func.count()).select_from(ContentQuestionRevision)) == 18
    assert await count(sessions, select(func.count()).select_from(ContentChallenge)) == 6
    assert await count(sessions, select(func.count()).select_from(QuestionNeighbour)) > 0


async def test_a_lesson_with_its_real_answer_keys(world) -> None:  # type: ignore[no-untyped-def]
    sessions, boost, _ = world
    attempts = AttemptService(
        sessions,
        SnapshotProvider(sessions, freshness_seconds=0),
        Subscribed(),
        progress=ProgressService(sessions),
    )

    attempt = await attempts.start(LEARNER, "1", uuid.uuid4())
    assert [item.question_id for item in attempt.items] == ["1", "2", "3"]

    for item in attempt.items:
        correct = boost.question(item.question_id)["correctOptionId"]
        # Answer question 3 wrong, the rest right.
        chosen = "a" if item.question_id == "3" else correct
        feedback = await attempts.answer(
            LEARNER,
            uuid.UUID(attempt.attempt_id),
            seq=item.seq,
            selected_option_key=chosen,
            response_id=uuid.uuid4(),
            duration_ms=1000,
            locale="en-GB",
        )
        assert feedback.is_correct is (chosen == correct)
        assert feedback.correct_option_key == correct

    lesson_done = await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="en-GB", timezone="Europe/Stockholm"
    )
    assert lesson_done.status == "IN_RETRY"
    assert lesson_done.retry is not None
    retried = [item.question_id for item in lesson_done.retry.items]
    # The wrong question comes back, plus similar ones from the same lesson (q1, q2 are
    # already in the attempt, so the neighbours that qualify are limited).
    assert "3" in retried


async def test_journey_3_comes_from_boost_dev(world) -> None:  # type: ignore[no-untyped-def]
    sessions, _, client = world
    redis = FakeAsyncRedis(server=FakeServer())
    bodies = BodyCache(
        client, RedisCache(redis, hard_ttl_seconds=3600, negative_ttl_seconds=30), batch_max_refs=50
    )
    snapshots = SnapshotProvider(sessions, freshness_seconds=0)
    journeys = LearningJourneyService(
        LearningJourneyRepository(sessions),
        BoostJourneyContent(sessions, snapshots, bodies, locale="en-GB"),
        Subscribed(),
    )

    journey = await journeys.get_learning_journey(LEARNER)
    challenge = await journeys.get_challenge_detail(LEARNER, "4")

    assert (journey.journey_id, journey.title, journey.version) == (
        "3",
        "Test journey: fordona-connect",
        2,
    )
    assert [m.title for m in journey.milestones] == [
        "Right of way",
        "Speed and distance",
        "The driver",
    ]
    assert journey.stats.question_count == 18
    assert challenge.display_code == "1.1"
    assert challenge.is_content_ready is True
    assert [q.question_id for q in challenge.questions] == ["1", "2", "3"]
    assert challenge.questions[1].question_type == "TRUE_FALSE"
    assert [o.text for o in challenge.questions[1].options] == ["True", "False"]
    assert challenge.questions[0].connected_chapters == ["The priority-to-the-right rule"]
