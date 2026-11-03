"""Boost payload builders shaped like the (inferred) delivery responses."""

from typing import Any


def module_payload(
    module_id: str = "1", locale: str = "sv-SE", **translation: Any
) -> dict[str, Any]:
    return {
        "id": module_id,
        "version": "3",
        "locale": locale,
        "availableLocales": ["sv-SE", "en-GB"],
        "updatedAt": "2026-10-01T10:00:00Z",
        "assetBaseUrl": "https://assets.boost.test/a/",
        "shared": {
            "iconId": "8f14e45f-ceea-467a-9575-2a9d1f0e0b11",
            "coverImageId": None,
        },
        "translation": {
            "title": "Trafikregler",
            "slug": "trafikregler",
            "description": "Grundläggande trafikregler",
            **translation,
        },
        "resources": [],
    }


def lesson_payload(
    lesson_id: str = "10", module_id: str = "1", locale: str = "sv-SE"
) -> dict[str, Any]:
    return {
        "id": lesson_id,
        "version": "2",
        "locale": locale,
        "shared": {
            "moduleId": module_id,
            "estimatedReadMinutes": 7,
            "aiContextSummary": "INTERNAL: summary for the AI engine",
        },
        "translation": {
            "title": "Väjningsplikt",
            "slug": "vajningsplikt",
            "contentHtml": "<p>Lektionstext</p>",
        },
        "resources": [
            {
                "fileId": "c9f0f895-fb98-4b91-8f0e-3f6b1e2d4a55",
                "type": "image",
                "placement": "hero",
            }
        ],
    }


def question_payload(
    question_id: str = "100", lesson_id: str = "10", locale: str = "sv-SE"
) -> dict[str, Any]:
    return {
        "id": question_id,
        "version": "5",
        "locale": locale,
        "availableLocales": ["sv-SE", "en-GB"],
        "shared": {
            "type": "mcq",
            "lessonId": lesson_id,
            "subjectId": "4",
            "difficulty": 2,
            "points": 1,
            "mediaId": "45c48cce-2e2d-4fbd-9d3e-1a2b3c4d5e6f",
            "mediaType": "image",
            # Must never reach the frontend even if Boost were to send it.
            "correctOptionId": "b",
        },
        "translation": {
            "questionText": "Vad betyder skylten?",
            "explanation": "SECRET explanation",
            "options": [
                {"id": "a", "text": "Stopp"},
                {"id": "b", "text": "Väjningsplikt"},
                {"id": "c", "text": "Parkering förbjuden"},
            ],
        },
    }


def page_payload(
    items: list[dict[str, Any]], *, total: int | None = None, page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    return {
        "items": items,
        "total": len(items) if total is None else total,
        "page": page,
        "pageSize": page_size,
        "asOf": "2026-10-13T08:00:00Z",
    }


def problem_payload(
    status: int, code: str = "ERR", request_id: str = "boost-req-1"
) -> dict[str, Any]:
    return {"status": status, "code": code, "detail": "upstream detail", "requestId": request_id}


# --- fordona-engine (Plan §7.4) ----------------------------------------------


def engine_envelope(response: Any) -> dict[str, Any]:
    return {
        "code": 200,
        "status": "Success",
        "message": "Operation Successful!",
        "response": response,
    }


def engine_problem(
    *,
    status: int,
    error_code: str,
    detail: str = "A business rule was violated.",
    type_path: str = "theory/lesson-locked",
    instance: str = "/internal/theory/v1/x",
) -> dict[str, Any]:
    return {
        "type": f"https://fordona.io/errors/{type_path}",
        "title": "Theory Error",
        "status": status,
        "detail": detail,
        "instance": instance,
        "errorCode": error_code,
        "correlationId": "cid-engine-1",
    }


def open_attempt_ref_payload(
    attempt_id: str = "11111111-1111-1111-1111-111111111111", phase: str = "IN_LESSON"
) -> dict[str, Any]:
    return {"attemptId": attempt_id, "phase": phase}


def home_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user": {"initials": "SI", "firstName": "Samira"},
        "week": {
            "timezone": "Europe/Stockholm",
            "startsOn": "SUNDAY",
            "days": [
                {"date": "2026-11-01", "status": "done", "done": None},
                {"date": "2026-11-02", "status": "today", "done": False},
                {"date": "2026-11-03", "status": "upcoming", "done": None},
                {"date": "2026-11-04", "status": "upcoming", "done": None},
                {"date": "2026-11-05", "status": "upcoming", "done": None},
                {"date": "2026-11-06", "status": "upcoming", "done": None},
                {"date": "2026-11-07", "status": "upcoming", "done": None},
            ],
        },
        "dailyChallenge": {
            "type": "COMPLETE_LESSONS",
            "target": 3,
            "progress": 1,
            "completed": False,
            "resetsAt": "2026-11-02T23:00:00Z",
        },
        "streak": {"current": 5, "longest": 9, "extendedToday": False},
        "readiness": {"percent": 13},
        "tabs": {
            "learningPath": {"locked": False, "lockReason": None},
            "mockExams": {"locked": True, "lockReason": "NOT_AVAILABLE"},
        },
        "continue": {
            "kind": "lesson",
            "unitId": "1",
            "unitDisplayIndex": "1",
            "lessonId": "11",
            "displayIndex": "1.1",
            "title": "Introduction to Driving",
            "action": "START",
            "openAttempt": None,
        },
        "upNext": [
            {
                "kind": "lesson",
                "lessonId": "12",
                "displayIndex": "1.2",
                "title": "Introduction to Signs",
                "status": "LOCKED",
            }
        ],
        "learningPathEtag": '"42.17.a9f3.sv-SE"',
    }
    payload.update(overrides)
    return payload


