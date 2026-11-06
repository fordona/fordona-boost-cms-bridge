"""Mock exams (new Boost entity, 2026-11-06, confirmed against the production Boost OpenAPI spec).
Synthesized entirely from the generated templates (``boost_stub.data._build_mock_exams``) — today's
Boost and this stub have no mock-exam authoring of their own yet.

Added to close a real gap: fordona-engine's ``ContentSyncService`` started calling
``GET /v1/delivery/mock-exams`` unconditionally (2026-11-05), and this route not existing at all
previously aborted the engine's whole sync whenever it ran against the stub (see fordona-engine
commit ``28df9c59`` for the matching 404-tolerance fix on that side)."""

from typing import Any

from fastapi import APIRouter, Request, Response

from boost_stub.deps import DeliveryToken, LocaleParam, Services
from boost_stub.responses import list_response

router = APIRouter(prefix="/delivery/mock-exams", tags=["mock-exams"])


def _to_item(exam: dict[str, Any], locale: str) -> dict[str, Any]:
    return {
        "id": exam["id"],
        "version": exam["version"],
        "name": exam["name"].get(locale, exam["name"].get("sv-SE")),
        "description": exam["description"].get(locale, exam["description"].get("sv-SE")),
        "questionCount": exam["questionCount"],
        "questionIds": exam["questionIds"],
        "complete": exam["complete"],
    }


@router.get("")
async def list_mock_exams(
    request: Request, services: Services, _: DeliveryToken, locale: LocaleParam = "sv-SE"
) -> Response:
    items = [_to_item(exam, locale) for exam in services.data.current.mock_exams.values()]
    body = {"items": items, "asOf": "2026-01-01T00:00:00Z", "locale": locale}
    return list_response(request, body)
