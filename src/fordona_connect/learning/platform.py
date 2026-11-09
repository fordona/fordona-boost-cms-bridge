"""Platform facts from fordona-engine: who a learner is, whether they subscribe, and
what changed (events). fordona-connect calls the engine; the engine never calls
fordona-connect.

* ``PlatformClient`` reads ``GET /internal/learning/v1/learners/{kindeSubject}``,
  caches it in Redis for ``ttl_seconds`` (shared by every replica), and **fails
  closed**: with the engine unreachable and nothing cached, a learner is treated
  as not subscribed.
* ``PlatformEventConsumer`` pulls ``GET /internal/learning/v1/events?after=``
  (the engine's outbox). One replica at a time consumes, behind an advisory lock;
  the cursor lives in ``platform_event_cursor``. Delivery is at least once, so
  every handler is idempotent.
"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from sqlalchemy import BigInteger, Integer, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.core.errors import AppError
from fordona_connect.core.logging import get_logger
from fordona_connect.db.models import Base
from fordona_connect.learning.attempts.models import AttemptItem, LessonAttempt, Mistake
from fordona_connect.learning.progress.models import (
    LearnerActivityDay,
    LearnerActivityLesson,
    LearnerSummary,
    LessonProgress,
)
from fordona_connect.learning.progress.screens import LearnerProfile

log = get_logger(__name__)

EVENTS_LOCK_KEY = 0x666F72646F6E62  # "fordonb": distinct from the content sync's lock
_CACHE_PREFIX = "connect:learner:"


class PlatformEventCursor(Base):
    """Where the event consumer is in the engine's outbox (a single row, id 1)."""

    __tablename__ = "platform_event_cursor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


@dataclass(frozen=True, slots=True)
class LearnerContext:
    user_id: int | None
    first_name: str
    last_name: str
    subscribed: bool


class KeyValueStore(Protocol):
    """The slice of ``redis.asyncio.Redis`` the client uses."""

    def get(self, name: str) -> Awaitable[Any]: ...

    def set(self, name: str, value: str, ex: int | None = None) -> Awaitable[Any]: ...

    def delete(self, *names: str) -> Awaitable[Any]: ...


class PlatformClient:
    def __init__(
        self, engine: EngineClient, cache: KeyValueStore, *, ttl_seconds: int = 60
    ) -> None:
        self._engine = engine
        self._cache = cache
        self._ttl = ttl_seconds

    async def learner(self, learner_id: str) -> LearnerContext:
        key = _CACHE_PREFIX + learner_id
        try:
            cached = await self._cache.get(key)
        except Exception:  # a cache outage must not block learning
            log.warning("learner_cache_read_failed", exc_info=True)
            cached = None
        if cached:
            return LearnerContext(**json.loads(cached))
        try:
            response = await self._engine.get_as_service(
                f"/internal/learning/v1/learners/{learner_id}"
            )
        except AppError as exc:
            log.warning("learner_context_unavailable_failing_closed", error=repr(exc))
            return LearnerContext(user_id=None, first_name="", last_name="", subscribed=False)
        data = response.data or {}
        context = LearnerContext(
            user_id=data.get("userId"),
            first_name=data.get("firstName") or "",
            last_name=data.get("lastName") or "",
            subscribed=bool(data.get("subscribed", False)),
        )
        try:
            await self._cache.set(key, json.dumps(asdict(context)), ex=self._ttl)
        except Exception:
            log.warning("learner_cache_write_failed", exc_info=True)
        return context

    async def forget(self, learner_id: str) -> None:
        try:
            await self._cache.delete(_CACHE_PREFIX + learner_id)
        except Exception:
            log.warning("learner_cache_delete_failed", exc_info=True)

    # SubscriptionSource
    async def is_subscribed(self, learner_id: str) -> bool:
        return (await self.learner(learner_id)).subscribed

    # ProfileSource
    async def profile(self, learner_id: str) -> LearnerProfile:
        context = await self.learner(learner_id)
        return LearnerProfile(first_name=context.first_name, last_name=context.last_name)


