"""Platform facts from fordona-engine: learner context and the event outbox (Postgres + respx)."""

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis, FakeServer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.learning.platform import (
    PlatformClient,
    PlatformEventConsumer,
    PlatformEventCursor,
)
from fordona_connect.learning.progress.models import LearnerSummary

pytestmark = pytest.mark.integration

ENGINE = "https://engine.test"


def payload(data: object) -> dict[str, object]:
    return {"code": 200, "status": "OK", "response": data}


async def test_learner_context_is_cached_and_fails_closed() -> None:
    redis = FakeAsyncRedis(server=FakeServer())
    async with httpx.AsyncClient(base_url=ENGINE) as http:
        platform = PlatformClient(
            EngineClient(http, internal_token="t", default_timeout=1.0), redis, ttl_seconds=60
        )
        with respx.mock(assert_all_called=False) as router:
            route = router.get(f"{ENGINE}/internal/learning/v1/learners/kp_1").respond(
                json=payload({"userId": 1, "firstName": "A", "lastName": "B", "subscribed": True})
            )
            router.get(f"{ENGINE}/internal/learning/v1/learners/kp_2").respond(503)

            assert await platform.is_subscribed("kp_1") is True
            assert (await platform.profile("kp_1")).first_name == "A"
            assert route.call_count == 1  # the second read came from the cache
            assert route.calls[0].request.headers["X-Fordona-Internal-Token"] == "t"
            assert "Authorization" not in route.calls[0].request.headers
            # Unreachable engine, nothing cached: not subscribed.
            assert await platform.is_subscribed("kp_2") is False

            await platform.forget("kp_1")
            await platform.is_subscribed("kp_1")
            assert route.call_count == 2


async def test_events_clear_caches_delete_learners_and_advance_the_cursor(
    learning_engine: AsyncEngine,
) -> None:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        learning_engine, expire_on_commit=False
    )
    async with sessions() as session, session.begin():
        session.add(
            LearnerSummary(
                learner_id="kp_gone",
                timezone="Europe/Stockholm",
                progress_version=1,
                completed_lessons=0,
                sum_best_accuracy=0,
                current_streak=0,
                longest_streak=0,
            )
        )
        await session.execute(
            PlatformEventCursor.__table__.delete()  # type: ignore[attr-defined]
        )
    redis = FakeAsyncRedis(server=FakeServer())
    await redis.set("connect:learner:kp_sub", "{}")
    events = [
        {"id": 11, "type": "subscription.changed", "kindeSubject": "kp_sub"},
        {"id": 12, "type": "user.deleted", "kindeSubject": "kp_gone"},
        {"id": 13, "type": "something.else", "kindeSubject": "kp_x"},
    ]
    async with httpx.AsyncClient(base_url=ENGINE) as http:
        engine = EngineClient(http, internal_token="t", default_timeout=1.0)
        consumer = PlatformEventConsumer(engine, sessions, PlatformClient(engine, redis))
        with respx.mock(assert_all_called=False) as router:
            route = router.get(f"{ENGINE}/internal/learning/v1/events").mock(
                side_effect=lambda request: httpx.Response(
                    200,
                    json=payload(
                        {
                            "events": [
                                e for e in events if e["id"] > int(request.url.params["after"])
                            ]
                        }
                    ),
                )
            )
            assert await consumer.consume_once() == 3
            assert await consumer.consume_once() == 0
            assert route.calls[1].request.url.params["after"] == "13"

    assert await redis.get("connect:learner:kp_sub") is None
    async with sessions() as session:
        assert await session.get(LearnerSummary, "kp_gone") is None
        cursor = await session.get(PlatformEventCursor, 1)
    assert cursor is not None
    assert cursor.last_event_id == 13
