"""The theory routes' backend, served by this service's own learning modules.

``LocalTheoryBackend`` has the exact method signatures of the engine's theory
client (``clients.engine.theory.EngineTheoryClient``) and returns the same models,
so ``TheoryService`` and the public routes work unchanged on either. The learner
is the one authenticated on the current request (``learner_id_var``).
"""

import uuid

from fordona_connect.clients.engine.theory import (
    EngineAnswerFeedback,
    EngineAttempt,
    EngineAttemptPhaseCompletion,
    EngineHome,
    EngineLearningPath,
    EngineLessonState,
    EngineMockExamDetail,
    EngineMockExamSummary,
    EngineReadiness,
)
from fordona_connect.core.context import learner_id_var
from fordona_connect.core.errors import UnauthorizedError
from fordona_connect.learning.attempts.service import AttemptService
from fordona_connect.learning.errors import AttemptNotFoundError
from fordona_connect.learning.mock_exams import MockExamService
from fordona_connect.learning.progress.screens import ProgressScreens


def _learner() -> str:
    learner_id = learner_id_var.get()
    if not learner_id:
        raise UnauthorizedError("No authenticated learner on this request")
    return learner_id


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AttemptNotFoundError(f"Attempt not found: {value}") from exc


class LocalTheoryBackend:
    def __init__(
        self, attempts: AttemptService, screens: ProgressScreens, mock_exams: MockExamService
    ) -> None:
        self._attempts = attempts
        self._screens = screens
        self._mock_exams = mock_exams

    async def get_home(self, *, accept_language: str, timezone: str | None) -> EngineHome:
        return await self._screens.home(_learner(), locale=accept_language, timezone=timezone)

    async def get_learning_path(
        self, *, accept_language: str, if_none_match: str | None
    ) -> tuple[EngineLearningPath | None, str | None, bool]:
        """Returns ``(path-or-None-when-unchanged, etag, not_modified)``."""
        learner_id = _learner()
        etag = await self._screens.learning_path_etag(learner_id, locale=accept_language)
        if if_none_match is not None and if_none_match == etag:
            return None, etag, True
        return await self._screens.learning_path(learner_id, locale=accept_language), etag, False

    async def get_readiness(self, *, accept_language: str) -> EngineReadiness:
        return await self._screens.readiness(_learner(), locale=accept_language)

    async def get_lesson_state(self, lesson_id: str) -> EngineLessonState:
        return await self._attempts.lesson_state(_learner(), lesson_id)

    async def list_mock_exams(self, *, accept_language: str) -> list[EngineMockExamSummary]:
        return await self._mock_exams.list(locale=accept_language)

    async def get_mock_exam(
        self, mock_exam_id: str, *, accept_language: str
    ) -> EngineMockExamDetail:
        return await self._mock_exams.detail(mock_exam_id, locale=accept_language)

    async def start_attempt(self, lesson_id: str, request_id: str) -> EngineAttempt:
        return await self._attempts.start(_learner(), lesson_id, uuid.UUID(request_id))

    async def get_attempt(self, attempt_id: str) -> EngineAttempt:
        return await self._attempts.get(_learner(), _uuid(attempt_id))

    async def answer(
        self,
        attempt_id: str,
        *,
        response_id: str,
        seq: int,
        selected_option_key: str,
        duration_ms: int | None,
        accept_language: str,
    ) -> EngineAnswerFeedback:
        return await self._attempts.answer(
            _learner(),
            _uuid(attempt_id),
            seq=seq,
            selected_option_key=selected_option_key,
            response_id=uuid.UUID(response_id),
            duration_ms=duration_ms,
            locale=accept_language,
        )

    async def complete_lesson_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> EngineAttemptPhaseCompletion:
        return await self._attempts.complete_lesson_phase(
            _learner(), _uuid(attempt_id), locale=accept_language, timezone=timezone
        )

    async def complete_retry_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> EngineAttemptPhaseCompletion:
        return await self._attempts.complete_retry_phase(
            _learner(), _uuid(attempt_id), locale=accept_language, timezone=timezone
        )
