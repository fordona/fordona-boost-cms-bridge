from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from boost_bridge.api.deps import Content, CurrentLearner, Locale, PageNumber, PageSize, serve
from boost_bridge.api.responses import CONTENT_ERRORS, LIST_ERRORS
from boost_bridge.schemas.common import ID_PATTERN, Page
from boost_bridge.schemas.lessons import LessonSummary
from boost_bridge.schemas.modules import Module

router = APIRouter(prefix="/modules", tags=["modules"])

ModuleId = Annotated[str, Path(alias="moduleId", pattern=ID_PATTERN, examples=["1"])]


@router.get(
    "",
    response_model=Page[Module],
    responses=LIST_ERRORS,
    summary="List published theory modules",
)
async def list_modules(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    slug: Annotated[str | None, Query(max_length=200, description="Exact slug match.")] = None,
) -> Page[Module]:
    served = await content.list_modules(locale, page=page, page_size=page_size, slug=slug)
    return serve(response, served, locale)


@router.get(
    "/{moduleId}",
    response_model=Module,
    responses=CONTENT_ERRORS,
    summary="Get one published theory module",
)
async def get_module(
    response: Response, content: Content, _: CurrentLearner, locale: Locale, module_id: ModuleId
) -> Module:
    return serve(response, await content.get_module(module_id, locale), locale)


@router.get(
    "/{moduleId}/lessons",
    response_model=Page[LessonSummary],
    responses=LIST_ERRORS,
    summary="List the published lessons (chapters) of a module",
)
async def list_module_lessons(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    module_id: ModuleId,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[LessonSummary]:
    served = await content.list_lessons(locale, page=page, page_size=page_size, module_id=module_id)
    return serve(response, served, locale)
