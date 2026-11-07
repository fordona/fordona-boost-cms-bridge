"""GET /v1/lessons/{lessonId} (Plan §7.3): no theory fetched for a locked lesson."""

import respx

from tests.conftest import BOOST, ENGINE, Harness
from tests.factories import engine_envelope, engine_problem, lesson_payload, lesson_state_payload


@respx.mock
async def test_locked_lesson_is_403_and_never_calls_boost(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/lessons/14").respond(
        json=engine_envelope(lesson_state_payload(locked=True, lockReason="THEORY_LESSON_LOCKED"))
    )

    response = await harness.client.get("/v1/lessons/14", headers=harness.auth())

    assert response.status_code == 403
    assert response.json()["errorCode"] == "THEORY_LESSON_LOCKED"
    assert not [c for c in harness.boost.calls if c.request.url.host == "boost.test"]


@respx.mock
async def test_module_locked_lesson_is_403_with_module_locked_code(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/lessons/21").respond(
        json=engine_envelope(
            lesson_state_payload(locked=True, lockReason="THEORY_ATTEMPT_MODULE_LOCKED")
        )
    )

    response = await harness.client.get("/v1/lessons/21", headers=harness.auth())

    assert response.status_code == 403
    assert response.json()["errorCode"] == "THEORY_ATTEMPT_MODULE_LOCKED"


@respx.mock
async def test_unlocked_lesson_renders_theory_blocks_from_boost(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/lessons/14").respond(
        json=engine_envelope(lesson_state_payload())
    )
    payload = lesson_payload(lesson_id="14")
    payload["translation"]["blocks"] = [{"type": "text", "markdown": "Welcome"}]
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/14").respond(json=payload)

    response = await harness.client.get("/v1/lessons/14", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["questionCount"] == 8
    assert body["theory"] == [{"type": "text", "markdown": "Welcome"}]
    assert body["title"] == "Väjningsplikt"


@respx.mock
async def test_unlocked_lesson_renders_theory_from_legacy_content_html(
    harness: Harness,
) -> None:
    """Confirmed 2026-11-06 against a live boost-api-dev.fordona.dev response: real
    Boost lessons never carry ``translation.blocks``, only legacy ``contentHtml`` —
    ``lesson_payload()``'s default shape (no ``blocks`` override) models exactly that.
    Before this fix, ``theory`` rendered as ``[]`` for every real lesson."""
    harness.engine.get(f"{ENGINE}/internal/theory/v1/lessons/14").respond(
        json=engine_envelope(lesson_state_payload())
    )
    harness.boost.get(f"{BOOST}/v1/delivery/lessons/14").respond(
        json=lesson_payload(lesson_id="14")
    )

    response = await harness.client.get("/v1/lessons/14", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["theory"] == [{"type": "text", "markdown": "Lektionstext"}]


@respx.mock
async def test_unknown_lesson_passes_through_engine_404(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/lessons/999").respond(
        404,
        json=engine_problem(
            status=404,
            error_code="THEORY_ATTEMPT_LESSON_NOT_FOUND",
            type_path="theory/lesson-not-found",
        ),
    )

    response = await harness.client.get("/v1/lessons/999", headers=harness.auth())

    assert response.status_code == 404
    assert response.json()["errorCode"] == "THEORY_ATTEMPT_LESSON_NOT_FOUND"
