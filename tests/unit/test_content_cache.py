"""Cache and refresh logic: freshness, SWR, single-flight, fail-open, fallback, purge."""

import asyncio
from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis, FakeServer

from boost_bridge.cache.keys import cache_key, refresh_lock_key
from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.clients.boost.errors import (
    BoostMisconfigured,
    BoostNotFound,
    BoostTimeout,
    BoostUnavailable,
)
from boost_bridge.core.errors import (
    ContentNotFoundError,
    UpstreamMisconfiguredError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from boost_bridge.db.snapshot_repository import Snapshot
from boost_bridge.services.content_cache import ContentCache, Source
from tests.factories import module_payload
from tests.fakes import FakeClock, FakeFetcher, InMemorySnapshots

PATH = "/v1/delivery/modules/1"
SOFT_TTL = 300
REQUEST = BoostRequests.module("1", "sv-SE")
KEY = cache_key(REQUEST)


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def redis(server: FakeServer) -> FakeAsyncRedis:
    return FakeAsyncRedis(server=server)


@pytest.fixture
def redis_cache(redis: FakeAsyncRedis) -> RedisCache:
    return RedisCache(redis, hard_ttl_seconds=3600, negative_ttl_seconds=30)


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher({PATH: module_payload()})


@pytest.fixture
def snapshots() -> InMemorySnapshots:
    return InMemorySnapshots()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def cache(
    fetcher: FakeFetcher, redis_cache: RedisCache, snapshots: InMemorySnapshots, clock: FakeClock
) -> ContentCache:
    cache = ContentCache(fetcher, redis_cache, snapshots, soft_ttl_seconds=SOFT_TTL, clock=clock)
    yield cache  # type: ignore[misc]
    await cache.aclose()


async def _drain(cache: ContentCache) -> None:
    await asyncio.gather(*list(cache._refreshing.values()), return_exceptions=True)


# --- freshness ---------------------------------------------------------------


async def test_miss_fetches_and_populates_redis_and_snapshot(
    cache: ContentCache, fetcher: FakeFetcher, redis: FakeAsyncRedis, snapshots: InMemorySnapshots
) -> None:
    result = await cache.get(REQUEST)

    assert result.source is Source.UPSTREAM
    assert result.value.id == "1"
    assert fetcher.calls_to(PATH) == 1
    assert await redis.get(KEY) is not None
    assert await redis.ttl(KEY) == 3600  # hard TTL
    assert KEY in snapshots.rows


async def test_fresh_hit_does_not_call_upstream(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL - 1)

    result = await cache.get(REQUEST)

    assert result.source is Source.CACHE
    assert fetcher.calls_to(PATH) == 1


async def test_stale_hit_is_served_and_refreshed_in_background(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)
    fetcher.responses[PATH] = module_payload(title="Updated")

    stale = await cache.get(REQUEST)
    assert stale.source is Source.CACHE_STALE
    assert stale.value.translation is not None
    assert stale.value.translation.title == "Trafikregler"  # old value, served immediately

    await _drain(cache)
    assert fetcher.calls_to(PATH) == 2

    fresh = await cache.get(REQUEST)
    assert fresh.source is Source.CACHE
    assert fresh.value.translation is not None
    assert fresh.value.translation.title == "Updated"


async def test_concurrent_stale_hits_trigger_one_refresh(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)

    await asyncio.gather(*(cache.get(REQUEST) for _ in range(20)))
    await _drain(cache)

    assert fetcher.calls_to(PATH) == 2  # initial load + exactly one refresh


async def test_refresh_skipped_when_another_replica_holds_the_lock(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock, redis: FakeAsyncRedis
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)
    await redis.set(refresh_lock_key(KEY), b"1", px=10_000)  # held elsewhere

    result = await cache.get(REQUEST)
    await _drain(cache)

    assert result.source is Source.CACHE_STALE
    assert fetcher.calls_to(PATH) == 1


async def test_failed_refresh_keeps_serving_stale_entry(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)
    fetcher.responses[PATH] = BoostUnavailable("down")

    await cache.get(REQUEST)
    await _drain(cache)
    clock.advance(1)
    result = await cache.get(REQUEST)

    assert result.source in {Source.CACHE_STALE, Source.SNAPSHOT}
    assert result.value.id == "1"


# --- single-flight -------------------------------------------------------------


async def test_concurrent_misses_share_one_upstream_call(
    cache: ContentCache, fetcher: FakeFetcher
) -> None:
    fetcher.gate = asyncio.Event()
    waiters = [asyncio.create_task(cache.get(REQUEST)) for _ in range(25)]
    await asyncio.sleep(0)
    fetcher.gate.set()

    results = await asyncio.gather(*waiters)

    assert fetcher.calls_to(PATH) == 1
    assert {r.value.id for r in results} == {"1"}


async def test_cancelled_waiter_does_not_cancel_shared_load(
    cache: ContentCache, fetcher: FakeFetcher
) -> None:
    fetcher.gate = asyncio.Event()
    first = asyncio.create_task(cache.get(REQUEST))
    second = asyncio.create_task(cache.get(REQUEST))
    await asyncio.sleep(0)
    first.cancel()
    fetcher.gate.set()

    result = await second

    assert result.value.id == "1"
    assert fetcher.calls_to(PATH) == 1


async def test_single_flight_propagates_errors_to_all_waiters(
    cache: ContentCache, fetcher: FakeFetcher
) -> None:
    fetcher.responses[PATH] = BoostNotFound("gone")
    fetcher.gate = asyncio.Event()
    waiters = [asyncio.create_task(cache.get(REQUEST)) for _ in range(3)]
    await asyncio.sleep(0)
    fetcher.gate.set()

    results = await asyncio.gather(*waiters, return_exceptions=True)

    assert all(isinstance(r, ContentNotFoundError) for r in results)
    assert fetcher.calls_to(PATH) == 1


# --- Redis failure (fail-open) -------------------------------------------------


async def test_redis_down_falls_through_to_upstream(
    cache: ContentCache, fetcher: FakeFetcher, server: FakeServer
) -> None:
    server.connected = False

    first = await cache.get(REQUEST)
    second = await cache.get(REQUEST)

    assert first.source is Source.UPSTREAM
    assert second.source is Source.UPSTREAM
    assert fetcher.calls_to(PATH) == 2


async def test_corrupt_redis_entry_is_a_miss(
    cache: ContentCache, fetcher: FakeFetcher, redis: FakeAsyncRedis
) -> None:
    await redis.set(KEY, b"{not json")

    result = await cache.get(REQUEST)

    assert result.source is Source.UPSTREAM
    assert fetcher.calls_to(PATH) == 1


async def test_unparseable_cached_payload_is_a_miss(
    cache: ContentCache, fetcher: FakeFetcher, redis_cache: RedisCache, clock: FakeClock
) -> None:
    await redis_cache.set(KEY, {"no": "id field"}, fetched_at=clock.now())

    result = await cache.get(REQUEST)

    assert result.source is Source.UPSTREAM
    assert fetcher.calls_to(PATH) == 1


# --- upstream failure → snapshot (stale-if-error) -----------------------------


@pytest.mark.parametrize(
    "failure",
    [BoostUnavailable("down"), BoostTimeout("slow"), BoostMisconfigured("bad token", status=401)],
)
async def test_upstream_failure_serves_snapshot(
    cache: ContentCache,
    fetcher: FakeFetcher,
    snapshots: InMemorySnapshots,
    failure: Exception,
) -> None:
    snapshots.rows[KEY] = Snapshot(payload=module_payload(), fetched_at=datetime.now(UTC))
    fetcher.responses[PATH] = failure

    result = await cache.get(REQUEST)

    assert result.source is Source.SNAPSHOT
    assert result.degraded
    assert result.value.id == "1"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (BoostUnavailable("down"), UpstreamUnavailableError),
        (BoostTimeout("slow"), UpstreamTimeoutError),
        (BoostMisconfigured("bad token", status=401), UpstreamMisconfiguredError),
    ],
)
async def test_upstream_failure_without_snapshot_raises(
    cache: ContentCache, fetcher: FakeFetcher, failure: Exception, expected: type[Exception]
) -> None:
    fetcher.responses[PATH] = failure

    with pytest.raises(expected):
        await cache.get(REQUEST)


