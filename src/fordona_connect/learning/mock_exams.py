"""The mock exam catalogue (ported from the engine's MockExamTheoryService).

Questions are listed only while active, at their current revision.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.clients.engine.theory import (
    EngineMockExamDetail,
    EngineMockExamQuestionRef,
    EngineMockExamSummary,
)
from fordona_connect.learning.content.models import ContentMockExam, ContentMockExamQuestion
from fordona_connect.learning.content.snapshot import SnapshotProvider
from fordona_connect.learning.errors import MockExamNotFoundError
from fordona_connect.learning.progress.screens import title_in


class MockExamService:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], snapshots: SnapshotProvider
    ) -> None:
        self._sessionmaker = sessionmaker
        self._snapshots = snapshots

    async def list(self, *, locale: str) -> list[EngineMockExamSummary]:
        async with self._sessionmaker() as session:
            exams = await session.scalars(
                select(ContentMockExam).order_by(ContentMockExam.mock_exam_id)
            )
            return [
                EngineMockExamSummary(
                    mock_exam_id=exam.mock_exam_id,
                    name=title_in(exam.name, locale),
                    description=title_in(exam.description, locale),
                    question_count=exam.question_count,
                    complete=exam.complete,
                )
                for exam in exams
            ]

    async def detail(self, mock_exam_id: str, *, locale: str) -> EngineMockExamDetail:
        snapshot = await self._snapshots.get()
        async with self._sessionmaker() as session:
            exam = await session.get(ContentMockExam, mock_exam_id)
            if exam is None:
                raise MockExamNotFoundError(f"Mock exam {mock_exam_id} not found")
            question_ids = await session.scalars(
                select(ContentMockExamQuestion.question_id)
                .where(ContentMockExamQuestion.mock_exam_id == mock_exam_id)
                .order_by(ContentMockExamQuestion.sort)
            )
            items = [
                EngineMockExamQuestionRef(
                    question_id=question.question_id, version=question.version
                )
                for question_id in question_ids
                if (question := snapshot.question(question_id)) is not None
            ]
        return EngineMockExamDetail(
            mock_exam_id=exam.mock_exam_id,
            name=title_in(exam.name, locale),
            description=title_in(exam.description, locale),
            question_count=exam.question_count,
            complete=exam.complete,
            items=items,
        )
