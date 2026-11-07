"""Attempt start/resume, answer, phase completion (Plan §7.3).

Also the security-invariant tests the tracker calls for explicitly: no public
response ever contains a question id, revision, correctOptionKey before an
answer, or a template id.
"""

from typing import Any

import respx

from tests.conftest import BOOST, ENGINE, Harness
from tests.factories import (
    answer_feedback_payload,
    attempt_item_ref_payload,
    attempt_payload,
    engine_envelope,
    phase_completion_payload,
    question_payload,
)

ATTEMPT_ID = "22222222-2222-2222-2222-222222222222"

_LEAKY_KEYS = {"questionId", "version", "correctOptionKey", "templateId"}


def _assert_no_leaked_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in _LEAKY_KEYS, f"leaked key: {key}"
            _assert_no_leaked_keys(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_leaked_keys(item)


@respx.mock
async def test_start_attempt_hydrates_items_with_labelled_options_and_no_leaks(
    harness: Harness,
) -> None:
    harness.engine.post(f"{ENGINE}/internal/theory/v1/lessons/12/attempts").respond(
        json=engine_envelope(
            attempt_payload(
                items=[
                    attempt_item_ref_payload(seq=1, question_id="100", option_order=["b", "a", "c"])
                ]
            )
        )
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/5").respond(
        json=question_payload(question_id="100")
    )

    response = await harness.client.post(
        "/v1/lessons/12/attempts",
        json={"requestId": "33333333-3333-3333-3333-333333333333"},
        headers=harness.auth(),
    )

    assert response.status_code == 200  # deliberate decision: see theory_attempts.py docstring
    body = response.json()
    assert body["lessonId"] == "12"
    assert body["questionCount"] == 1
    [item] = body["items"]
    assert [opt["key"] for opt in item["options"]] == ["b", "a", "c"]
    assert [opt["label"] for opt in item["options"]] == ["A", "B", "C"]
    assert item["answered"] is False
    assert body["retry"] is None
    _assert_no_leaked_keys(body)


@respx.mock
async def test_get_attempt_splits_lesson_and_retry_items_by_phase(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/attempts/{ATTEMPT_ID}").respond(
        json=engine_envelope(
            attempt_payload(
                status="IN_RETRY",
                items=[
                    attempt_item_ref_payload(seq=1, question_id="100", answered=True),
                    attempt_item_ref_payload(
                        seq=9, phase="RETRY", question_id="200", answered=None
                    ),
                ],
            )
        )
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/5").respond(
        json=question_payload(question_id="100")
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/200/revisions/5").respond(
        json=question_payload(question_id="200")
    )

    response = await harness.client.get(f"/v1/attempts/{ATTEMPT_ID}", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["lessonId"] is None
    assert len(body["items"]) == 1
    assert body["items"][0]["answered"] is True
    assert body["retry"]["total"] == 1
    assert len(body["retry"]["items"]) == 1
    _assert_no_leaked_keys(body)


@respx.mock
async def test_answer_resolves_correct_option_content_from_cached_body(harness: Harness) -> None:
    # Seed the attempt-ref mapping the way start_attempt would.
    harness.engine.post(f"{ENGINE}/internal/theory/v1/lessons/12/attempts").respond(
        json=engine_envelope(
            attempt_payload(items=[attempt_item_ref_payload(seq=1, question_id="100")])
        )
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/5").respond(
        json=question_payload(question_id="100")
    )
    await harness.client.post(
        "/v1/lessons/12/attempts",
        json={"requestId": "33333333-3333-3333-3333-333333333333"},
        headers=harness.auth(),
    )

    harness.engine.post(f"{ENGINE}/internal/theory/v1/attempts/{ATTEMPT_ID}/responses").respond(
        json=engine_envelope(answer_feedback_payload(correctOptionKey="b", correctOptionLabel="A"))
    )

    response = await harness.client.post(
        f"/v1/attempts/{ATTEMPT_ID}/responses",
        json={
            "responseId": "44444444-4444-4444-4444-444444444444",
            "seq": 1,
            "selectedOptionKey": "a",
            "durationMs": 1200,
        },
        headers=harness.auth(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["correctOption"]["key"] == "b"
    assert body["correctOption"]["label"] == "A"
    assert body["correctOption"]["content"][0]["markdown"] == "Väjningsplikt"
    assert body["explanation"][0]["type"] == "text"
    _assert_no_leaked_keys(body)


@respx.mock
async def test_answer_renders_explanation_from_a_real_boost_html_string(
    harness: Harness,
) -> None:
    """Confirmed 2026-11-06: the engine forwards whatever raw shape Boost sent for
    ``explanation`` verbatim, and real Boost sends a plain HTML string, never a block
    list (the stub's synthetic data is block-list-shaped, which is why this went
    unnoticed until tested against real content). Before this fix, this response
    would 500 — ``EngineAnswerFeedback.explanation: list[Any]`` raised
    ``ValidationError`` on a ``str``."""
    harness.engine.post(f"{ENGINE}/internal/theory/v1/lessons/12/attempts").respond(
        json=engine_envelope(
            attempt_payload(items=[attempt_item_ref_payload(seq=1, question_id="100")])
        )
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/5").respond(
        json=question_payload(question_id="100")
    )
    await harness.client.post(
        "/v1/lessons/12/attempts",
        json={"requestId": "33333333-3333-3333-3333-333333333333"},
        headers=harness.auth(),
    )

    harness.engine.post(f"{ENGINE}/internal/theory/v1/attempts/{ATTEMPT_ID}/responses").respond(
        json=engine_envelope(
            answer_feedback_payload(
                explanation="<p>At a junction without signs, yield to traffic from the right.</p>"
            )
        )
    )

    response = await harness.client.post(
        f"/v1/attempts/{ATTEMPT_ID}/responses",
        json={
            "responseId": "44444444-4444-4444-4444-444444444444",
            "seq": 1,
            "selectedOptionKey": "a",
            "durationMs": 1200,
        },
        headers=harness.auth(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] == [
        {
            "type": "text",
            "markdown": "At a junction without signs, yield to traffic from the right.",
        }
    ]
    _assert_no_leaked_keys(body)


@respx.mock
async def test_complete_lesson_phase_hydrates_retry_items(harness: Harness) -> None:
    harness.engine.post(
        f"{ENGINE}/internal/theory/v1/attempts/{ATTEMPT_ID}/phases/lesson/complete"
    ).respond(json=engine_envelope(phase_completion_payload()))
    harness.boost.get(f"{BOOST}/v1/delivery/questions/200/revisions/5").respond(
        json=question_payload(question_id="200")
    )

    response = await harness.client.post(
        f"/v1/attempts/{ATTEMPT_ID}/phases/lesson/complete", headers=harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_RETRY"
    assert body["lessonSummary"] == {"total": 8, "correct": 6, "wrong": 2}
    assert body["retry"]["total"] == 2
    assert len(body["retry"]["items"]) == 1
    _assert_no_leaked_keys(body)


@respx.mock
async def test_complete_retry_phase_passes_through_next_and_progress(harness: Harness) -> None:
    harness.engine.post(
        f"{ENGINE}/internal/theory/v1/attempts/{ATTEMPT_ID}/phases/retry/complete"
    ).respond(
        json=engine_envelope(
            phase_completion_payload(
                status="COMPLETED",
                retrySummary={"total": 2, "correct": 1, "wrong": 1},
                retry=None,
                next={
                    "kind": "lesson",
                    "lessonId": "13",
                    "displayIndex": "1.3",
                    "title": "Road Signs",
                    "status": "CURRENT",
                    "action": "START",
                },
                progress={
                    "streak": {"current": 6, "longest": 9, "extendedToday": True},
                    "dailyChallenge": {"target": 3, "progress": 2, "completed": False},
                    "readiness": {"percent": 17},
                    "learningPathEtag": '"42.18.a9f3.sv-SE"',
                },
            )
        )
    )

    response = await harness.client.post(
        f"/v1/attempts/{ATTEMPT_ID}/phases/retry/complete", headers=harness.auth()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["next"]["lessonId"] == "13"
    assert body["progress"]["learningPathEtag"] == '"42.18.a9f3.sv-SE"'
    assert "retry" not in body
    _assert_no_leaked_keys(body)
