"""The content sync: Boost's published catalogue into the content tables.

One run lists every module, lesson, question, mock exam and learning journey in
every locale, fetches answer keys only for question revisions not stored yet,
and writes only what changed. Published revisions never change, so after the
first run a quiet catalogue costs zero grading calls.

Several instances may run the loop; a transaction-scoped advisory lock lets only
one of them write per round.
"""

import asyncio
import contextlib
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.clients.boost.grading import BoostGradingRevision
from fordona_connect.core.logging import get_logger
from fordona_connect.learning.content.catalogue import fetch_catalogue, fetch_grading
from fordona_connect.learning.content.read_model import build_read_model, refs_needing_grading
from fordona_connect.learning.content.writer import stored_correct_keys, write_read_model

log = get_logger(__name__)

# Arbitrary, fixed: "fordona" in ASCII. Shared by every instance of this service.
SYNC_LOCK_KEY = 0x666F72646F6E61


@dataclass(frozen=True, slots=True)
class SyncResult:
    changed: bool
    release_id: int
    new_revisions: int
    grading_calls: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ContentSyncService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        client: BoostClient,
        *,
        locales: Collection[str],
        default_locale: str,
        page_size: int,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if default_locale not in locales:
            raise ValueError(f"default locale {default_locale!r} is not among {list(locales)}")
        self._sessionmaker = sessionmaker
        self._client = client
        self._locales = list(locales)
        self._default_locale = default_locale
        self._page_size = page_size
        self._now = now
        # Answer keys fetched this process for revisions that are not stored
        # (excluded questions), so they are not fetched again every round.
        self._fetched: dict[tuple[str, str], BoostGradingRevision] = {}

    async def sync(self) -> SyncResult | None:
        """Run one sync. ``None`` if another instance holds the lock this round."""
        catalogue = await fetch_catalogue(
            self._client,
            self._locales,
            default_locale=self._default_locale,
            page_size=self._page_size,
        )
        async with self._sessionmaker() as session:
            known_keys = await stored_correct_keys(session)

        refs = refs_needing_grading(catalogue, known_keys) - self._fetched.keys()
        fetched = await fetch_grading(self._client, refs)
        self._fetched.update(
            {ref: revision for ref, revision in fetched.items() if revision is not None}
        )
        model = build_read_model(
            catalogue, stored_correct_keys=known_keys, grading={**self._fetched, **fetched}
        )

        async with self._sessionmaker() as session, session.begin():
            locked = await session.scalar(select(func.pg_try_advisory_xact_lock(SYNC_LOCK_KEY)))
            if not locked:
                log.info("content_sync_skipped_locked")
                return None
            written = await write_read_model(session, model, self._now())

        result = SyncResult(
            changed=written.changed,
            release_id=written.release_id,
            new_revisions=written.new_revisions,
            grading_calls=len(refs),
        )
        log.info(
            "content_sync_done",
            changed=result.changed,
            release_id=result.release_id,
            new_revisions=result.new_revisions,
            grading_calls=result.grading_calls,
            questions=len(model.questions),
        )
        return result


class ContentSyncRunner:
    """Runs ``ContentSyncService.sync`` every ``interval`` seconds in the background."""

    def __init__(self, service: ContentSyncService, interval: float) -> None:
        self._service = service
        self._interval = interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="content-sync")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._service.sync()
            except asyncio.CancelledError:
                raise
            except Exception:
                # The next round retries from scratch; nothing was half-written,
                # because the write is one transaction.
                log.exception("content_sync_failed")
            await asyncio.sleep(self._interval)
