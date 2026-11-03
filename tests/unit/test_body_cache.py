"""BodyCache: Redis-first, Boost-on-miss, no TTL (Plan §13, P6.T3)."""

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis, FakeServer

from boost_bridge.cache.keys import body_cache_key
from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostClient
from boost_bridge.core.errors import ContentNotFoundError, UpstreamUnavailableError
from boost_bridge.services.body_cache import BodyCache, QuestionRef
from tests.factories import lesson_payload, problem_payload, question_payload
from tests.fakes import FakeClock

BASE = "https://boost.test"
LOCALE = "sv-SE"


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=BASE) as client:
        yield client  # type: ignore[misc]


@pytest.fixture
def boost_client(http: httpx.AsyncClient) -> BoostClient:
    return BoostClient(http, token="svc-token", max_retries=0)


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(server=FakeServer())


@pytest.fixture
def redis_cache(redis: FakeAsyncRedis) -> RedisCache:
    return RedisCache(redis, hard_ttl_seconds=3600, negative_ttl_seconds=30)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def body_cache(boost_client: BoostClient, redis_cache: RedisCache, clock: FakeClock) -> BodyCache:
    return BodyCache(boost_client, redis_cache, batch_max_refs=100, clock=clock)


async def _seed_question(redis_cache: RedisCache, clock: FakeClock, ref: QuestionRef) -> None:
    key = body_cache_key("QUESTION", ref.id, ref.version, LOCALE)
    await redis_cache.set_forever(
        key, question_payload(question_id=ref.id, locale=LOCALE), fetched_at=clock.now()
    )


# --- questions ---------------------------------------------------------------


@respx.mock
async def test_cache_hit_makes_no_boost_call(
    body_cache: BodyCache, redis_cache: RedisCache, clock: FakeClock
) -> None:
    ref = QuestionRef(id="100", version="5")
    await _seed_question(redis_cache, clock, ref)
    route = respx.get(f"{BASE}/v1/delivery/questions/revisions")

    found, missing = await body_cache.get_question_revisions([ref], LOCALE)

    assert found["100"].id == "100"
    assert missing == []
    assert route.call_count == 0


@respx.mock
async def test_mixed_hit_and_miss_fetches_only_missing_in_one_batch_call(
    body_cache: BodyCache, redis_cache: RedisCache, clock: FakeClock
) -> None:
    cached = QuestionRef(id="100", version="5")
    uncached = QuestionRef(id="200", version="3")
    await _seed_question(redis_cache, clock, cached)
    route = respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(
        json={"items": [question_payload(question_id="200", locale=LOCALE)], "missing": []}
    )

    found, missing = await body_cache.get_question_revisions([cached, uncached], LOCALE)

    assert set(found) == {"100", "200"}
    assert missing == []
    assert route.call_count == 1
    assert route.calls.last.request.url.params["refs"] == "200:3"


@respx.mock
async def test_mixed_hit_and_miss_caches_the_fetched_item_forever(
    body_cache: BodyCache, redis_cache: RedisCache, redis: FakeAsyncRedis, clock: FakeClock
) -> None:
    uncached = QuestionRef(id="200", version="3")
    respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(
        json={"items": [question_payload(question_id="200", locale=LOCALE)], "missing": []}
    )

    await body_cache.get_question_revisions([uncached], LOCALE)

    # Cached under the version Boost actually returned (factories.py's question_payload
    # always answers "5"), not the version that was requested.
    key = body_cache_key("QUESTION", "200", "5", LOCALE)
    assert await redis.get(key) is not None
    assert await redis.ttl(key) == -1  # no TTL at all — immutable


@respx.mock
async def test_boost_missing_ref_is_dropped_and_logged(body_cache: BodyCache) -> None:
    ref = QuestionRef(id="999", version="1")
    respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(
        json={"items": [], "missing": ["999:1"]}
    )

    found, missing = await body_cache.get_question_revisions([ref], LOCALE)

    assert found == {}
    assert missing == [ref]


