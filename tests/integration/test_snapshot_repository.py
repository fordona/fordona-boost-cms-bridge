"""SnapshotRepository against a real Postgres (testcontainers).

These tests need a running Docker daemon and skip themselves otherwise, so the
default suite stays runnable on a laptop without Docker. The migration is
applied through Alembic, which also checks that the migration and the ORM
model agree.
"""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from boost_bridge.db.session import create_sessionmaker, ping
from boost_bridge.db.snapshot_repository import SnapshotRepository, content_hash

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
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        url = container.get_connection_url()
        _migrate(url)
        yield url


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


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def repository(engine: AsyncEngine) -> SnapshotRepository:
    return SnapshotRepository(create_sessionmaker(engine))


async def test_ping(engine: AsyncEngine) -> None:
    await ping(engine)


async def test_upsert_then_get_round_trips(repository: SnapshotRepository) -> None:
    now = datetime.now(UTC)
    payload = {"id": "1", "translation": {"title": "Trafikregler åäö"}}

    await repository.upsert(
        "k:roundtrip", resource="module", locale="sv-SE", payload=payload, fetched_at=now
    )
    snapshot = await repository.get("k:roundtrip")

    assert snapshot is not None
    assert snapshot.payload == payload
    assert snapshot.fetched_at == now


async def test_unchanged_content_does_not_rewrite(repository: SnapshotRepository) -> None:
    first = datetime.now(UTC)
    payload = {"id": "1"}
    await repository.upsert(
        "k:same", resource="module", locale="sv-SE", payload=payload, fetched_at=first
    )
    await repository.upsert(
        "k:same",
        resource="module",
        locale="sv-SE",
        payload=payload,
        fetched_at=first + timedelta(hours=1),
    )

    snapshot = await repository.get("k:same")
    assert snapshot is not None
    assert snapshot.fetched_at == first  # the no-op branch did not write


async def test_changed_content_is_replaced(repository: SnapshotRepository) -> None:
    first = datetime.now(UTC)
    await repository.upsert(
        "k:chg", resource="module", locale="sv-SE", payload={"v": 1}, fetched_at=first
    )
    later = first + timedelta(minutes=5)
    await repository.upsert(
        "k:chg", resource="module", locale="sv-SE", payload={"v": 2}, fetched_at=later
    )

    snapshot = await repository.get("k:chg")
    assert snapshot is not None
    assert snapshot.payload == {"v": 2}
    assert snapshot.fetched_at == later


async def test_delete_removes_row(repository: SnapshotRepository) -> None:
    await repository.upsert(
        "k:del", resource="module", locale="sv-SE", payload={}, fetched_at=datetime.now(UTC)
    )
    await repository.delete("k:del")
    assert await repository.get("k:del") is None


async def test_get_missing_returns_none(repository: SnapshotRepository) -> None:
    assert await repository.get("k:never") is None


def test_content_hash_is_key_order_independent() -> None:
    assert content_hash({"a": 1, "b": [1, 2]}) == content_hash({"b": [1, 2], "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})
