"""The content sync against Postgres (testcontainers; skips without Docker) and fake Boost."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.db.connection import ASYNCPG_CONNECT_ARGS, DB_SCHEMA
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentChallengeQuestion,
    ContentJourney,
    ContentLesson,
    ContentMockExam,
    ContentMockExamQuestion,
    ContentQuestion,
    ContentQuestionRevision,
    ContentRelease,
)
from fordona_connect.learning.content.sync import SYNC_LOCK_KEY, ContentSyncService
from tests.learning_content.boost_world import BASE, LOCALES, BoostWorld, FakeLesson, FakeQuestion

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    from alembic import command
    from alembic.config import Config
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        url = container.get_connection_url()
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            command.upgrade(config, "head")
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, connect_args=ASYNCPG_CONNECT_ARGS)
    async with engine.begin() as connection:
        # Each test starts from an empty content read model.
        await connection.execute(
            text(
                f"TRUNCATE {DB_SCHEMA}.content_release, {DB_SCHEMA}.content_unit, "
                f"{DB_SCHEMA}.content_mock_exam, {DB_SCHEMA}.content_journey CASCADE"
            )
        )
        await connection.execute(text(f"TRUNCATE {DB_SCHEMA}.content_question CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def boost_http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE) as http:
        yield http


def service(engine: AsyncEngine, http: httpx.AsyncClient) -> ContentSyncService:
    client = BoostClient(http, token="svc-token", grading_token="grading-token", max_retries=0)
    return ContentSyncService(
        async_sessionmaker(engine, expire_on_commit=False),
        client,
        locales=LOCALES,
        default_locale="sv-SE",
        page_size=50,
    )


def world() -> BoostWorld:
    return BoostWorld(
        modules=["m1"],
        lessons=[FakeLesson("l1"), FakeLesson("l2")],
        questions=[
            FakeQuestion("q1", "l1"),
            FakeQuestion("q2", "l2"),
            FakeQuestion("q3", "l2", locales=("sv-SE",)),
        ],
        mock_exams=[{"id": "e1", "version": "1", "questionCount": 2, "questionIds": ["q1", "q2"]}],
        journeys=[
            {
                "id": "j1",
                "title": "B",
                "milestones": [
                    {
                        "id": "ms1",
                        "title": "One",
                        "challenges": [
                            {"id": "c1", "title": "C", "chapterIds": ["l1"], "questionIds": ["q1"]}
                        ],
                    }
                ],
            }
        ],
    )


async def run(sync: ContentSyncService, boost: BoostWorld):  # type: ignore[no-untyped-def]
    with respx.mock(assert_all_called=False) as router:
        boost.mount(router)
        return await sync.sync()


async def count(engine: AsyncEngine, table: type) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(select(func.count()).select_from(table)) or 0)


async def test_first_sync_writes_everything_once(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    boost = world()
    result = await run(service(engine, boost_http), boost)

    assert result is not None
    assert result.changed is True
    assert result.new_revisions == 2  # q3 is excluded (no en-GB), so no revision
    assert sorted(boost.grading_calls) == ["q1@1", "q2@1", "q3@1"]
    assert await count(engine, ContentQuestion) == 3
    assert await count(engine, ContentQuestionRevision) == 2
    assert await count(engine, ContentMockExamQuestion) == 2
    assert await count(engine, ContentChallengeQuestion) == 1
    async with engine.connect() as connection:
        key = await connection.scalar(
            select(ContentQuestionRevision.correct_option_key).where(
                ContentQuestionRevision.question_id == "q1"
            )
        )
    assert key == "a"


async def test_an_unchanged_catalogue_writes_nothing_and_fetches_no_answers(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    sync = service(engine, boost_http)
    first = await run(sync, world())
    boost = world()
    second = await run(sync, boost)

    assert first is not None
    assert second is not None
    assert second.changed is False
    assert second.release_id == first.release_id
    # Stored revisions are never fetched again; the excluded q3 is remembered too.
    assert boost.grading_calls == []
    assert await count(engine, ContentRelease) == 1


async def test_a_new_version_fetches_only_that_revision_and_keeps_the_old_one(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    sync = service(engine, boost_http)
    await run(sync, world())
    boost = world()
    boost.questions[0].version = "2"
    boost.questions[0].correct = "c"

    result = await run(sync, boost)

    assert result is not None
    assert result.changed is True
    assert boost.grading_calls == ["q1@2"]
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(ContentQuestionRevision.version, ContentQuestionRevision.correct_option_key)
                .where(ContentQuestionRevision.question_id == "q1")
                .order_by(ContentQuestionRevision.version)
            )
        ).all()
        current = await connection.scalar(
            select(ContentQuestion.current_version).where(ContentQuestion.question_id == "q1")
        )
    assert [tuple(row) for row in rows] == [("1", "a"), ("2", "c")]
    assert current == "2"


async def test_content_removed_from_boost_is_hidden_excluded_or_deleted(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    sync = service(engine, boost_http)
    await run(sync, world())
    boost = world()
    boost.lessons = [FakeLesson("l1")]
    boost.questions = [FakeQuestion("q1", "l1")]
    boost.mock_exams = []
    boost.journeys = []

    result = await run(sync, boost)

    assert result is not None
    assert result.changed is True
    async with engine.connect() as connection:
        lesson_status = dict(
            (await connection.execute(select(ContentLesson.lesson_id, ContentLesson.status))).all()
        )
        questions = {
            row.question_id: (row.status, row.exclusion_reason)
            for row in await connection.execute(select(ContentQuestion))
        }
    assert lesson_status == {"l1": "VISIBLE", "l2": "HIDDEN"}
    assert questions == {
        "q1": ("ACTIVE", None),
        "q2": ("EXCLUDED", "REMOVED"),
        "q3": ("EXCLUDED", "REMOVED"),
    }
    # Revisions stay: attempts may refer to them.
    assert await count(engine, ContentQuestionRevision) == 2
    for table in (ContentMockExam, ContentJourney, ContentChallenge, ContentMockExamQuestion):
        assert await count(engine, table) == 0


async def test_only_one_instance_writes_at_a_time(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    async with engine.connect() as holder:
        await holder.execute(text("BEGIN"))
        await holder.execute(select(func.pg_advisory_xact_lock(SYNC_LOCK_KEY)))

        result = await run(service(engine, boost_http), world())

        await holder.execute(text("ROLLBACK"))

    assert result is None
    assert await count(engine, ContentQuestion) == 0


async def test_concurrent_instances_store_each_revision_once(
    engine: AsyncEngine, boost_http: httpx.AsyncClient
) -> None:
    with respx.mock(assert_all_called=False) as router:
        world().mount(router)
        results = await asyncio.gather(
            service(engine, boost_http).sync(), service(engine, boost_http).sync()
        )

    assert any(result is not None for result in results)
    assert await count(engine, ContentQuestionRevision) == 2
