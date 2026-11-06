"""Mock exam browsing — list + preview, read-only (2026-11-07). No attempt/session
tracking or scoring yet: that's a separate, larger piece of work (see the engine
service's own docstring for why)."""

from typing import Annotated

from fastapi import APIRouter, Path

from boost_bridge.api.deps import CurrentLearner, Locale, ReadRateLimit, Theory
from boost_bridge.api.responses import MOCK_EXAM_DETAIL_ERRORS, READ_ERRORS
from boost_bridge.schemas.common import ID_PATTERN
from boost_bridge.schemas.theory import MockExamDetailOut, MockExamSummaryOut

router = APIRouter(tags=["theory"])

MockExamId = Annotated[str, Path(alias="mockExamId", pattern=ID_PATTERN, examples=["1"])]


@router.get(
    "/mock-exams",
    response_model=list[MockExamSummaryOut],
    responses=READ_ERRORS,
    summary="List available mock exams",
)
async def list_mock_exams(
    theory: Theory, _: CurrentLearner, __: ReadRateLimit, locale: Locale
) -> list[MockExamSummaryOut]:
    return await theory.list_mock_exams(locale=locale)


@router.get(
    "/mock-exams/{mockExamId}",
    response_model=MockExamDetailOut,
    responses=MOCK_EXAM_DETAIL_ERRORS,
    summary="One mock exam's questions, for preview",
)
async def get_mock_exam(
    theory: Theory,
    _: CurrentLearner,
    __: ReadRateLimit,
    locale: Locale,
    mock_exam_id: MockExamId,
) -> MockExamDetailOut:
    return await theory.mock_exam_detail(mock_exam_id, locale=locale)
