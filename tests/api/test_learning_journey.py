"""Route-level tests for the Personalized Learning Journey endpoints, through the
real app/auth/rate-limit stack with the DB-backed service swapped for
``FakeLearningJourneyRepository`` (no Docker needed — see ``tests/learning_journey/``
for the deeper service-level state-machine coverage this doesn't repeat).

Asserts the spec's own envelope/field-naming contract, which is deliberately
different from every other route in this BFF (see
``learning_journey/__init__.py``): snake_case fields, ``{"success": ..., "data"/
"error": ...}``, not RFC 7807.
"""

import uuid

import pytest

from boost_bridge.learning_journey.service import LearningJourneyService
from tests.conftest import Harness
from tests.learning_journey.fakes import FakeEngineClient, FakeLearningJourneyRepository

CHALLENGE = "ch_028"  # ms_008 — a paid milestone; a subscribed fake engine lets it through


@pytest.fixture
async def journey_harness(harness_factory):  # type: ignore[no-untyped-def]
    async with harness_factory() as harness:
        harness.app.state.services.learning_journey = LearningJourneyService(
            FakeLearningJourneyRepository(), FakeEngineClient(subscribed=True)
        )
        yield harness


async def test_get_learning_journey_returns_the_spec_envelope(
    journey_harness: Harness,
) -> None:
    response = await journey_harness.client.get(
        "/v1/learning-journey", headers=journey_harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["journey_id"] == "journey_001"
    assert len(body["data"]["milestones"]) == 10


async def test_get_learning_journey_without_token_is_401(journey_harness: Harness) -> None:
    response = await journey_harness.client.get("/v1/learning-journey")

    assert response.status_code == 401


async def test_get_milestone_requires_the_query_param(journey_harness: Harness) -> None:
    response = await journey_harness.client.get("/v1/milestones", headers=journey_harness.auth())

    assert response.status_code == 422


async def test_start_attempt_returns_201_with_frozen_questions(
    journey_harness: Harness,
) -> None:
    response = await journey_harness.client.post(
        "/v1/challenges/attempts",
        json={"challenge_id": CHALLENGE, "mode": "INITIAL"},
        headers={**journey_harness.auth(), "Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["question_count"] == 12
    assert len(body["data"]["questions"]) == 12


async def test_start_attempt_without_idempotency_key_is_422(journey_harness: Harness) -> None:
    response = await journey_harness.client.post(
        "/v1/challenges/attempts",
        json={"challenge_id": CHALLENGE, "mode": "INITIAL"},
        headers=journey_harness.auth(),
    )

    assert response.status_code == 422


async def test_start_attempt_on_content_not_ready_challenge_uses_the_error_envelope(
    journey_harness: Harness,
) -> None:
    response = await journey_harness.client.post(
        "/v1/challenges/attempts",
        json={"challenge_id": "ch_001", "mode": "INITIAL"},
        headers={**journey_harness.auth(), "Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CONTENT_NOT_READY"
    assert "request_id" in body["error"]


async def test_repeated_idempotency_key_replays_through_the_api(
    journey_harness: Harness,
) -> None:
    key = str(uuid.uuid4())
    payload = {"challenge_id": CHALLENGE, "mode": "INITIAL"}
    headers = {**journey_harness.auth(), "Idempotency-Key": key}

    first = await journey_harness.client.post(
        "/v1/challenges/attempts", json=payload, headers=headers
    )
    second = await journey_harness.client.post(
        "/v1/challenges/attempts", json=payload, headers=headers
    )

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


async def test_resume_attempt_then_answer_and_submit_full_flow(
    journey_harness: Harness,
) -> None:
    start = await journey_harness.client.post(
        "/v1/challenges/attempts",
        json={"challenge_id": CHALLENGE, "mode": "INITIAL"},
        headers={**journey_harness.auth(), "Idempotency-Key": str(uuid.uuid4())},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    questions = start.json()["data"]["questions"]

    resumed = await journey_harness.client.get(
        f"/v1/challenges/attempts/{attempt_id}", headers=journey_harness.auth()
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["answered_count"] == 0

    # Answer every question with option "A" (right or wrong doesn't matter here —
    # this test checks the HTTP contract, not scoring; test_service.py covers scoring).
    for question in questions:
        answer = await journey_harness.client.post(
            f"/v1/challenges/attempts/{attempt_id}/answers",
            json={"question_id": question["question_id"], "selected_option_keys": ["A"]},
            headers={**journey_harness.auth(), "Idempotency-Key": str(uuid.uuid4())},
        )
        assert answer.status_code == 200
        assert "is_correct" in answer.json()["data"]

    submit = await journey_harness.client.post(
        f"/v1/challenges/attempts/{attempt_id}/submit",
        json={},
        headers={**journey_harness.auth(), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert submit.status_code == 200
    assert submit.json()["data"]["status"] == "SUBMITTED"


async def test_list_attempts_history(journey_harness: Harness) -> None:
    response = await journey_harness.client.get(
        "/v1/challenges/attempts",
        params={"challenge_id": CHALLENGE},
        headers=journey_harness.auth(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "challenge_id": CHALLENGE,
        "items": [],
        "next_cursor": None,
    }


async def test_readiness_endpoint(journey_harness: Harness) -> None:
    response = await journey_harness.client.get(
        "/v1/learning-journey/readiness", headers=journey_harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["completed_challenges"] == 0
    assert body["data"]["best_mock_result"] is None


async def test_home_endpoint(journey_harness: Harness) -> None:
    response = await journey_harness.client.get(
        "/v1/learning-journey/home",
        headers={**journey_harness.auth(), "X-Timezone": "Europe/Stockholm"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]["week"]["days"]) == 7
    assert body["data"]["week"]["timezone"] == "Europe/Stockholm"
    assert "continue" in body["data"]  # the Python-keyword field serializes by its alias
    assert body["data"]["tabs"]["mock_exams"]["is_locked"] is True
