"""A migrated Postgres for the learning-service integration tests (skips without Docker)."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fordona_connect.db.connection import ASYNCPG_CONNECT_ARGS, DB_SCHEMA

ROOT = Path(__file__).resolve().parents[2]

# Every container here is stopped by its own context manager, so testcontainers'
# Ryuk reaper adds nothing, and it intermittently fails to publish its port
# ("Port mapping ... 8080 is not available"), erroring whole test modules.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Learner and content state, emptied before each test that asks for ``learning_engine``.
_LEARNING_TABLES = (
    "content_release",
    "content_unit",
    "content_question",
    "content_mock_exam",
    "content_journey",
    "mistake",
    "lesson_progress",
    "learner_summary",
    "learner_activity_day",
    "learner_activity_lesson",
)


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
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
async def learning_engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database_url, connect_args=ASYNCPG_CONNECT_ARGS)
    tables = ", ".join(f"{DB_SCHEMA}.{table}" for table in _LEARNING_TABLES)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield engine
    await engine.dispose()
