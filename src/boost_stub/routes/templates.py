"""§13.2 #2, #3 and §13.4: question templates, served entirely from the generated
``stub-data/templates.json`` (scripts/generate_stub_templates.py, tracker P2.T2)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from boost_stub.deps import DeliveryToken, LocaleParam, Services
from boost_stub.responses import boost_problem, immutable_response, list_response

router = APIRouter(prefix="/delivery/question-templates", tags=["templates"])

PAGE_SIZE_MAX = 250


def _ids(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def _to_item(template: dict[str, Any], locale: str) -> dict[str, Any]:
    title = template["titles"].get(locale, template["titles"].get("sv-SE"))
    return {
        "id": template["id"],
        "version": template["version"],
        "locale": locale,
        "shared": {
            "lessonId": template["lessonId"],
            "moduleId": template["moduleId"],
            "sort": template["sort"],
            "questions": [
                {"questionId": q["questionId"], "sort": q["sort"]} for q in template["questions"]
            ],
        },
        "translation": {"title": title},
    }


@router.get("")
async def list_templates(
    request: Request,
    services: Services,
    _: DeliveryToken,
    locale: LocaleParam = "sv-SE",
    lesson_id: Annotated[str | None, Query(alias="lessonId")] = None,
    module_id: Annotated[str | None, Query(alias="moduleId")] = None,
    id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=PAGE_SIZE_MAX)] = 20,
) -> Response:
    templates = list(services.data.current.templates.values())
    if lesson_id is not None:
        templates = [t for t in templates if t["lessonId"] == lesson_id]
    if module_id is not None:
        templates = [t for t in templates if t["moduleId"] == module_id]
    wanted = _ids(id)
    if wanted is not None:
        templates = [t for t in templates if t["id"] in wanted]
    templates.sort(key=lambda t: (int(t["lessonId"]), t["sort"]))

    total = len(templates)
    start = (page - 1) * page_size
    page_items = templates[start : start + page_size]
    body = {
        "items": [_to_item(t, locale) for t in page_items],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "asOf": "2026-01-01T00:00:00Z",
    }
    return list_response(request, body)


@router.get("/{template_id}/revisions/{version}")
async def template_revision(
    template_id: str,
    version: str,
    services: Services,
    _: DeliveryToken,
    locale: LocaleParam = "sv-SE",
) -> Response:
    template = services.data.current.templates.get(template_id)
    if template is None or template["version"] != version:
        raise boost_problem(
            404, "TEMPLATE_NOT_FOUND", f"Template {template_id}:{version} not found"
        )
    return immutable_response(_to_item(template, locale))
