"""The learning pipeline against the **live** Boost dev API (opt-in).

Runs only with ``BOOST_LIVE=1`` and Boost dev credentials in ``.env``
(``BOOST_BASE_URL``, ``BOOST_DELIVERY_TOKEN``, ``BOOST_GRADING_TOKEN``). It syncs the
real catalogue into a throwaway Postgres, checks that the captured fixture
(``tests/fixtures/boost_dev_catalogue.json``) still matches Boost dev, and grades a
lesson with the answer keys fetched from the grading API.

    BOOST_LIVE=1 uv run pytest -m integration tests/integration/test_boost_dev_live.py
"""

import os
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.clients.boost.client import BoostClient, create_http_client
from fordona_connect.core.config import BoostAuthMode, Settings
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentJourney,
    ContentLesson,
    ContentMilestone,
    ContentQuestion,
    ContentQuestionRevision,
)
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.content.sync import ContentSyncService
from fordona_connect.learning.progress.recorder import ProgressService
from tests.learning_content.boost_dev import load

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("BOOST_LIVE") != "1", reason="set BOOST_LIVE=1"),
]

LEARNER = "kp_boost_dev_live"
JOURNEY = "3"


class Subscribed:
    async def is_subscribed(self, learner_id: str) -> bool:
        return True


@pytest.fixture
async def synced(learning_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    settings = Settings()
    if settings.boost_auth_mode is not BoostAuthMode.SERVICE_TOKEN or not (
        settings.boost_grading_token.get_secret_value()
    ):
        pytest.skip("Boost dev service and grading tokens are not configured")
    sessions = async_sessionmaker(learning_engine, expire_on_commit=False)
    async with create_http_client(settings, read_timeout=30.0) as http:
        client = BoostClient.from_settings(http, settings)
        await ContentSyncService(
            sessions,
            client,
            locales=("sv-SE", "en-GB"),
            default_locale="sv-SE",
            page_size=settings.content_page_size,
        ).sync()
    return sessions


async def scalar(sessions: async_sessionmaker[AsyncSession], statement):  # type: ignore[no-untyped-def]
    async with sessions() as session:
        return await session.scalar(statement)


async def test_every_active_question_has_its_answer_key(synced) -> None:  # type: ignore[no-untyped-def]
    active = await scalar(synced, select(func.count()).where(ContentQuestion.status == "ACTIVE"))
    keyed = await scalar(
        synced,
        select(func.count(func.distinct(ContentQuestionRevision.question_id))).where(
            ContentQuestionRevision.question_id.in_(
                select(ContentQuestion.question_id).where(ContentQuestion.status == "ACTIVE")
            )
        ),
    )
    assert active > 0
    assert keyed == active


async def test_the_fixture_matches_boost_dev(synced) -> None:  # type: ignore[no-untyped-def]
    fixture = load()
    async with synced() as session:
        lessons = set(
            await session.scalars(
                select(ContentLesson.lesson_id).where(ContentLesson.status == "VISIBLE")
            )
        )
        keys = dict(
            (
                await session.execute(
                    select(
                        ContentQuestionRevision.question_id,
                        ContentQuestionRevision.correct_option_key,
                    )
                )
            ).all()
        )

    assert {chapter["id"] for chapter in fixture["chapters"]} <= lessons
    for question in fixture["questions"]:
        assert keys.get(question["id"]) == question["correctOptionId"], question["id"]


async def test_journey_3_is_synced_with_its_milestones_and_challenges(synced) -> None:  # type: ignore[no-untyped-def]
    fixture_journey = next(j for j in load()["journeys"] if str(j["id"]) == JOURNEY)
    async with synced() as session:
        journey = await session.get(ContentJourney, JOURNEY)
        milestones = (
            await session.scalars(
                select(ContentMilestone)
                .where(ContentMilestone.journey_id == JOURNEY)
                .order_by(ContentMilestone.sort)
            )
        ).all()
        challenges = (
            await session.scalars(
                select(ContentChallenge.challenge_id).where(
                    ContentChallenge.milestone_id.in_([m.milestone_id for m in milestones])
                )
            )
        ).all()

    assert journey is not None
    assert len(milestones) == len(fixture_journey["milestones"])
    assert sorted(challenges, key=int) == sorted(
        (str(c["id"]) for m in fixture_journey["milestones"] for c in m["challenges"]), key=int
    )


async def test_a_lesson_is_graded_with_the_live_answer_keys(synced) -> None:  # type: ignore[no-untyped-def]
    lesson_id = load()["chapters"][0]["id"]
    attempts = AttemptService(
        synced,
        SnapshotProvider(synced, freshness_seconds=0),
        Subscribed(),
        progress=ProgressService(synced),
    )
    attempt = await attempts.start(LEARNER, lesson_id, uuid.uuid4())
    assert attempt.items

    async with synced() as session:
        keys = dict(
            (
                await session.execute(
                    select(
                        ContentQuestionRevision.question_id,
                        ContentQuestionRevision.correct_option_key,
                    )
                )
            ).all()
        )
    for item in attempt.items:
        feedback = await attempts.answer(
            LEARNER,
            uuid.UUID(attempt.attempt_id),
            seq=item.seq,
            selected_option_key=keys[item.question_id],
            response_id=uuid.uuid4(),
            duration_ms=1000,
            locale="en-GB",
        )
        assert feedback.is_correct is True

    done = await attempts.complete_lesson_phase(
        LEARNER, uuid.UUID(attempt.attempt_id), locale="en-GB", timezone="Europe/Stockholm"
    )
    assert done.status == "COMPLETED"
