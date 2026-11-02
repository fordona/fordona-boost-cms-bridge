"""A minimal stand-in for real Boost's delivery and grading APIs.

Used only to run the §13 contract suite against a *live* instance of the Boost
stub (``test_stub_against_contract_suite.py``). Real network, real tokens
checked by value — the point is to prove the stub's own HTTP behaviour, not to
model every corner of Boost.
"""

from typing import Any

from fastapi import FastAPI, HTTPException, Request

DELIVERY_TOKEN = "fake-delivery-token"
GRADING_TOKEN = "fake-grading-token"


def _problem(status: int, code: str) -> HTTPException:
    return HTTPException(
        status,
        {"status": status, "code": code, "detail": code, "requestId": "fake", "errors": None},
    )


def _require(request: Request, token: str) -> None:
    header = request.headers.get("authorization", "")
    if header != f"Bearer {token}":
        raise _problem(401, "UNAUTHORIZED")


def _page(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "total": len(items),
        "page": page,
        "pageSize": page_size,
        "asOf": "2026-01-01T00:00:00Z",
    }


def build_fake_boost(
    modules: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    grading: dict[tuple[str, str], dict[str, Any]],
) -> FastAPI:
    app = FastAPI()
    by_id = {
        "modules": {m["id"]: m for m in modules},
        "lessons": {le["id"]: le for le in lessons},
        "questions": {q["id"]: q for q in questions},
    }

    @app.get("/v1/delivery/modules")
    async def list_modules(
        request: Request,
        locale: str = "sv-SE",
        page: int = 1,
        pageSize: int = 20,  # noqa: N803
    ) -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        body = _page(modules, page, pageSize)
        body["items"] = [{**item, "locale": locale} for item in body["items"]]
        return body

    @app.get("/v1/delivery/modules/{module_id}")
    async def get_module(module_id: str, request: Request, locale: str = "sv-SE") -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        item = by_id["modules"].get(module_id)
        if item is None:
            raise _problem(404, "NOT_FOUND")
        return {**item, "locale": locale}

    @app.get("/v1/delivery/lessons")
    async def list_lessons(
        request: Request,
        moduleId: str | None = None,  # noqa: N803
        locale: str = "sv-SE",
        page: int = 1,
        pageSize: int = 20,  # noqa: N803
    ) -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        items = (
            lessons
            if moduleId is None
            else [le for le in lessons if le["shared"]["moduleId"] == moduleId]
        )
        body = _page(items, page, pageSize)
        body["items"] = [{**item, "locale": locale} for item in body["items"]]
        return body

    @app.get("/v1/delivery/lessons/{lesson_id}")
    async def get_lesson(lesson_id: str, request: Request, locale: str = "sv-SE") -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        item = by_id["lessons"].get(lesson_id)
        if item is None:
            raise _problem(404, "NOT_FOUND")
        return {**item, "locale": locale}

    @app.get("/v1/delivery/questions")
    async def list_questions(
        request: Request,
        moduleId: str | None = None,  # noqa: N803
        lessonId: str | None = None,  # noqa: N803
        locale: str = "sv-SE",
        page: int = 1,
        pageSize: int = 20,  # noqa: N803
    ) -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        items = questions
        if moduleId is not None:
            items = [q for q in items if q["shared"]["moduleId"] == moduleId]
        if lessonId is not None:
            items = [q for q in items if q["shared"]["lessonId"] == lessonId]
        body = _page(items, page, pageSize)
        body["items"] = [{**item, "locale": locale} for item in body["items"]]
        return body

    @app.get("/v1/delivery/questions/{question_id}")
    async def get_question(
        question_id: str, request: Request, locale: str = "sv-SE"
    ) -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        item = by_id["questions"].get(question_id)
        if item is None:
            raise _problem(404, "NOT_FOUND")
        return {**item, "locale": locale}

    @app.get("/v1/delivery/questions/{question_id}/revisions/{version}")
    async def get_question_revision(
        question_id: str, version: str, request: Request, locale: str = "sv-SE"
    ) -> dict[str, Any]:
        _require(request, DELIVERY_TOKEN)
        item = by_id["questions"].get(question_id)
        if item is None or item["version"] != version:
            raise _problem(404, "NOT_FOUND")
        return {**item, "locale": locale}

    @app.get("/v1/grading/questions/{question_id}/revisions/{version}")
    async def get_grading(question_id: str, version: str, request: Request) -> dict[str, Any]:
        _require(request, GRADING_TOKEN)
        item = grading.get((question_id, version))
        if item is None:
            raise _problem(404, "NOT_FOUND")
        return item

    return app