def learning_path_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "units": [
            {
                "unitId": "1",
                "displayIndex": "1",
                "title": "Fundamentals",
                "iconUrl": None,
                "locked": False,
                "lockReason": None,
                "progress": {"completedLessons": 3, "totalLessons": 7, "percent": 43},
                "entries": [
                    {
                        "kind": "lesson",
                        "lessonId": "11",
                        "displayIndex": "1.1",
                        "title": "Introduction to Driving",
                        "status": "COMPLETED",
                        "lastResult": {"correct": 6, "total": 8},
                        "openAttempt": None,
                    }
                ],
            }
        ]
    }
    payload.update(overrides)
    return payload


def readiness_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "percent": 13,
        "completedLessons": 3,
        "totalLessons": 23,
        "averageBestAccuracy": 0.81,
        "units": [
            {
                "unitId": "1",
                "displayIndex": "1",
                "title": "Fundamentals",
                "percent": 35,
                "completedLessons": 3,
                "totalLessons": 7,
                "locked": False,
            }
        ],
    }
    payload.update(overrides)
    return payload


def lesson_state_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "CURRENT",
        "locked": False,
        "lockReason": None,
        "openAttempt": None,
        "questionCount": 8,
        "estimatedMinutes": 8,
        "lessonVersion": "2",
    }
    payload.update(overrides)
    return payload


def attempt_item_ref_payload(
    *,
    seq: int,
    phase: str = "LESSON",
    question_id: str,
    version: str = "5",
    option_order: list[str] | None = None,
    answered: bool | None = None,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "phase": phase,
        "questionId": question_id,
        "version": version,
        "optionOrder": option_order or ["b", "a", "c"],
        "answered": answered,
    }


def attempt_payload(
    *,
    attempt_id: str = "22222222-2222-2222-2222-222222222222",
    status: str = "IN_LESSON",
    attempt_no: int = 1,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "attemptId": attempt_id,
        "status": status,
        "attemptNo": attempt_no,
        "items": items
        if items is not None
        else [attempt_item_ref_payload(seq=1, question_id="100")],
    }


def answer_feedback_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seq": 1,
        "isCorrect": False,
        "selectedOptionKey": "b",
        "correctOptionKey": "a",
        "correctOptionLabel": "B",
        "explanation": [
            {"type": "text", "markdown": "In this instance the right-hand rule applies."}
        ],
    }
    payload.update(overrides)
    return payload


def phase_completion_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attemptId": "22222222-2222-2222-2222-222222222222",
        "status": "IN_RETRY",
        "lessonSummary": {"total": 8, "correct": 6, "wrong": 2},
        "retrySummary": None,
        "retry": {
            "total": 2,
            "items": [attempt_item_ref_payload(seq=9, phase="RETRY", question_id="200")],
        },
        "next": None,
        "progress": None,
    }
    payload.update(overrides)
    return payload
