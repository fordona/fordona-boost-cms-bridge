"""The public theory and learning-journey services on the local learning backend.

Real ``TheoryService`` and ``LearningJourneyService`` over Postgres (testcontainers;
skips without Docker), fake Boost (content sync and question bodies) and a fake
fordona-engine platform endpoint (learner context).
"""

import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis, FakeServer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.cache.attempt_refs import AttemptRefCache
from fordona_connect.cache.redis_cache import RedisCache
from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.core.context import learner_id_var, learner_token_var
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.backend import LocalTheoryBackend
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.content.sync import ContentSyncService
from fordona_connect.learning.mock_exams import MockExamService
from fordona_connect.learning.platform import PlatformClient
from fordona_connect.learning.progress.recorder import ProgressService
from fordona_connect.learning.progress.screens import ProgressScreens
from fordona_connect.learning_journey.boost_content import BoostJourneyContent
from fordona_connect.learning_journey.repository import LearningJourneyRepository
from fordona_connect.learning_journey.service import LearningJourneyService
from fordona_connect.services.body_cache import BodyCache
from fordona_connect.services.media import build_asset_url_resolver
from fordona_connect.services.theory_service import TheoryService
from tests.conftest import make_settings
from tests.learning_content.boost_world import BASE, LOCALES, BoostWorld, FakeLesson, FakeQuestion

pytestmark = pytest.mark.integration

ENGINE = "https://engine.test"
LEARNER = "kp_e2e"


def catalogue() -> BoostWorld:
    return BoostWorld(
        modules=["m1"],
        lessons=[FakeLesson("l1"), FakeLesson("l2")],
        questions=[FakeQuestion("q1", "l1"), FakeQuestion("q2", "l1"), FakeQuestion("q3", "l2")],
        journeys=[
            {
                "id": "j1",
                "version": "4",
                "title": "B Licence",
                "milestones": [
                    {
                        "id": "ms1",
                        "title": "Basics",
                        "challenges": [
                            {
                                "id": "c1",
                                "title": "Give way",
                                "goal": "Know who goes first",
                                "chapterIds": ["l1"],
                                "questionIds": ["q2", "q1"],
                            }
                        ],
                    },
                    {
                        "id": "ms2",
                        "title": "More",
                        "challenges": [
                            {
                                "id": "c2",
                                "title": "Next",
                                "chapterIds": ["l2"],
                                "questionIds": ["q3"],
                            }
                        ],
                    },
                ],
            }
        ],
    )


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        catalogue().mount(mock)
        mock.get(f"{ENGINE}/internal/learning/v1/learners/{LEARNER}").respond(
            json={
                "code": 200,
                "status": "OK",
                "response": {
                    "userId": 7,
                    "firstName": "Ashen",
                    "lastName": "Priyankara",
                    "subscribed": False,
                },
            }
        )
        yield mock


@pytest.fixture
async def services(
    learning_engine: AsyncEngine, router: respx.MockRouter
) -> AsyncIterator[tuple[TheoryService, LearningJourneyService]]:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        learning_engine, expire_on_commit=False
    )
    settings = make_settings(engine_base_url=ENGINE)
    async with (
        httpx.AsyncClient(base_url=BASE) as boost_http,
        httpx.AsyncClient(base_url=ENGINE) as engine_http,
    ):
        boost = BoostClient(boost_http, token="svc", grading_token="grading-token", max_retries=0)
        await ContentSyncService(
            sessions, boost, locales=LOCALES, default_locale="sv-SE", page_size=50
        ).sync()

        redis = FakeAsyncRedis(server=FakeServer())
        cache = RedisCache(redis, hard_ttl_seconds=3600, negative_ttl_seconds=30)
        bodies = BodyCache(boost, cache, batch_max_refs=50)
        platform = PlatformClient(
            EngineClient(engine_http, internal_token="internal-secret", default_timeout=2.0),
            redis,
        )
        snapshots = SnapshotProvider(sessions, freshness_seconds=0)
        screens = ProgressScreens(sessions, snapshots, platform, platform)
        attempts = AttemptService(
            sessions,
            snapshots,
            platform,
            progress=ProgressService(sessions),
            summaries=screens,
        )
        theory = TheoryService(
            LocalTheoryBackend(attempts, screens, MockExamService(sessions, snapshots)),
            bodies,
            AttemptRefCache(cache),
            build_asset_url_resolver(settings),
        )
        journeys = LearningJourneyService(
            LearningJourneyRepository(sessions),
            BoostJourneyContent(sessions, snapshots, bodies, locale="sv-SE"),
            platform,
        )
        learner = learner_id_var.set(LEARNER)
        token = learner_token_var.set("learner-jwt")
        try:
            yield theory, journeys
        finally:
            learner_id_var.reset(learner)
            learner_token_var.reset(token)


async def test_a_lesson_from_home_to_completion(
    services: tuple[TheoryService, LearningJourneyService],
) -> None:
    theory, _ = services

    home = await theory.home(locale="sv-SE", timezone="Europe/Stockholm")
    lesson = await theory.lesson_detail("l1", locale="sv-SE")
    attempt = await theory.start_attempt("l1", request_id=uuid.uuid4(), locale="sv-SE")

    assert home.model_dump(by_alias=True)["user"]["firstName"] == "Ashen"
    assert lesson.model_dump(by_alias=True)["questionCount"] == 2
    dumped = attempt.model_dump(by_alias=True)
    assert len(dumped["items"]) == 2

    for item in dumped["items"]:
        options = item["options"]
        # Option "a" is correct in the fake catalogue; its text block says so.
        correct = next(option for option in options if "option a" in str(option["content"]))
        feedback = await theory.answer(
            uuid.UUID(dumped["attemptId"]),
            response_id=uuid.uuid4(),
            seq=item["seq"],
            selected_option_key=correct["key"],
            duration_ms=900,
            locale="sv-SE",
        )
        assert feedback.model_dump(by_alias=True)["isCorrect"] is True

    done = (
        await theory.complete_lesson_phase(
            uuid.UUID(dumped["attemptId"]), locale="sv-SE", timezone="Europe/Stockholm"
        )
    ).model_dump(by_alias=True)
    assert done["status"] == "COMPLETED"
    assert done["next"]["lessonId"] == "l2"

    path, etag, not_modified = await theory.learning_path(locale="sv-SE", if_none_match=None)
    assert path is not None
    assert not_modified is False
    entries = path.model_dump(by_alias=True)["units"][0]["entries"]
    assert [entry["status"] for entry in entries] == ["COMPLETED", "CURRENT"]
    _, _, unchanged = await theory.learning_path(locale="sv-SE", if_none_match=etag)
    assert unchanged is True


async def test_the_learning_journey_comes_from_boost(
    services: tuple[TheoryService, LearningJourneyService],
) -> None:
    _, journeys = services

    journey = await journeys.get_learning_journey(LEARNER)
    detail = await journeys.get_challenge_detail(LEARNER, "c1")

    assert (journey.journey_id, journey.title, journey.version) == ("j1", "B Licence", 4)
    assert [m.milestone_id for m in journey.milestones] == ["ms1", "ms2"]
    assert journey.milestones[1].access.reason == "SUBSCRIPTION_REQUIRED"
    assert journey.stats.question_count == 3
    assert detail.display_code == "1.1"
    assert detail.description == "Know who goes first"
    assert [q.question_id for q in detail.questions] == ["q2", "q1"]
    assert detail.questions[0].question_text == "q2? (sv-SE)"
    assert [o.text for o in detail.questions[0].options] == ["option a", "option b", "option c"]
    assert detail.is_content_ready is True
