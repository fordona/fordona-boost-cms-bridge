"""Persistence for last-known-good content snapshots."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boost_bridge.db.models import ContentSnapshot


@dataclass(frozen=True, slots=True)
class Snapshot:
    payload: Any
    fetched_at: datetime


def content_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SnapshotRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, cache_key: str) -> Snapshot | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(ContentSnapshot.payload, ContentSnapshot.fetched_at).where(
                        ContentSnapshot.cache_key == cache_key
                    )
                )
            ).one_or_none()
        return Snapshot(payload=row.payload, fetched_at=row.fetched_at) if row else None

    async def upsert(
        self, cache_key: str, *, resource: str, locale: str, payload: Any, fetched_at: datetime
    ) -> None:
        """Insert or replace, writing nothing when the content has not changed.

        Most refreshes return identical content. The ``WHERE`` on the conflict
        branch turns those into no-ops, so a busy cache does not churn the table.
        """
        digest = content_hash(payload)
        stmt = insert(ContentSnapshot).values(
            cache_key=cache_key,
            resource=resource,
            locale=locale,
            payload=payload,
            content_hash=digest,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ContentSnapshot.cache_key],
            set_={
                "payload": stmt.excluded.payload,
                "content_hash": stmt.excluded.content_hash,
                "fetched_at": stmt.excluded.fetched_at,
            },
            where=ContentSnapshot.content_hash != stmt.excluded.content_hash,
        )
        async with self._sessionmaker() as session, session.begin():
            await session.execute(stmt)

    async def delete(self, cache_key: str) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                delete(ContentSnapshot).where(ContentSnapshot.cache_key == cache_key)
            )
