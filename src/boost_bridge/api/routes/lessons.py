from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from boost_bridge.api.deps import Content, CurrentLearner, Locale, PageNumber, PageSize, serve
from boost_bridge.api.responses import CONTENT_ERRORS, LIST_ERRORS
from boost_bridge.schemas.common import ID_PATTERN, Page
from boost_bridge.schemas.lessons import Lesson, LessonSummary
from boost_bridge.schemas.questions import LessonQuestions

router = APIRouter(prefix="/lessons", tags=["lessons"])

LessonId = Annotated[str, Path(alias="lessonId", pattern=ID_PATTERN, examples=["10"])]


@router.get(
    "",
    response_model=Page[LessonSummary],
    responses=LIST_ERRORS,
    summary="List published lessons (chapters)",
)
async def list_lessons(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    module_id: Annotated[str | None, Query(alias="moduleId", pattern=ID_PATTERN)] = None,
    slug: Annotated[str | None, Query(max_length=200, description="Exact slug match.")] = None,
) -> Page[LessonSummary]:
    served = await content.list_lessons(
        locale, page=page, page_size=page_size, module_id=module_id, slug=slug
    )
    return serve(response, served, locale)


@router.get(
    "/{lessonId}",
    response_model=Lesson,
    responses=CONTENT_ERRORS,
    summary="Get one published lesson (chapter) with its content",
)
async def get_lesson(
    response: Response, content: Content, _: CurrentLearner, locale: Locale, lesson_id: LessonId
) -> Lesson:
    return serve(response, await content.get_lesson(lesson_id, locale), locale)


@router.get(
    "/{lessonId}/questions",
    response_model=LessonQuestions,
    responses=LIST_ERRORS,
    summary="All published questions of a lesson, in learning order",
    description="Returns the lesson's complete question set (not paginated), ordered by "
    "the active sequencer. Phase 1 keeps the CMS order; the AI recommendation engine "
    "will plug in here without changing this contract. Questions never include answers.",
)
async def get_lesson_questions(
    response: Response,
    content: Content,
    learner: CurrentLearner,
    locale: Locale,
    lesson_id: LessonId,
) -> LessonQuestions:
    return serve(response, await content.lesson_questions(learner, lesson_id, locale), locale)
