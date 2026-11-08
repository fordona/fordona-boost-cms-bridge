"""Lesson theory screen (Plan §7.3) — the one route Phase 1 retired and this
task re-adds, now behind the engine's lock check (security invariant #2: no
theory is fetched from Boost until the engine says the lesson isn't locked).
"""

from typing import Annotated

from fastapi import APIRouter, Path

from fordona_connect.api.deps import CurrentLearner, Locale, ReadRateLimit, Theory
from fordona_connect.api.responses import LESSON_DETAIL_ERRORS
from fordona_connect.schemas.common import ID_PATTERN
from fordona_connect.schemas.theory import LessonDetailOut

router = APIRouter(tags=["theory"])

LessonId = Annotated[str, Path(alias="lessonId", pattern=ID_PATTERN, examples=["14"])]


@router.get(
    "/lessons/{lessonId}",
    response_model=LessonDetailOut,
    responses=LESSON_DETAIL_ERRORS,
    summary="Lesson theory, before Start Quiz",
)
async def get_lesson(
    theory: Theory, _: CurrentLearner, __: ReadRateLimit, locale: Locale, lesson_id: LessonId
) -> LessonDetailOut:
    return await theory.lesson_detail(lesson_id, locale=locale)
