"""Home dashboard, learning path and readiness detail (Plan §7.3)."""

from typing import Annotated

from fastapi import APIRouter, Header, Response

from fordona_connect.api.deps import CurrentLearner, Locale, ReadRateLimit, Theory, Timezone
from fordona_connect.api.responses import READ_ERRORS
from fordona_connect.schemas.theory import HomeOut, LearningPathOut, ReadinessOut

router = APIRouter(tags=["theory"])

IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match", include_in_schema=False)]


@router.get(
    "/home",
    response_model=HomeOut,
    responses=READ_ERRORS,
    summary="Home dashboard — week, streak, daily challenge, readiness, continue card",
)
async def get_home(
    theory: Theory, _: CurrentLearner, __: ReadRateLimit, locale: Locale, timezone: Timezone
) -> HomeOut:
    return await theory.home(locale=locale, timezone=timezone)


@router.get(
    "/learning-path",
    response_model=LearningPathOut,
    responses={304: {"description": "Not modified."}, **READ_ERRORS},
    summary="Swipe-up learning path sheet, with ETag/304",
)
async def get_learning_path(
    response: Response,
    theory: Theory,
    _: CurrentLearner,
    __: ReadRateLimit,
    locale: Locale,
    if_none_match: IfNoneMatch = None,
) -> LearningPathOut | Response:
    path, etag, not_modified = await theory.learning_path(
        locale=locale, if_none_match=if_none_match
    )
    response.headers["Cache-Control"] = "private, no-cache"
    if etag:
        response.headers["ETag"] = etag
    if not_modified:
        return Response(status_code=304, headers=dict(response.headers))
    assert path is not None
    return path


@router.get(
    "/readiness",
    response_model=ReadinessOut,
    responses=READ_ERRORS,
    summary="Readiness detail screen",
)
async def get_readiness(
    theory: Theory, _: CurrentLearner, __: ReadRateLimit, locale: Locale
) -> ReadinessOut:
    return await theory.readiness(locale=locale)