async def test_snapshot_store_down_does_not_mask_upstream_error(
    cache: ContentCache, fetcher: FakeFetcher, snapshots: InMemorySnapshots
) -> None:
    snapshots.fail = True
    fetcher.responses[PATH] = BoostUnavailable("down")

    with pytest.raises(UpstreamUnavailableError) as exc_info:
        await cache.get(REQUEST)

    assert exc_info.value.headers["Retry-After"] == "5"


async def test_snapshot_write_failure_does_not_fail_request(
    cache: ContentCache, snapshots: InMemorySnapshots
) -> None:
    snapshots.fail = True

    result = await cache.get(REQUEST)

    assert result.source is Source.UPSTREAM


async def test_upstream_failure_is_not_cached(
    cache: ContentCache, fetcher: FakeFetcher, redis: FakeAsyncRedis
) -> None:
    fetcher.responses[PATH] = BoostUnavailable("down")
    with pytest.raises(UpstreamUnavailableError):
        await cache.get(REQUEST)
    assert await redis.get(KEY) is None


# --- 404 / unpublish ---------------------------------------------------------


async def test_not_found_purges_snapshot_and_is_negatively_cached(
    cache: ContentCache,
    fetcher: FakeFetcher,
    snapshots: InMemorySnapshots,
    redis: FakeAsyncRedis,
) -> None:
    snapshots.rows[KEY] = Snapshot(payload=module_payload(), fetched_at=datetime.now(UTC))
    fetcher.responses[PATH] = BoostNotFound("unpublished")

    with pytest.raises(ContentNotFoundError):
        await cache.get(REQUEST)
    with pytest.raises(ContentNotFoundError):
        await cache.get(REQUEST)

    assert KEY not in snapshots.rows
    assert fetcher.calls_to(PATH) == 1  # second 404 came from the negative entry
    assert 0 < await redis.ttl(KEY) <= 30


async def test_unpublished_content_disappears_on_refresh(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock, snapshots: InMemorySnapshots
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)
    fetcher.responses[PATH] = BoostNotFound("unpublished")

    await cache.get(REQUEST)  # stale served once, refresh discovers the 404
    await _drain(cache)

    assert KEY not in snapshots.rows
    with pytest.raises(ContentNotFoundError):
        await cache.get(REQUEST)


async def test_aclose_cancels_pending_refreshes(
    cache: ContentCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get(REQUEST)
    clock.advance(SOFT_TTL + 1)
    fetcher.gate = asyncio.Event()  # refresh will hang

    await cache.get(REQUEST)
    await asyncio.sleep(0)
    assert cache._refreshing

    await cache.aclose()
    assert not cache._refreshing


def test_cache_key_varies_by_locale_and_params() -> None:
    sv = cache_key(BoostRequests.modules("sv-SE", page=1, page_size=20))
    en = cache_key(BoostRequests.modules("en-GB", page=1, page_size=20))
    page2 = cache_key(BoostRequests.modules("sv-SE", page=2, page_size=20))
    assert len({sv, en, page2}) == 3
    assert sv.startswith("bridge:v1:module_list:sv-SE:")
