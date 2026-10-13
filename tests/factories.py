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
