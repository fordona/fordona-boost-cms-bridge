"""§13.2's "existing lists" (modules, lessons, questions) and the new lesson and
single-question revision endpoints, proxied from today's Boost (plan §4.5).

**The multi-value ``id=`` filter is enforced by the stub itself**, not assumed
of upstream Boost: a filtered request fetches every page from Boost and filters
in Python. Boost's own id-filter support is unverified (``fordona_connect``'s
README), and the plan requires this filter to work *now*, on today's Boost.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from boost_stub.config import MAX_BATCH_REFS
from boost_stub.data import synthetic_delivery_item
from boost_stub.deps import DeliveryToken, LocaleParam, Services
from boost_stub.responses import boost_problem, immutable_response, list_response
from boost_stub.transforms import transform_lesson_item, transform_question_item
from boost_stub.upstream import UpstreamError

router = APIRouter(prefix="/delivery", tags=["content"])

Transform = Callable[[dict[str, Any]], dict[str, Any]]


def _ids(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def _identity(item: dict[str, Any]) -> dict[str, Any]:
    return item


async def _list(
    services: Services,
    token: str,
    path: str,
    *,
    locale: str,
    page: int,
    page_size: int,
    id_filter: str | None,
    extra_params: dict[str, Any],
    transform: Transform,
) -> dict[str, Any]:
    wanted = _ids(id_filter)
    if wanted is not None:
        all_items = await services.upstream.list_all(
            path, token, {**extra_params, "locale": locale}
        )
        matched = [item for item in all_items if str(item.get("id")) in wanted]
        total = len(matched)
        start = (page - 1) * page_size
        page_items = matched[start : start + page_size]
        return {
            "items": [transform(item) for item in page_items],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "asOf": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    body = await services.upstream.get_json(
        path, token, {**extra_params, "locale": locale, "page": page, "pageSize": page_size}
    )
    return {**body, "items": [transform(item) for item in body.get("items", [])]}


async def _single(
    services: Services, token: str, path: str, transform: Transform
) -> dict[str, Any]:
    try:
        return transform(await services.upstream.get_json(path, token))
    except UpstreamError as exc:
        if exc.response.status_code == 404:
            raise boost_problem(404, "NOT_FOUND", "Not found") from exc
        raise


# --- modules -------------------------------------------------------------------


@router.get("/modules")
async def list_modules(
    request: Request,
    services: Services,
    token: DeliveryToken,
    locale: LocaleParam = "sv-SE",
    id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=250)] = 20,
) -> Response:
    body = await _list(
        services,
        token,
        "/v1/delivery/modules",
        locale=locale,
        page=page,
        page_size=page_size,
        id_filter=id,
        extra_params={},
        transform=_identity,
    )
    return list_response(request, body)


@router.get("/modules/{module_id}")
async def get_module(module_id: str, services: Services, token: DeliveryToken) -> dict[str, Any]:
    return await _single(services, token, f"/v1/delivery/modules/{module_id}", _identity)


# --- lessons ---------------------------------------------------------------------


@router.get("/lessons")
async def list_lessons(
    request: Request,
    services: Services,
    token: DeliveryToken,
    locale: LocaleParam = "sv-SE",
    module_id: Annotated[str | None, Query(alias="moduleId")] = None,
    id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=250)] = 20,
) -> Response:
    body = await _list(
        services,
        token,
        "/v1/delivery/lessons",
        locale=locale,
        page=page,
        page_size=page_size,
        id_filter=id,
        extra_params={"moduleId": module_id} if module_id else {},
        transform=transform_lesson_item,
    )
    return list_response(request, body)


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str, services: Services, token: DeliveryToken) -> dict[str, Any]:
    return await _single(
        services, token, f"/v1/delivery/lessons/{lesson_id}", transform_lesson_item
    )


@router.get("/lessons/{lesson_id}/revisions/{version}")
async def lesson_revision(
    lesson_id: str, version: str, services: Services, token: DeliveryToken
) -> Response:
    """§13.2 #4 (new): today's Boost has no revision history, only the current
    lesson, so the stub serves exactly that version and 404s on any other."""
    try:
        lesson = await services.upstream.get_json(f"/v1/delivery/lessons/{lesson_id}", token)
    except UpstreamError as exc:
        if exc.response.status_code == 404:
            raise boost_problem(404, "LESSON_NOT_FOUND", f"Lesson {lesson_id} not found") from exc
        raise
    if str(lesson.get("version")) != version:
        raise boost_problem(
            404, "LESSON_NOT_FOUND", f"Lesson {lesson_id} has no revision {version}"
        )
    return immutable_response(transform_lesson_item(lesson))


# --- questions -------------------------------------------------------------------


@router.get("/questions")
async def list_questions(
    request: Request,
    services: Services,
    token: DeliveryToken,
    locale: LocaleParam = "sv-SE",
    module_id: Annotated[str | None, Query(alias="moduleId")] = None,
    lesson_id: Annotated[str | None, Query(alias="lessonId")] = None,
    id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=250)] = 20,
) -> Response:
    extra: dict[str, Any] = {}
    if module_id:
        extra["moduleId"] = module_id
    if lesson_id:
        extra["lessonId"] = lesson_id
    body = await _list(
        services,
        token,
        "/v1/delivery/questions",
        locale=locale,
        page=page,
        page_size=page_size,
        id_filter=id,
        extra_params=extra,
        transform=transform_question_item,
    )
    return list_response(request, body)


# --- questions: batch revisions (§13.2 #5, new) -----------------------------------


def parse_refs(raw: str | None) -> list[tuple[str, str]]:
    """``id:version,id:version`` (§13.2). 422 for empty, malformed, or over the batch limit."""
    if not raw or not raw.strip():
        raise boost_problem(422, "REFS_REQUIRED", "refs is required")
    refs: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise boost_problem(422, "INVALID_REF", f"ref {part!r} is not id:version")
        question_id, version = part.split(":", 1)
        if not question_id or not version:
            raise boost_problem(422, "INVALID_REF", f"ref {part!r} is not id:version")
        refs.append((question_id, version))
    if not refs:
        raise boost_problem(422, "REFS_REQUIRED", "refs is required")
    if len(refs) > MAX_BATCH_REFS:
        raise boost_problem(422, "TOO_MANY_REFS", f"at most {MAX_BATCH_REFS} refs per batch")
    return refs


@router.get("/questions/revisions")
async def question_revisions_batch(
    services: Services,
    token: DeliveryToken,
    refs: Annotated[str, Query()],
    locale: LocaleParam = "sv-SE",
) -> Response:
    parsed = parse_refs(refs)
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    real_refs: list[tuple[str, str]] = []
    for question_id, version in parsed:
        synthetic = services.data.current.synthetic_questions.get(question_id)
        if synthetic is None:
            real_refs.append((question_id, version))
        elif synthetic["version"] == version:
            items.append(synthetic_delivery_item(synthetic, locale))
        else:
            missing.append(f"{question_id}:{version}")

    if real_refs:
        paths = [f"/v1/delivery/questions/{qid}/revisions/{v}" for qid, v in real_refs]
        results = await services.upstream.get_many(paths, token, {"locale": locale})
        for (question_id, version), path in zip(real_refs, paths, strict=True):
            result = results[path]
            if result is None:
                missing.append(f"{question_id}:{version}")
            else:
                items.append(transform_question_item(result))

    return immutable_response({"items": items, "missing": missing})


@router.get("/questions/{question_id}")
async def get_question(
    question_id: str, services: Services, token: DeliveryToken, locale: LocaleParam = "sv-SE"
) -> dict[str, Any]:
    synthetic = services.data.current.synthetic_questions.get(question_id)
    if synthetic is not None:
        return synthetic_delivery_item(synthetic, locale)
    return await _single(
        services, token, f"/v1/delivery/questions/{question_id}", transform_question_item
    )


@router.get("/questions/{question_id}/revisions/{version}")
async def question_revision(
    question_id: str,
    version: str,
    services: Services,
    token: DeliveryToken,
    locale: LocaleParam = "sv-SE",
) -> Response:
    synthetic = services.data.current.synthetic_questions.get(question_id)
    if synthetic is not None:
        if synthetic["version"] != version:
            raise boost_problem(
                404, "QUESTION_NOT_FOUND", f"Question {question_id} has no revision {version}"
            )
        return immutable_response(synthetic_delivery_item(synthetic, locale))
    try:
        item = await services.upstream.get_json(
            f"/v1/delivery/questions/{question_id}/revisions/{version}", token
        )
    except UpstreamError as exc:
        if exc.response.status_code == 404:
            raise boost_problem(
                404, "QUESTION_NOT_FOUND", f"Question {question_id}:{version} not found"
            ) from exc
        raise
    return immutable_response(transform_question_item(item))
