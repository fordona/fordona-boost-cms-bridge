import re
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from boost_bridge.api.deps import Content, CurrentLearner, Locale, PageNumber, PageSize, serve
from boost_bridge.api.responses import CONTENT_ERRORS, LIST_ERRORS
from boost_bridge.core.errors import ValidationFailedError
from boost_bridge.schemas.common import ID_PATTERN, Page
from boost_bridge.schemas.questions import Question

router = APIRouter(prefix="/questions", tags=["questions"])

QuestionId = Annotated[str, Path(alias="questionId", pattern=ID_PATTERN, examples=["100"])]
_ID = re.compile(ID_PATTERN)
_MAX_IDS = 100


def _parse_ids(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    invalid = [i for i in ids if not _ID.match(i)]
    if not ids or invalid or len(ids) > _MAX_IDS:
        message = f"ids must be 1-{_MAX_IDS} comma-separated decimal ids"
        raise ValidationFailedError(
            message,
            extra={"fieldErrors": [{"field": "ids", "location": "query", "message": message}]},
        )
    return ids


@router.get(
    "",
    response_model=Page[Question],
    responses=LIST_ERRORS,
    summary="List published questions (answer-free)",
)
async def list_questions(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    module_id: Annotated[str | None, Query(alias="moduleId", pattern=ID_PATTERN)] = None,
    lesson_id: Annotated[str | None, Query(alias="lessonId", pattern=ID_PATTERN)] = None,
    ids: Annotated[
        str | None,
        Query(
            max_length=2_200,
            description=f"Comma-separated question ids (max {_MAX_IDS}) for batch lookup.",
            examples=["100,101,102"],
        ),
    ] = None,
) -> Page[Question]:
    served = await content.list_questions(
        locale,
        page=page,
        page_size=page_size,
        module_id=module_id,
        lesson_id=lesson_id,
        ids=_parse_ids(ids),
    )
    return serve(response, served, locale)


@router.get(
    "/{questionId}",
    response_model=Question,
    responses=CONTENT_ERRORS,
    summary="Get one published question (answer-free)",
)
async def get_question(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    question_id: QuestionId,
) -> Question:
    return serve(response, await content.get_question(question_id, locale), locale)


@router.get(
    "/{questionId}/revisions/{version}",
    response_model=Question,
    responses=CONTENT_ERRORS,
    summary="Get a specific previously published revision of a question",
    description="For attempts pinned to the revision the learner actually saw. "
    "Answer-free, like every question response.",
)
async def get_question_revision(
    response: Response,
    content: Content,
    _: CurrentLearner,
    locale: Locale,
    question_id: QuestionId,
    version: Annotated[str, Path(pattern=ID_PATTERN, examples=["5"])],
) -> Question:
    served = await content.get_question_revision(question_id, version, locale)
    return serve(response, served, locale)
