"""Release prefetch (Plan §9.1/§9.4, P6.T7): gate dedup + the runner's own work."""

import httpx
import respx
from fakeredis import FakeAsyncRedis, FakeServer

from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostClient
from boost_bridge.services.body_cache import BodyCache
from boost_bridge.services.release_prefetch import (
    ReleasePrefetchGate,
    ReleasePrefetchRunner,
    parse_release_id,
)
from tests.factories import lesson_payload, page_payload, question_payload

BASE = "https://boost.test"
LOCALE = "sv-SE"


def test_parse_release_id_takes_the_leading_dot_segment() -> None:
    assert parse_release_id('"42.17.a9f3.sv-SE"') == "42"


def test_parse_release_id_handles_an_unquoted_etag() -> None:
    assert parse_release_id("42.17.a9f3.sv-SE") == "42"


def test_parse_release_id_returns_none_for_an_empty_etag() -> None:
    assert parse_release_id('""') is None


def _redis_cache() -> RedisCache:
    return RedisCache(
        FakeAsyncRedis(server=FakeServer()), hard_ttl_seconds=86_400, negative_ttl_seconds=30
    )


async def test_gate_claims_a_release_id_exactly_once() -> None:
    gate = ReleasePrefetchGate(_redis_cache())

    first = await gate.claim('"42.17.a9f3.sv-SE"')
    second = await gate.claim('"42.17.a9f3.sv-SE"')

    assert first == "42"
    assert second is None


async def test_gate_treats_different_releases_independently() -> None:
    gate = ReleasePrefetchGate(_redis_cache())

    first = await gate.claim('"42.17.a9f3.sv-SE"')
    other_release = await gate.claim('"43.1.a9f3.sv-SE"')

    assert first == "42"
    assert other_release == "43"


@respx.mock
async def test_runner_warms_every_current_lesson_and_question_across_locales() -> None:
    async with httpx.AsyncClient(base_url=BASE) as http:
        boost_client = BoostClient(http, token="svc-token", max_retries=0)
        redis_cache = _redis_cache()
        body_cache = BodyCache(boost_client, redis_cache, batch_max_refs=100)
        runner = ReleasePrefetchRunner(
            boost_client, body_cache, batch_max_refs=100, batch_delay_seconds=0
        )

        lessons_route = respx.get(f"{BASE}/v1/delivery/lessons").respond(
            json=page_payload([lesson_payload(lesson_id="10")], page_size=250)
        )
        lesson_revision_route = respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2").respond(
            json=lesson_payload(lesson_id="10")
        )
        questions_route = respx.get(f"{BASE}/v1/delivery/questions").respond(
            json=page_payload([question_payload(question_id="100")], page_size=250)
        )
        revisions_route = respx.get(f"{BASE}/v1/delivery/questions/revisions").respond(
            json={"items": [question_payload(question_id="100")], "missing": []}
        )

        await runner.run("42")

        # Once per supported locale (sv-SE, en-GB).
        assert lessons_route.call_count == 2
        assert lesson_revision_route.call_count == 2
        assert questions_route.call_count == 2
        assert revisions_route.call_count == 2


@respx.mock
async def test_runner_continues_past_a_failed_lesson_revision() -> None:
    async with httpx.AsyncClient(base_url=BASE) as http:
        boost_client = BoostClient(http, token="svc-token", max_retries=0)
        body_cache = BodyCache(boost_client, _redis_cache(), batch_max_refs=100)
        runner = ReleasePrefetchRunner(
            boost_client, body_cache, batch_max_refs=100, batch_delay_seconds=0
        )

        respx.get(f"{BASE}/v1/delivery/lessons").respond(
            json=page_payload([lesson_payload(lesson_id="10")], page_size=250)
        )
        respx.get(f"{BASE}/v1/delivery/lessons/10/revisions/2").respond(500)
        respx.get(f"{BASE}/v1/delivery/questions").respond(json=page_payload([], page_size=250))

        await runner.run("42")  # must not raise
