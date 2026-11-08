"""Async engine and session factory (SQLAlchemy 2 + asyncpg)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fordona_connect.core.config import Settings
from fordona_connect.db.connection import ASYNCPG_CONNECT_ARGS


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=2,  # fail fast; the snapshot is a fallback, not the hot path
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={**ASYNCPG_CONNECT_ARGS, "timeout": 2, "command_timeout": 2},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
