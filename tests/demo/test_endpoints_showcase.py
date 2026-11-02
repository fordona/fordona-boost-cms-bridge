"""Demo suite: one test per route the bridge serves.

This is NOT a replacement for tests/api/test_content_routes.py, which already
covers these routes in depth (locale, pagination, caching, error handling,
...). This file exists to be read top to bottom in a terminal during a
walkthrough: one test = one real endpoint, each one proving two things at once:

1. the bridge returns 200 with a correctly *mapped* body (not a passthrough
   stub — the assertions check real field values built by the mapper), and
2. the bridge actually made the matching call to Boost's delivery API
   (`harness.boost` is a mocked Boost server; `route.calls` proves the bridge
   reached it, and the asserted request path/params prove it reached the
   *right* operation).

The question and module catalogue routes were retired (plan §15, R-11); see
tests/api/test_retired_routes.py.

Run just this file for the walkthrough:

    uv run pytest tests/demo/test_endpoints_showcase.py -v
"""

from datetime import UTC, datetime

from boost_bridge.cache.keys import cache_key
from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.db.snapshot_repository import Snapshot
from tests.conftest import BOOST, Harness
from tests.factories import lesson_payload, page_payload

# --- 1. GET /v1/lessons --------------------------------------------------------


async def test_endpoint_01_list_lessons_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
        json=page_payload([lesson_payload()])
    )

    response = await harness.client.get(
        "/v1/lessons", params={"moduleId": "1"}, headers=harness.auth()
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["slug"] == "vajningsplikt"
    assert route.call_count == 1


# --- 2. GET /v1/lessons/{lessonId} ---------------------------------------------


async def test_endpoint_02_get_lesson_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["contentHtml"] == "<p>Lektionstext</p>"
    assert "aiContextSummary" not in body  # internal field correctly hidden
    assert route.call_count == 1


# --- 3 & 4. GET /health/live and /health/ready ----------------------------------


async def test_endpoint_03_health_live_needs_no_boost_or_auth(harness: Harness) -> None:
    response = await harness.client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_endpoint_04_health_ready_checks_db_and_redis(harness: Harness) -> None:
    response = await harness.client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["components"]) == {"database", "redis"}


# --- bonus: resilience, in one glance ------------------------------------------


async def test_endpoint_05_bridge_keeps_serving_when_boost_is_down(harness: Harness) -> None:
    """The single most convincing demo: the bridge has a last-known-good copy
    and keeps answering even while Boost itself is returning 503."""
    key = cache_key(BoostRequests.lesson("10", "sv-SE"))
    snapshot = Snapshot(payload=lesson_payload("10"), fetched_at=datetime.now(UTC))
    harness.snapshots.rows[key] = snapshot
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(503)

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200  # learner still gets an answer
    assert response.headers["X-Content-Stale"] == "true"  # ...honestly labelled stale
