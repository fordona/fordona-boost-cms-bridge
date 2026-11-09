"""Mock exam browsing: list + preview (2026-11-07, read-only, no attempt/session tracking)."""

import respx

from fordona_connect.learning.errors import MockExamNotFoundError
from tests.conftest import BOOST, Harness
from tests.factories import question_payload


def _mock_exam_summary(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "mockExamId": "1",
        "name": "Exam A",
        "description": "Covers unit 1",
        "questionCount": 2,
        "complete": True,
    }
    payload.update(overrides)
    return payload


async def test_list_mock_exams_returns_the_backend_summaries(harness: Harness) -> None:
    harness.theory.set(
        "list_mock_exams",
        [_mock_exam_summary(), _mock_exam_summary(mockExamId="2", name="Exam B")],
    )

    response = await harness.client.get("/v1/mock-exams", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert [e["mockExamId"] for e in body] == ["1", "2"]
    assert body[0]["name"] == "Exam A"
    assert body[0]["questionCount"] == 2


@respx.mock
async def test_get_mock_exam_hydrates_each_question_from_boost(harness: Harness) -> None:
    harness.theory.set(
        "get_mock_exam",
        {**_mock_exam_summary(), "items": [{"questionId": "100", "version": "5"}]},
    )
    harness.boost.get(f"{BOOST}/v1/delivery/questions/100/revisions/5").respond(
        json=question_payload(question_id="100")
    )

    response = await harness.client.get("/v1/mock-exams/1", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["mockExamId"] == "1"
    assert len(body["questions"]) == 1
    [question] = body["questions"]
    assert question["prompt"][0]["markdown"] == "Vad betyder skylten?"
    assert [opt["key"] for opt in question["options"]] == ["a", "b", "c"]
    # Never leaks internal ids — same invariant as attempt items.
    assert "questionId" not in body["questions"][0]


async def test_get_mock_exam_unknown_id_is_404(harness: Harness) -> None:
    harness.theory.set("get_mock_exam", MockExamNotFoundError("Mock exam not found: 999"))

    response = await harness.client.get("/v1/mock-exams/999", headers=harness.auth())

    assert response.status_code == 404
    assert response.json()["errorCode"] == "THEORY_MOCK_EXAM_NOT_FOUND"
