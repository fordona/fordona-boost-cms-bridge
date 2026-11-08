import pytest

from fordona_connect.db.connection import (
    ASYNCPG_CONNECT_ARGS,
    DB_SCHEMA,
    normalize_database_url,
)
from fordona_connect.db.models import Base


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.internal:5432/fordona",
        "postgres://u:p@db.internal:5432/fordona",
        "postgresql+asyncpg://u:p@db.internal:5432/fordona",
    ],
)
def test_postgres_urls_are_normalized_to_asyncpg(url: str) -> None:
    assert normalize_database_url(url) == "postgresql+asyncpg://u:p@db.internal:5432/fordona"


def test_normalized_url_keeps_query_and_special_password_characters() -> None:
    url = "postgresql://u:p%40ss@db.internal:6543/fordona?ssl=require"
    assert (
        normalize_database_url(url)
        == "postgresql+asyncpg://u:p%40ss@db.internal:6543/fordona?ssl=require"
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db/fordona",
        "postgresql+psycopg2://u:p@db/fordona",
        "mysql://u:p@db/fordona",
    ],
)
def test_other_drivers_are_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="asyncpg"):
        normalize_database_url(url)


def test_garbage_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a valid database URL"):
        normalize_database_url("not a url")


def test_asyncpg_statement_caches_are_off_for_poolers() -> None:
    assert ASYNCPG_CONNECT_ARGS["statement_cache_size"] == 0
    assert ASYNCPG_CONNECT_ARGS["prepared_statement_cache_size"] == 0


def test_prepared_statement_names_are_unique() -> None:
    name_func = ASYNCPG_CONNECT_ARGS["prepared_statement_name_func"]
    assert name_func() != name_func()


def test_every_table_is_in_the_connect_learning_schema() -> None:
    import fordona_connect.learning_journey.models  # noqa: F401 - registers the tables

    assert Base.metadata.tables
    assert {table.schema for table in Base.metadata.tables.values()} == {DB_SCHEMA}


def test_foreign_keys_point_into_the_connect_learning_schema() -> None:
    import fordona_connect.learning_journey.models  # noqa: F401 - registers the tables

    targets = {
        fk.column.table.schema
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    }
    assert targets == {DB_SCHEMA}