@respx.mock
async def test_boost_down_but_fully_cached_is_served(
    body_cache: BodyCache, redis_cache: RedisCache, clock: FakeClock
) -> None:
    ref = QuestionRef(id="100", version="5")
    await _seed_question(redis_cache, clock, ref)
    route = respx.get(f"{BASE}/v1/delivery/questions/revisions").mock(
        side_effect=httpx.ConnectError("refused")
    )

    found, missing = await body_cache.get_question_revisions([ref], LOCALE)

    assert found["100"].id == "100"
    assert missing == []
    assert route.call_count == 0


@respx.mock
async def test_boost_down_and_not_cached_is_unavailable(body_cache: BodyCache) -> None:
    ref = QuestionRef(id="100", version="5")
    respx.get(f"{BASE}/v1/delivery/questions/revisions").mock(
        side_effect=httpx.ConnectError("refused")
    )

    with pytest.raises(UpstreamUnavailableError):
        await body_cache.get_question_revisions([ref], LOCALE)


@respx.mock
async def test_boost_rejecting_batch_and_not_cached_is_unavailable(body_cache: BodyCache) -> None:
    ref = QuestionRef(id="100", version="5")
    respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(503, json=problem_payload(503))

    with pytest.raises(UpstreamUnavailableError):
        await body_cache.get_question_revisions([ref], LOCALE)


@respx.mock
async def test_more_refs_than_batch_max_are_split_into_multiple_calls(
    boost_client: BoostClient, redis_cache: RedisCache, clock: FakeClock
) -> None:
    body_cache = BodyCache(boost_client, redis_cache, batch_max_refs=2, clock=clock)
    refs = [QuestionRef(id=str(i), version="1") for i in range(5)]
    route = respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(
        json={
            "items": [question_payload(question_id=str(i), locale=LOCALE) for i in range(5)],
            "missing": [],
        }
    )
    # Each chunk only asks for its own slice, so a single fixed response above
    # doesn't model per-chunk refs precisely, but the call *count* still proves
    # chunking happened — the refs param format is checked in the earlier test.

    await body_cache.get_question_revisions(refs, LOCALE)

    assert route.call_count == 3  # ceil(5 / 2)


async def test_empty_refs_makes_no_call(body_cache: BodyCache) -> None:
    found, missing = await body_cache.get_question_revisions([], LOCALE)
    assert found == {}
    assert missing == []


# --- lesson revisions ----------------------------------------------------------


@respx.mock
async def test_lesson_cache_hit_makes_no_boost_call(
    body_cache: BodyCache, redis_cache: RedisCache, clock: FakeClock
) -> None:
    key = body_cache_key("LESSON", "10", "2", LOCALE)
    await redis_cache.set_forever(
        key, lesson_payload(lesson_id="10", locale=LOCALE), fetched_at=clock.now()
    )
    route = respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2")

    lesson = await body_cache.get_lesson_revision("10", "2", LOCALE)

    assert lesson.id == "10"
    assert route.call_count == 0


@respx.mock
async def test_lesson_cache_miss_fetches_and_caches_forever(
    body_cache: BodyCache, redis: FakeAsyncRedis
) -> None:
    respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2").respond(
        json=lesson_payload(lesson_id="10", locale=LOCALE)
    )

    lesson = await body_cache.get_lesson_revision("10", "2", LOCALE)

    assert lesson.id == "10"
    key = body_cache_key("LESSON", "10", "2", LOCALE)
    assert await redis.get(key) is not None
    assert await redis.ttl(key) == -1


@respx.mock
async def test_lesson_not_found_raises_content_not_found(body_cache: BodyCache) -> None:
    respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2").respond(404, json=problem_payload(404))

    with pytest.raises(ContentNotFoundError):
        await body_cache.get_lesson_revision("10", "2", LOCALE)


@respx.mock
async def test_lesson_boost_down_raises_unavailable(body_cache: BodyCache) -> None:
    respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2").mock(
        side_effect=httpx.ConnectError("refused")
    )

    with pytest.raises(UpstreamUnavailableError):
        await body_cache.get_lesson_revision("10", "2", LOCALE)