async def forget_learner_data(session: AsyncSession, learner_id: str) -> None:
    """Delete a learner's learning data (``user.deleted``). Idempotent."""
    from fordona_connect.learning_journey import models as journey

    for table in (
        LearnerActivityLesson,
        LearnerActivityDay,
        LearnerSummary,
        LessonProgress,
        Mistake,
        AttemptItem,
        LessonAttempt,
    ):
        await session.execute(delete(table).where(table.learner_id == learner_id))
    for journey_table in (
        journey.LearningJourneyIdempotencyRecord,
        journey.LearningJourneyRemediation,
        journey.LearningJourneyAttemptQuestion,
        journey.LearningJourneyAttempt,
        journey.LearningJourneySession,
        journey.LearningJourneyUserChallengeProgress,
        journey.LearningJourneyUserAssignment,
    ):
        column = getattr(journey_table, "app_user_id", None)
        if column is not None:
            await session.execute(delete(journey_table).where(column == learner_id))
        elif journey_table is journey.LearningJourneyAttemptQuestion:
            attempts = select(journey.LearningJourneyAttempt.attempt_id).where(
                journey.LearningJourneyAttempt.app_user_id == learner_id
            )
            await session.execute(
                delete(journey_table).where(journey_table.attempt_id.in_(attempts))
            )
        elif journey_table is journey.LearningJourneyRemediation:
            sessions = select(journey.LearningJourneySession.session_id).where(
                journey.LearningJourneySession.app_user_id == learner_id
            )
            await session.execute(
                delete(journey_table).where(journey_table.session_id.in_(sessions))
            )
        elif journey_table is journey.LearningJourneyUserChallengeProgress:
            assignments = select(journey.LearningJourneyUserAssignment.assignment_id).where(
                journey.LearningJourneyUserAssignment.app_user_id == learner_id
            )
            await session.execute(
                delete(journey_table).where(journey_table.assignment_id.in_(assignments))
            )


class PlatformEventConsumer:
    """Pulls the engine's outbox and applies each event once per cursor position."""

    def __init__(
        self,
        engine: EngineClient,
        sessionmaker: async_sessionmaker[AsyncSession],
        platform: PlatformClient,
        *,
        interval_seconds: float = 5.0,
        batch_size: int = 100,
    ) -> None:
        self._engine = engine
        self._sessionmaker = sessionmaker
        self._platform = platform
        self._interval = interval_seconds
        self._batch = batch_size
        self._task: asyncio.Task[None] | None = None
        self._handlers: dict[str, Callable[[AsyncSession, str], Awaitable[None]]] = {
            "subscription.changed": self._invalidate,
            "user.updated": self._invalidate,
            "user.deleted": self._delete,
        }

    async def _invalidate(self, session: AsyncSession, learner_id: str) -> None:
        await self._platform.forget(learner_id)

    async def _delete(self, session: AsyncSession, learner_id: str) -> None:
        await forget_learner_data(session, learner_id)
        await self._platform.forget(learner_id)

    async def consume_once(self) -> int | None:
        """Apply one batch. ``None`` if another replica holds the lock this round."""
        async with self._sessionmaker() as session, session.begin():
            if not await session.scalar(select(func.pg_try_advisory_xact_lock(EVENTS_LOCK_KEY))):
                return None
            cursor = await session.get(PlatformEventCursor, 1)
            after = cursor.last_event_id if cursor else 0
            response = await self._engine.get_as_service(
                "/internal/learning/v1/events",
                params={"after": str(after), "limit": str(self._batch)},
            )
            events = (response.data or {}).get("events", [])
            last = after
            for event in events:
                handler = self._handlers.get(event.get("type", ""))
                subject = event.get("kindeSubject")
                if handler is not None and subject:
                    await handler(session, subject)
                last = max(last, int(event["id"]))
            if last != after:
                await session.execute(
                    pg_insert(PlatformEventCursor)
                    .values(id=1, last_event_id=last)
                    .on_conflict_do_update(index_elements=["id"], set_={"last_event_id": last})
                )
            if events:
                log.info("platform_events_applied", count=len(events), cursor=last)
            return len(events)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="platform-events")

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
                await self.consume_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("platform_events_failed")
            await asyncio.sleep(self._interval)
