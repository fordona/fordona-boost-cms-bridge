"""Sharing fordona-engine's database (testcontainers; skips without Docker).

The database starts with an engine-owned table in ``public``. Migrations run from a
driverless ``postgresql://`` URL — the form the engine's ``DB_*`` values and hosting
panels give — and must put every fordona-connect object, Alembic's version table included, in
the ``fordona_connect`` schema while leaving ``public`` exactly as the engine left it.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fordona_connect.db.connection import ASYNCPG_CONNECT_ARGS, DB_SCHEMA
from fordona_connect.learning_journey.models import LearningJourneyUserAssignment

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

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


@pytest.fixture(scope="module")
def asyncpg_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        url = container.get_connection_url()
        yield url


@pytest.fixture(scope="module")
def migrated_url(asyncpg_url: str) -> str:
    import asyncio

    async def _seed_engine_table() -> None:
        engine = create_async_engine(asyncpg_url)
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE public.content_question (question_id TEXT PRIMARY KEY)")
            )
            await connection.execute(text("INSERT INTO public.content_question VALUES ('q1')"))
        await engine.dispose()

    asyncio.run(_seed_engine_table())
    driverless = make_url(asyncpg_url).set(drivername="postgresql")
    _migrate(driverless.render_as_string(hide_password=False))
    return asyncpg_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url, connect_args=ASYNCPG_CONNECT_ARGS)
    yield engine
    await engine.dispose()


async def _tables(engine: AsyncEngine, schema: str) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
            {"schema": schema},
        )
        return {row[0] for row in rows}


async def test_migrations_leave_public_schema_untouched(engine: AsyncEngine) -> None:
    assert await _tables(engine, "public") == {"content_question"}
    async with engine.connect() as connection:
        rows = await connection.execute(text("SELECT question_id FROM public.content_question"))
        assert [row[0] for row in rows] == ["q1"]


async def test_connect_tables_and_version_table_live_in_connect_learning_schema(
    engine: AsyncEngine,
) -> None:
    tables = await _tables(engine, DB_SCHEMA)
    assert "alembic_version" in tables
    assert "content_snapshot" in tables
    assert {t for t in tables if t.startswith("learning_journey_")} == {
        "learning_journey_user_assignments",
        "learning_journey_user_challenge_progress",
        "learning_journey_sessions",
        "learning_journey_attempts",
        "learning_journey_attempt_questions",
        "learning_journey_remediations",
        "learning_journey_idempotency_records",
    }


async def test_orm_queries_resolve_to_the_connect_learning_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = (await connection.execute(select(LearningJourneyUserAssignment.assignment_id))).all()
    assert rows == []


def test_rerunning_migrations_is_a_no_op(migrated_url: str) -> None:
    # Sync on purpose: Alembic's env.py calls asyncio.run(), which can't nest in a test loop.
    import asyncio

    async def _connect_tables() -> set[str]:
        engine = create_async_engine(migrated_url, connect_args=ASYNCPG_CONNECT_ARGS)
        try:
            return await _tables(engine, DB_SCHEMA)
        finally:
            await engine.dispose()

    before = asyncio.run(_connect_tables())
    driverless = make_url(migrated_url).set(drivername="postgresql")
    _migrate(driverless.render_as_string(hide_password=False))
    assert asyncio.run(_connect_tables()) == before


async def test_repeated_queries_work_without_statement_cache(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        for _ in range(5):
            assert (
                await connection.execute(select(LearningJourneyUserAssignment.assignment_id))
            ).all() == []
