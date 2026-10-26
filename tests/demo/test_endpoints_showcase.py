"""Demo suite: one test per route in docs/design.md's API contract table.

This is NOT a replacement for tests/api/test_content_routes.py, which already
covers these routes in depth (locale, pagination, caching, error handling,
the sequencer extension point, ...). This file exists to be read top to bottom
in a terminal during a walkthrough: one test = one real endpoint, printed in
the same order as the design doc, each one proving two things at once:

1. the bridge returns 200 with a correctly *mapped* body (not a passthrough
   stub — the assertions check real field values built by the mapper), and
2. the bridge actually made the matching call to Boost's delivery API
   (`harness.boost` is a mocked Boost server; `route.calls` proves the bridge
   reached it, and the asserted request path/params prove it reached the
   *right* operation).

Run just this file for the walkthrough:

    uv run pytest tests/demo/test_endpoints_showcase.py -v
"""

from datetime import UTC, datetime

from boost_bridge.cache.keys import cache_key
from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.db.snapshot_repository import Snapshot
from tests.conftest import BOOST, Harness
from tests.factories import lesson_payload, module_payload, page_payload, question_payload

# --- 1. GET /v1/modules -------------------------------------------------------


async def test_endpoint_01_list_modules_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules").respond(
        json=page_payload([module_payload("1"), module_payload("2")], total=2)
    )

    response = await harness.client.get("/v1/modules", headers=harness.auth())

    assert response.status_code == 200
    assert [m["id"] for m in response.json()["items"]] == ["1", "2"]
    assert route.call_count == 1
    assert route.calls.last.request.url.path == "/v1/delivery/modules"


# --- 2. GET /v1/modules/{moduleId} --------------------------------------------


async def test_endpoint_02_get_module_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload("1"))

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["title"] == "Trafikregler"
    assert route.call_count == 1


# --- 3. GET /v1/modules/{moduleId}/lessons ------------------------------------


async def test_endpoint_03_list_module_lessons_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
        json=page_payload([lesson_payload(lesson_id="10", module_id="1")])
    )

    response = await harness.client.get("/v1/modules/1/lessons", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["items"][0]["moduleId"] == "1"
    assert route.calls.last.request.url.params["moduleId"] == "1"


# --- 4. GET /v1/lessons --------------------------------------------------------


async def test_endpoint_04_list_lessons_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
        json=page_payload([lesson_payload()])
    )

    response = await harness.client.get(
        "/v1/lessons", params={"moduleId": "1"}, headers=harness.auth()
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["slug"] == "vajningsplikt"
    assert route.call_count == 1


# --- 5. GET /v1/lessons/{lessonId} ---------------------------------------------


async def test_endpoint_05_get_lesson_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["contentHtml"] == "<p>Lektionstext</p>"
    assert "aiContextSummary" not in body  # internal field correctly hidden
    assert route.call_count == 1


# --- 6. GET /v1/lessons/{lessonId}/questions -----------------------------------


async def test_endpoint_06_list_lesson_questions_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
        json=page_payload([question_payload("100"), question_payload("101")], page_size=100)
    )

    response = await harness.client.get("/v1/lessons/10/questions", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["lessonId"] == "10"
    assert body["total"] == 2
    assert route.calls.last.request.url.params["lessonId"] == "10"


# --- 7. GET /v1/questions -------------------------------------------------------


async def test_endpoint_07_list_questions_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
        json=page_payload([question_payload("100")])
    )

    response = await harness.client.get("/v1/questions", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "100"
    assert route.call_count == 1


# --- 8. GET /v1/questions/{questionId} ------------------------------------------


async def test_endpoint_08_get_question_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions/100").respond(
        json=question_payload()
    )

    response = await harness.client.get("/v1/questions/100", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["questionText"] == "Vad betyder skylten?"
    # Answer-leak guard: the upstream payload has correctOptionId/explanation,
    # the bridge's response must never expose them.
    assert "correctOptionId" not in response.text
    assert "SECRET" not in response.text
    assert route.call_count == 1


# --- 9. GET /v1/questions/{questionId}/revisions/{version} ---------------------


async def test_endpoint_09_get_question_revision_talks_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/4").respond(
        json=question_payload()
    )

    response = await harness.client.get("/v1/questions/100/revisions/4", headers=harness.auth())

    assert response.status_code == 200
    assert "SECRET" not in response.text
    assert route.call_count == 1


# --- 10 & 11. GET /health/live and /health/ready --------------------------------


async def test_endpoint_10_health_live_needs_no_boost_or_auth(harness: Harness) -> None:
    response = await harness.client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_endpoint_11_health_ready_checks_db_and_redis(harness: Harness) -> None:
    response = await harness.client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["components"]) == {"database", "redis"}


# --- bonus: resilience, in one glance ------------------------------------------


async def test_endpoint_12_bridge_keeps_serving_when_boost_is_down(harness: Harness) -> None:
    """Not in the design doc's table, but the single most convincing demo:
    the bridge has a last-known-good copy and keeps answering even while
    Boost itself is returning 503."""
    key = cache_key(BoostRequests.module("1", "sv-SE"))
    snapshot = Snapshot(payload=module_payload("1"), fetched_at=datetime.now(UTC))
    harness.snapshots.rows[key] = snapshot
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(503)

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 200  # learner still gets an answer
    assert response.headers["X-Content-Stale"] == "true"  # ...honestly labelled stale
