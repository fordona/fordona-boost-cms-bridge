"""Content routes end to end: auth, validation, mapping, locale, caching headers, errors."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

import httpx
import pytest

from boost_bridge.cache.keys import cache_key
from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.core.security import Learner
from boost_bridge.db.snapshot_repository import Snapshot
from boost_bridge.schemas.questions import Question
from boost_bridge.services.sequencing import SequencingContext
from tests.conftest import ASSETS, BOOST, ITEM_ASSETS, Harness
from tests.factories import (
    lesson_payload,
    module_payload,
    page_payload,
    problem_payload,
    question_payload,
)

HarnessFactory = Callable[..., AbstractAsyncContextManager[Harness]]


# --- authentication ----------------------------------------------------------


async def test_missing_token_is_401_problem(harness: Harness) -> None:
    response = await harness.client.get("/v1/modules")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert body["errorCode"] == "UNAUTHORIZED"
    assert body["correlationId"] == response.headers["X-Correlation-ID"]


async def test_expired_token_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/modules", headers=harness.auth(exp=1))
    assert response.status_code == 401


async def test_non_bearer_scheme_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/modules", headers={"Authorization": "Basic Zm9v"})
    assert response.status_code == 401


async def test_auth_disabled_locally_needs_no_token(harness_factory: HarnessFactory) -> None:
    async with harness_factory(auth_enabled=False) as h:
        h.boost.get(f"{BOOST}/v1/delivery/modules").respond(json=page_payload([]))
        response = await h.client.get("/v1/modules")
    assert response.status_code == 200


async def test_forward_mode_sends_the_learners_own_token(harness_factory: HarnessFactory) -> None:
    async with harness_factory(boost_auth_mode="forward_learner_token") as h:
        route = h.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())
        headers = h.auth()

        response = await h.client.get("/v1/modules/1", headers=headers)

    assert response.status_code == 200
    assert route.calls.last.request.headers["Authorization"] == headers["Authorization"]


async def test_forward_mode_never_forwards_an_unverified_token(
    harness_factory: HarnessFactory,
) -> None:
    async with harness_factory(boost_auth_mode="forward_learner_token") as h:
        route = h.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())

        response = await h.client.get("/v1/modules/1", headers=h.auth(aud=["elsewhere"]))

    assert response.status_code == 401
    assert route.call_count == 0


# --- modules -----------------------------------------------------------------


async def test_list_modules(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules").respond(
        json=page_payload([module_payload("1"), module_payload("2")], total=7, page_size=2)
    )

    response = await harness.client.get(
        "/v1/modules", params={"pageSize": 2, "locale": "en-GB"}, headers=harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert [m["id"] for m in body["items"]] == ["1", "2"]
    assert body["total"] == 7
    assert body["pageSize"] == 2
    assert body["items"][0] == {
        "id": "1",
        "version": "3",
        "locale": "sv-SE",
        "availableLocales": ["sv-SE", "en-GB"],
        "title": "Trafikregler",
        "slug": "trafikregler",
        "description": "Grundläggande trafikregler",
        "iconUrl": f"{ITEM_ASSETS}/8f14e45f-ceea-467a-9575-2a9d1f0e0b11",  # item assetBaseUrl wins
        "coverImageUrl": None,
        "updatedAt": "2026-10-01T10:00:00Z",
    }
    upstream = route.calls.last.request.url.params
    assert upstream["locale"] == "en-GB"
    assert upstream["pageSize"] == "2"
    assert route.calls.last.request.headers["Authorization"] == "Bearer svc-token"
    assert response.headers["Content-Language"] == "en-GB"
    assert "X-Content-Stale" not in response.headers


async def test_get_module_is_cached(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())

    for _ in range(3):
        response = await harness.client.get("/v1/modules/1", headers=harness.auth())
        assert response.status_code == 200

    assert route.call_count == 1


async def test_module_not_found_is_404_problem(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/modules/99").respond(404, json=problem_payload(404))

    response = await harness.client.get("/v1/modules/99", headers=harness.auth())

    assert response.status_code == 404
    body = response.json()
    assert body["errorCode"] == "CONTENT_NOT_FOUND"
    assert body["instance"] == "/v1/modules/99"


async def test_module_lessons_filters_by_module(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
        json=page_payload([lesson_payload()])
    )

    response = await harness.client.get("/v1/modules/1/lessons", headers=harness.auth())

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["moduleId"] == "1"
    assert "contentHtml" not in item  # summaries stay light
    assert route.calls.last.request.url.params["moduleId"] == "1"


# --- lessons -----------------------------------------------------------------


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


# --- questions: the answer-leak guard -------------------------------------------


async def test_question_never_contains_answers(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100").respond(json=question_payload())

    response = await harness.client.get("/v1/questions/100", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["questionText"] == "Vad betyder skylten?"
    assert [o["id"] for o in body["options"]] == ["a", "b", "c"]
    assert body["media"] == {
        "type": "image",
        "url": f"{ASSETS}/45c48cce-2e2d-4fbd-9d3e-1a2b3c4d5e6f",
    }
    for leaked in ("correctOptionId", "correct_option_id", "explanation", "SECRET"):
        assert leaked not in response.text


async def test_question_list_never_contains_answers(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
        json=page_payload([question_payload("100"), question_payload("101")])
    )

    response = await harness.client.get("/v1/questions", headers=harness.auth())

    assert response.status_code == 200
    assert "correctOptionId" not in response.text
    assert "SECRET" not in response.text


async def test_question_ids_batch_lookup(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(json=page_payload([]))

    response = await harness.client.get(
        "/v1/questions", params={"ids": "101, 100"}, headers=harness.auth()
    )

    assert response.status_code == 200
    assert route.calls.last.request.url.params["id"] == "100,101"


@pytest.mark.parametrize("ids", ["", "abc", "1,0", ",".join(str(i) for i in range(1, 102))])
async def test_invalid_ids_are_422(harness: Harness, ids: str) -> None:
    response = await harness.client.get(
        "/v1/questions", params={"ids": ids}, headers=harness.auth()
    )
    assert response.status_code == 422
    assert response.json()["fieldErrors"][0]["field"] == "ids"


async def test_question_revision(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/4").respond(
        json=question_payload()
    )

    response = await harness.client.get("/v1/questions/100/revisions/4", headers=harness.auth())

    assert response.status_code == 200
    assert "SECRET" not in response.text
    assert route.call_count == 1


# --- lesson questions + sequencer extension point ------------------------------


async def test_lesson_questions_collects_every_page(harness: Harness) -> None:
    first = [question_payload(str(i)) for i in range(100, 350)]
    second = [question_payload(str(i)) for i in range(350, 380)]
    route = harness.boost.get(f"{BOOST}/v1/delivery/questions")
    route.side_effect = lambda request: httpx.Response(
        200,
        json=page_payload(
            first if request.url.params["page"] == "1" else second,
            total=280,
            page=int(request.url.params["page"]),
            page_size=250,
        ),
    )

    response = await harness.client.get("/v1/lessons/10/questions", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["lessonId"] == "10"
    assert body["total"] == 280
    assert len(body["items"]) == 280
    assert route.call_count == 2
    assert all(c.request.url.params["lessonId"] == "10" for c in route.calls)
    assert all(c.request.url.params["pageSize"] == "250" for c in route.calls)


class ReversingSequencer:
    """Stands in for the future recommendation engine."""

    def __init__(self) -> None:
        self.seen: list[tuple[Learner, SequencingContext]] = []

    async def sequence(
        self, learner: Learner, questions: list[Question], context: SequencingContext
    ) -> list[Question]:
        self.seen.append((learner, context))
        foreign = questions[0].model_copy(update={"id": "999999"})
        return [*reversed(questions), foreign]  # the foreign one must be dropped


@pytest.mark.parametrize("sequencer", [ReversingSequencer()], ids=["reversing"])
async def test_sequencer_extension_point(harness: Harness, sequencer: ReversingSequencer) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
        json=page_payload([question_payload("100"), question_payload("101")], page_size=100)
    )

    response = await harness.client.get(
        "/v1/lessons/10/questions", params={"locale": "en-GB"}, headers=harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert [q["id"] for q in body["items"]] == ["101", "100"]  # reordered...
    assert body["total"] == 2  # ...and the injected foreign question was dropped
    learner, context = sequencer.seen[-1]
    assert learner.sub == "kp_learner123"
    assert context == SequencingContext(surface="lesson", locale="en-GB", lesson_id="10")


async def test_lesson_questions_without_any_questions(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
        json=page_payload([], total=0, page_size=100)
    )

    response = await harness.client.get("/v1/lessons/10/questions", headers=harness.auth())

    assert response.status_code == 200
    assert response.json() == {"lessonId": "10", "items": [], "total": 0}


# --- validation --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/v1/modules/abc", "/v1/modules/0", "/v1/lessons/-1", "/v1/questions/1.5"],
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
    response = await harness.client.get("/v1/modules", params=params, headers=harness.auth())
    assert response.status_code == 422


async def test_unsupported_locale_is_422(harness: Harness) -> None:
    response = await harness.client.get(
        "/v1/modules", params={"locale": "de-DE"}, headers=harness.auth()
    )
    assert response.status_code == 422
    assert response.json()["fieldErrors"][0]["field"] == "locale"


async def test_accept_language_selects_locale(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(
        json=module_payload(locale="en-GB")
    )

    response = await harness.client.get(
        "/v1/modules/1", headers={**harness.auth(), "Accept-Language": "en-US,en;q=0.9"}
    )

    assert response.status_code == 200
    assert route.calls.last.request.url.params["locale"] == "en-GB"
    assert response.headers["Content-Language"] == "en-GB"


async def test_default_locale_is_swedish(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())
    await harness.client.get("/v1/modules/1", headers=harness.auth())
    assert route.calls.last.request.url.params["locale"] == "sv-SE"


# --- upstream failures -------------------------------------------------------


async def test_boost_down_without_snapshot_is_503(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(503)

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 503
    assert response.json()["errorCode"] == "UPSTREAM_UNAVAILABLE"
    assert response.headers["Retry-After"] == "5"


async def test_boost_timeout_without_snapshot_is_504(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").mock(side_effect=httpx.ReadTimeout("slow"))

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 504
    assert response.json()["errorCode"] == "UPSTREAM_TIMEOUT"


async def test_boost_rejecting_our_token_is_502_not_401(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(401, json=problem_payload(401))

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 502
    assert response.json()["errorCode"] == "UPSTREAM_MISCONFIGURED"
    assert "WWW-Authenticate" not in response.headers


async def test_boost_down_serves_snapshot_marked_stale(harness: Harness) -> None:
    key = cache_key(BoostRequests.module("1", "sv-SE"))
    harness.snapshots.rows[key] = Snapshot(payload=module_payload(), fetched_at=datetime.now(UTC))
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(503)

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["title"] == "Trafikregler"
    assert response.headers["X-Content-Stale"] == "true"


async def test_redis_down_still_serves(harness: Harness) -> None:
    harness.redis_server.connected = False
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 200


# --- cross-cutting -----------------------------------------------------------


async def test_correlation_id_round_trips_to_boost(harness: Harness) -> None:
    route = harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload())

    response = await harness.client.get(
        "/v1/modules/1", headers={**harness.auth(), "X-Correlation-ID": "fe-trace-7"}
    )

    assert response.headers["X-Correlation-ID"] == "fe-trace-7"
    assert route.calls.last.request.headers["X-Correlation-ID"] == "fe-trace-7"


async def test_cors_preflight_allows_configured_origin(harness: Harness) -> None:
    response = await harness.client.options(
        "/v1/modules",
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

    operation = spec["paths"]["/v1/questions/{questionId}"]["get"]
    assert operation["operationId"] == "get_question"
    assert operation["security"] == [{"KindeBearer": []}]
    assert "application/problem+json" in operation["responses"]["404"]["content"]
    question_schema = spec["components"]["schemas"]["Question"]["properties"]
    assert "correctOptionId" not in question_schema
    assert "explanation" not in question_schema
