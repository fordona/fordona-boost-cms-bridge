"""How fordona-connect connects to Postgres: URL driver, schema, and pooler-safe asyncpg options.

fordona-connect shares fordona-engine's database. Three consequences live here, with no
dependency on ``Settings``, so ``migrations/env.py`` can use them without needing Boost
or Kinde configuration:

* **Driver.** Hosting panels and the engine's own ``DB_*`` values describe the database
  as ``postgresql://`` (or ``postgres://``). SQLAlchemy 2.1 maps a driverless
  ``postgresql://`` to psycopg 3, which this project doesn't install — the pre-deploy
  migration crashed with ``No module named 'psycopg'``. ``normalize_database_url``
  rewrites those to ``postgresql+asyncpg://`` and refuses any other explicit driver.
* **Schema.** Every fordona-connect table lives in ``DB_SCHEMA``, never in the engine's
  ``public`` schema, so the two services' tables can't collide and fordona-connect's footprint
  can be granted, inspected or dropped as one unit.
* **Pooler.** The engine's production JDBC URL sets ``prepareThreshold=0``, the usual sign
  of a transaction-mode pooler (PgBouncer, Supabase's pooler). Behind one, consecutive
  statements can land on different server connections, so asyncpg's cached prepared
  statements fail with ``prepared statement "__asyncpg_stmt_N__" already exists`` /
  ``does not exist``. ``ASYNCPG_CONNECT_ARGS`` turns both statement caches off and gives
  every prepared statement a unique name — SQLAlchemy's documented asyncpg + PgBouncer
  setup. It is harmless on a direct connection, so it is always on.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DB_SCHEMA = "connect_learning"

_ASYNC_DRIVERNAME = "postgresql+asyncpg"
_DRIVERLESS = frozenset({"postgres", "postgresql"})


def _unique_statement_name() -> str:
    return f"__asyncpg_{uuid4()}__"


ASYNCPG_CONNECT_ARGS: dict[str, Any] = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
    "prepared_statement_name_func": _unique_statement_name,
}


def normalize_database_url(url: str) -> str:
    """Return ``url`` with the asyncpg driver, or raise ``ValueError`` for anything else."""
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise ValueError("DATABASE_URL is not a valid database URL") from exc
    if parsed.drivername in _DRIVERLESS:
        parsed = parsed.set(drivername=_ASYNC_DRIVERNAME)
    elif parsed.drivername != _ASYNC_DRIVERNAME:
        raise ValueError(
            f"DATABASE_URL must be a PostgreSQL URL for asyncpg "
            f"(postgresql:// or {_ASYNC_DRIVERNAME}://), got {parsed.drivername}://"
        )
    return parsed.render_as_string(hide_password=False)
