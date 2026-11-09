"""Alembic environment (async). Runs as a pre-deploy step, never at app startup.

fordona-connect shares fordona-engine's database, so everything it owns — its tables and
Alembic's own version table — lives in the ``connect_learning`` schema. The migration files
create tables by bare name; ``SET LOCAL search_path`` inside the migration transaction
points those names at the schema without editing (already-applied) migration files, and
``SET LOCAL`` is safe behind a transaction-mode pooler because it ends with the
transaction.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from fordona_connect.db.connection import ASYNCPG_CONNECT_ARGS, DB_SCHEMA, normalize_database_url
from fordona_connect.db.models import Base
from fordona_connect.learning.content import models as _content_models  # noqa: F401 - registers tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Read DATABASE_URL directly instead of loading Settings: migrations must
    # not require Boost or Kinde configuration to run.
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=DB_SCHEMA,
    )
    with context.begin_transaction():
        context.execute(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
        context.execute(f'SET LOCAL search_path TO "{DB_SCHEMA}"')
        context.run_migrations()


def _run(connection: Connection) -> None:
    # Opens the one transaction every migration runs in; Alembic's begin_transaction()
    # joins it rather than starting its own, so it is committed explicitly below.
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{DB_SCHEMA}"'))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=DB_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()


async def run_migrations_online() -> None:
    engine = create_async_engine(
        _database_url(), poolclass=pool.NullPool, connect_args=ASYNCPG_CONNECT_ARGS
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
