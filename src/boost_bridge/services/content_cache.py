"""Read-through content cache: Redis → Boost → Postgres snapshot.

The full strategy, with a diagram and failure modes, is in ``docs/design.md`` §5.
In short:

* **fresh** Redis entry (age < soft TTL): served as-is.
* **stale** Redis entry (soft TTL ≤ age < hard TTL): served immediately while one
  background task refreshes it (stale-while-revalidate). A Redis ``SET NX``
  lock deduplicates across replicas, and ``_refreshing`` within a process.
* **miss**: one upstream call per key per process, however many requests are
  waiting (single-flight).
* Boost **unavailable / timed out / rejecting us**: serve the Postgres snapshot
  if there is one (stale-if-error), otherwise raise.
* Boost **404**: remember it briefly, and purge both Redis and the snapshot so
  unpublished content cannot come back through the fallback.

Cached data is the raw upstream payload. It is parsed by the current model on
every read, and an entry the current model cannot parse is treated as a miss.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import ValidationError

from boost_bridge.cache.keys import cache_key, refresh_lock_key
from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostRequest
from boost_bridge.clients.boost.errors import (
    BoostMisconfigured,
    BoostNotFound,
    BoostTimeout,
    BoostUnavailable,
)
from boost_bridge.clients.boost.models import BoostModel
from boost_bridge.core.clock import Clock, SystemClock
from boost_bridge.core.errors import (
    ContentNotFoundError,
    UpstreamMisconfiguredError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from boost_bridge.core.logging import get_logger
from boost_bridge.db.snapshot_repository import Snapshot

log = get_logger(__name__)

_CLIENT_RETRY_AFTER_SECONDS = "5"


class RawFetcher(Protocol):
    async def fetch_raw(self, request: BoostRequest[Any]) -> Any: ...


class SnapshotStore(Protocol):
    async def get(self, cache_key: str) -> Snapshot | None: ...

    async def upsert(
        self, cache_key: str, *, resource: str, locale: str, payload: Any, fetched_at: datetime
    ) -> None: ...

    async def delete(self, cache_key: str) -> None: ...


class Source(StrEnum):
    CACHE = "cache"
    CACHE_STALE = "cache_stale"  # served while a background refresh runs
    UPSTREAM = "upstream"
    SNAPSHOT = "snapshot"  # Boost failed; last-known-good copy


@dataclass(frozen=True, slots=True)
class CacheResult[T]:
    value: T
    source: Source

    @property
    def degraded(self) -> bool:
        """True when the content may be older than one refresh cycle because Boost failed."""
        return self.source is Source.SNAPSHOT


@dataclass(frozen=True, slots=True)
class _Loaded:
    payload: Any
    source: Source


class ContentCache:
    def __init__(
        self,
        fetcher: RawFetcher,
        redis_cache: RedisCache,
        snapshots: SnapshotStore,
        *,
        soft_ttl_seconds: int,
        refresh_lock_ttl_ms: int = 10_000,
        clock: Clock | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._redis = redis_cache
        self._snapshots = snapshots
        self._soft_ttl = soft_ttl_seconds
        self._lock_ttl_ms = refresh_lock_ttl_ms
        self._clock = clock or SystemClock()
        self._inflight: dict[str, asyncio.Future[_Loaded]] = {}
        self._refreshing: dict[str, asyncio.Task[None]] = {}

    async def get[T: BoostModel](self, request: BoostRequest[T]) -> CacheResult[T]:
        key = cache_key(request)
        entry = await self._redis.get(key)

        if entry is not None:
            if entry.negative:
                log.debug("cache_negative_hit", key=key)
                raise ContentNotFoundError()
            try:
                value = request.parse(entry.payload)
            except ValidationError:
                # Written by an older model version, or corrupt. Treat as a miss.
                log.warning("cache_entry_unparseable", key=key)
            else:
                if self._clock.now() - entry.fetched_at < self._soft_ttl:
                    log.debug("cache_hit", key=key)
                    return CacheResult(value, Source.CACHE)
                log.debug("cache_stale_hit", key=key)
                self._schedule_refresh(request, key)
                return CacheResult(value, Source.CACHE_STALE)

        log.debug("cache_miss", key=key)
        loaded = await self._single_flight(request, key)
        return CacheResult(request.parse(loaded.payload), loaded.source)

    async def aclose(self) -> None:
        """Cancel background refreshes. Called from the application lifespan."""
        tasks = list(self._refreshing.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- internals ---------------------------------------------------------

    async def _single_flight(self, request: BoostRequest[Any], key: str) -> _Loaded:
        future = self._inflight.get(key)
        if future is None:
            future = asyncio.ensure_future(self._load(request, key))
            self._inflight[key] = future
            future.add_done_callback(lambda done: self._settle(key, done))
        # shield: a caller that disconnects must not cancel the load for the
        # other requests waiting on the same key.
        return await asyncio.shield(future)

    def _settle(self, key: str, future: asyncio.Future[_Loaded]) -> None:
        if self._inflight.get(key) is future:
            del self._inflight[key]
        if not future.cancelled():
            future.exception()  # mark retrieved; every waiter already received it

    async def _load(self, request: BoostRequest[Any], key: str) -> _Loaded:
        try:
            payload = await self._fetcher.fetch_raw(request)
        except BoostNotFound:
            await self._purge(key)
            raise ContentNotFoundError() from None
        except (BoostUnavailable, BoostTimeout, BoostMisconfigured) as exc:
            snapshot = await self._snapshot_get(key)
            if snapshot is not None:
                log.warning(
                    "serving_snapshot",
                    key=key,
                    reason=type(exc).__name__,
                    snapshot_fetched_at=snapshot.fetched_at.isoformat(),
                )
                return _Loaded(snapshot.payload, Source.SNAPSHOT)
            raise _to_app_error(exc) from exc

        fetched_at = self._clock.now()
        await self._redis.set(key, payload, fetched_at=fetched_at)
        await self._snapshot_upsert(request, key, payload, fetched_at)
        return _Loaded(payload, Source.UPSTREAM)

    def _schedule_refresh(self, request: BoostRequest[Any], key: str) -> None:
        if key in self._refreshing:
            return
        task = asyncio.create_task(self._refresh(request, key), name=f"refresh:{key}")
        self._refreshing[key] = task
        task.add_done_callback(lambda _: self._refreshing.pop(key, None))

    async def _refresh(self, request: BoostRequest[Any], key: str) -> None:
        # The lock is left to expire rather than released, so another replica
        # does not re-fetch straight after this one finished.
        if not await self._redis.try_lock(refresh_lock_key(key), ttl_ms=self._lock_ttl_ms):
            return
        try:
            loaded = await self._single_flight(request, key)
            log.debug("cache_refreshed", key=key, source=loaded.source.value)
        except ContentNotFoundError:
            log.info("cache_refresh_content_gone", key=key)
        except Exception:
            log.exception("cache_refresh_failed", key=key)

    async def _purge(self, key: str) -> None:
        await self._redis.set_negative(key, fetched_at=self._clock.now())
        try:
            await self._snapshots.delete(key)
        except Exception as exc:
            log.warning("snapshot_delete_failed", key=key, error=repr(exc))

    async def _snapshot_get(self, key: str) -> Snapshot | None:
        try:
            return await self._snapshots.get(key)
        except Exception as exc:
            log.warning("snapshot_read_failed", key=key, error=repr(exc))
            return None

    async def _snapshot_upsert(
        self, request: BoostRequest[Any], key: str, payload: Any, fetched_at: float
    ) -> None:
        try:
            await self._snapshots.upsert(
                key,
                resource=request.resource,
                locale=request.locale,
                payload=payload,
                fetched_at=datetime.fromtimestamp(fetched_at, tz=UTC),
            )
        except Exception as exc:
            # Losing a snapshot write only weakens the fallback; the request succeeds.
            log.warning("snapshot_write_failed", key=key, error=repr(exc))


def _to_app_error(
    exc: BoostUnavailable | BoostTimeout | BoostMisconfigured,
) -> UpstreamUnavailableError | UpstreamTimeoutError | UpstreamMisconfiguredError:
    if isinstance(exc, BoostMisconfigured):
        return UpstreamMisconfiguredError()
    retry = {"Retry-After": _CLIENT_RETRY_AFTER_SECONDS}
    if isinstance(exc, BoostTimeout):
        return UpstreamTimeoutError(headers=retry)
    return UpstreamUnavailableError(headers=retry)
