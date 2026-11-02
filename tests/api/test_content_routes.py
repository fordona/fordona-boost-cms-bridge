"""Content routes end to end: auth, validation, mapping, locale, caching headers, errors."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

import httpx
import pytest

from boost_bridge.cache.keys import cache_key
from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.db.snapshot_repository import Snapshot
from tests.conftest import ASSETS, BOOST, Harness
from tests.factories import lesson_payload, page_payload, problem_payload

HarnessFactory = Callable[..., AbstractAsyncContextManager[Harness]]


# --- authentication ----------------------------------------------------------


async def test_missing_token_is_401_problem(harness: Harness) -> None:
    response = await harness.client.get("/v1/lessons")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert body["errorCode"] == "UNAUTHORIZED"
    assert body["correlationId"] == response.headers["X-Correlation-ID"]


async def test_expired_token_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/lessons", headers=harness.auth(exp=1))
    assert response.status_code == 401


async def test_non_bearer_scheme_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/lessons", headers={"Authorization": "Basic Zm9v"})
    assert response.status_code == 401


async def test_auth_disabled_locally_needs_no_token(harness_factory: HarnessFactory) -> None:
    async with harness_factory(auth_enabled=False) as h:
        h.boost.get(f"{BOOST}/v1/delivery/lessons").respond(json=page_payload([]))
        response = await h.client.get("/v1/lessons")
    assert response.status_code == 200


async def test_forward_mode_sends_the_learners_own_token(harness_factory: HarnessFactory) -> None:
    async with harness_factory(boost_auth_mode="forward_learner_token") as h:
        route = h.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())
        headers = h.auth()

        response = await h.client.get("/v1/lessons/10", headers=headers)

    assert response.status_code == 200
    assert route.calls.last.request.headers["Authorization"] == headers["Authorization"]


async def test_forward_mode_never_forwards_an_unverified_token(
    harness_factory: HarnessFactory,
) -> None:
    async with harness_factory(boost_auth_mode="forward_learner_token") as h:
        route = h.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

        response = await h.client.get("/v1/lessons/10", headers=h.auth(aud=["elsewhere"]))

    assert response.status_code == 401
    assert route.call_count == 0


# --- lessons -----------------------------------------------------------------


async def test_list_lessons_maps_the_page(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
        json=page_payload([lesson_payload("10"), lesson_payload("11")], total=7, page_size=2)
    )

    response = await harness.client.get(
        "/v1/lessons", params={"pageSize": 2, "locale": "en-GB"}, headers=harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert [lesson["id"] for lesson in body["items"]] == ["10", "11"]
    assert body["total"] == 7
    assert body["pageSize"] == 2
    assert body["items"][0] == {
        "id": "10",
        "version": "2",
        "locale": "sv-SE",
        "availableLocales": None,
        "moduleId": "1",
        "title": "Väjningsplikt",
        "slug": "vajningsplikt",
        "estimatedReadMinutes": 7,
        "updatedAt": None,
    }
    upstream = route.calls.last.request.url.params
    assert upstream["locale"] == "en-GB"
    assert upstream["pageSize"] == "2"
    assert route.calls.last.request.headers["Authorization"] == "Bearer svc-token"
    assert response.headers["Content-Language"] == "en-GB"
    assert "X-Content-Stale" not in response.headers


async def test_get_lesson_maps_content_and_hides_ai_summary(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["contentHtml"] == "<p>Lektionstext</p>"
    assert body["estimatedReadMinutes"] == 7
    assert body["resources"] == [
        {
            "type": "image",
            "url": f"{ASSETS}/c9f0f895-fb98-4b91-8f0e-3f6b1e2d4a55",
            "placement": "hero",
        }
    ]
    assert body["availableLocales"] is None  # absent upstream -> null, not []
    assert "aiContextSummary" not in body
    assert "INTERNAL" not in response.text


async def test_get_lesson_is_cached(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    for _ in range(3):
        response = await harness.client.get("/v1/lessons/10", headers=harness.auth())
        assert response.status_code == 200

    assert route.call_count == 1


async def test_lesson_not_found_is_404_problem(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/99").respond(404, json=problem_payload(404))

    response = await harness.client.get("/v1/lessons/99", headers=harness.auth())

    assert response.status_code == 404
    body = response.json()
    assert body["errorCode"] == "CONTENT_NOT_FOUND"
    assert body["instance"] == "/v1/lessons/99"


async def test_list_lessons_passes_filters(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(json=page_payload([]))

    response = await harness.client.get(
        "/v1/lessons",
        params={"moduleId": "3", "slug": "vajningsplikt", "page": 2},
        headers=harness.auth(),
    )

    assert response.status_code == 200
    params = route.calls.last.request.url.params
    assert (params["moduleId"], params["slug"], params["page"]) == ("3", "vajningsplikt", "2")


# --- validation --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/v1/lessons/abc", "/v1/lessons/0", "/v1/lessons/-1", "/v1/lessons/1.5"],
)
async def test_malformed_ids_are_422_and_never_reach_boost(harness: Harness, path: str) -> None:
    response = await harness.client.get(path, headers=harness.auth())

    assert response.status_code == 422
    assert response.json()["errorCode"] == "VALIDATION_FAILED"
    assert not [c for c in harness.boost.calls if c.request.url.host == "boost.test"]


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"pageSize": 0}, {"pageSize": 101}, {"page": "x"}],
)
async def test_bad_pagination_is_422(harness: Harness, params: dict[str, object]) -> None:
    response = await harness.client.get("/v1/lessons", params=params, headers=harness.auth())
    assert response.status_code == 422


async def test_unsupported_locale_is_422(harness: Harness) -> None:
    response = await harness.client.get(
        "/v1/lessons", params={"locale": "de-DE"}, headers=harness.auth()
    )
    assert response.status_code == 422
    assert response.json()["fieldErrors"][0]["field"] == "locale"


async def test_accept_language_selects_locale(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(
        json=lesson_payload(locale="en-GB")
    )

    response = await harness.client.get(
        "/v1/lessons/10", headers={**harness.auth(), "Accept-Language": "en-US,en;q=0.9"}
    )

    assert response.status_code == 200
    assert route.calls.last.request.url.params["locale"] == "en-GB"
    assert response.headers["Content-Language"] == "en-GB"


async def test_default_locale_is_swedish(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())
    await harness.client.get("/v1/lessons/10", headers=harness.auth())
    assert route.calls.last.request.url.params["locale"] == "sv-SE"


# --- upstream failures -------------------------------------------------------


async def test_boost_down_without_snapshot_is_503(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(503)

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 503
    assert response.json()["errorCode"] == "UPSTREAM_UNAVAILABLE"
    assert response.headers["Retry-After"] == "5"


async def test_boost_timeout_without_snapshot_is_504(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").mock(side_effect=httpx.ReadTimeout("slow"))

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 504
    assert response.json()["errorCode"] == "UPSTREAM_TIMEOUT"


async def test_boost_rejecting_our_token_is_502_not_401(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(401, json=problem_payload(401))

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 502
    assert response.json()["errorCode"] == "UPSTREAM_MISCONFIGURED"
    assert "WWW-Authenticate" not in response.headers


async def test_boost_down_serves_snapshot_marked_stale(harness: Harness) -> None:
    key = cache_key(BoostRequests.lesson("10", "sv-SE"))
    harness.snapshots.rows[key] = Snapshot(payload=lesson_payload(), fetched_at=datetime.now(UTC))
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(503)

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["title"] == "Väjningsplikt"
    assert response.headers["X-Content-Stale"] == "true"


async def test_redis_down_still_serves(harness: Harness) -> None:
    harness.redis_server.connected = False
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    response = await harness.client.get("/v1/lessons/10", headers=harness.auth())

    assert response.status_code == 200


# --- cross-cutting -----------------------------------------------------------


async def test_correlation_id_round_trips_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons/10").respond(json=lesson_payload())

    response = await harness.client.get(
        "/v1/lessons/10", headers={**harness.auth(), "X-Correlation-ID": "fe-trace-7"}
    )

    assert response.headers["X-Correlation-ID"] == "fe-trace-7"
    assert route.calls.last.request.headers["X-Correlation-ID"] == "fe-trace-7"


async def test_cors_preflight_allows_configured_origin(harness: Harness) -> None:
    response = await harness.client.options(
        "/v1/lessons",
        headers={
            "Origin": "https://theory.fordona.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://theory.fordona.test"


async def test_openapi_documents_routes_and_security(harness: Harness) -> None:
    spec = (await harness.client.get("/openapi.json")).json()

    operation = spec["paths"]["/v1/lessons/{lessonId}"]["get"]
    assert operation["operationId"] == "get_lesson"
    assert operation["security"] == [{"KindeBearer": []}]
    assert "application/problem+json" in operation["responses"]["404"]["content"]


async def test_openapi_schemas_carry_no_answer_fields(harness: Harness) -> None:
    spec = (await harness.client.get("/openapi.json")).json()

    for schema in spec["components"]["schemas"].values():
        properties = schema.get("properties", {})
        assert "correctOptionId" not in properties
        assert "explanation" not in properties
