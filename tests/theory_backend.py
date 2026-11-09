"""An in-memory ``TheoryBackend`` for the API tests.

Each method returns the payload set for it (validated into the real model, so a
payload drifting from the model fails loudly) or raises the exception set for it.
Every call is recorded with its arguments.
"""

from dataclasses import dataclass, field
from typing import Any

from fordona_connect.learning.theory_models import (
    TheoryAnswerFeedback,
    TheoryAttempt,
    TheoryAttemptPhaseCompletion,
    TheoryHome,
    TheoryLearningPath,
    TheoryLessonState,
    TheoryMockExamDetail,
    TheoryMockExamSummary,
    TheoryReadiness,
)


@dataclass
class Call:
    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass
class FakeTheoryBackend:
    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)

    def set(self, method: str, response: Any) -> None:
        """A payload (or list of payloads) to return, or an exception to raise."""
        self.responses[method] = response

    def calls_to(self, method: str) -> list[Call]:
        return [call for call in self.calls if call.method == method]

    def _respond(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(Call(method, args, kwargs))
        if method not in self.responses:
            raise AssertionError(f"FakeTheoryBackend.{method} was called but not set")
        response = self.responses[method]
        if isinstance(response, BaseException):
            raise response
        return response

    async def get_home(self, *, accept_language: str, timezone: str | None) -> TheoryHome:
        payload = self._respond("get_home", accept_language=accept_language, timezone=timezone)
        return TheoryHome.model_validate(payload)

    async def get_learning_path(
        self, *, accept_language: str, if_none_match: str | None
    ) -> tuple[TheoryLearningPath | None, str | None, bool]:
        """Set a ``(payload-or-None, etag, not_modified)`` tuple."""
        payload, etag, not_modified = self._respond(
            "get_learning_path", accept_language=accept_language, if_none_match=if_none_match
        )
        path = None if payload is None else TheoryLearningPath.model_validate(payload)
        return path, etag, not_modified

    async def get_readiness(self, *, accept_language: str) -> TheoryReadiness:
        payload = self._respond("get_readiness", accept_language=accept_language)
        return TheoryReadiness.model_validate(payload)

    async def get_lesson_state(self, lesson_id: str) -> TheoryLessonState:
        return TheoryLessonState.model_validate(self._respond("get_lesson_state", lesson_id))

    async def list_mock_exams(self, *, accept_language: str) -> list[TheoryMockExamSummary]:
        payloads = self._respond("list_mock_exams", accept_language=accept_language)
        return [TheoryMockExamSummary.model_validate(item) for item in payloads]

    async def get_mock_exam(
        self, mock_exam_id: str, *, accept_language: str
    ) -> TheoryMockExamDetail:
        payload = self._respond("get_mock_exam", mock_exam_id, accept_language=accept_language)
        return TheoryMockExamDetail.model_validate(payload)

    async def start_attempt(self, lesson_id: str, request_id: str) -> TheoryAttempt:
        return TheoryAttempt.model_validate(self._respond("start_attempt", lesson_id, request_id))

    async def get_attempt(self, attempt_id: str) -> TheoryAttempt:
        return TheoryAttempt.model_validate(self._respond("get_attempt", attempt_id))

    async def answer(
        self,
        attempt_id: str,
        *,
        response_id: str,
        seq: int,
        selected_option_key: str,
        duration_ms: int | None,
        accept_language: str,
    ) -> TheoryAnswerFeedback:
        payload = self._respond(
            "answer",
            attempt_id,
            response_id=response_id,
            seq=seq,
            selected_option_key=selected_option_key,
            duration_ms=duration_ms,
            accept_language=accept_language,
        )
        return TheoryAnswerFeedback.model_validate(payload)

    async def complete_lesson_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> TheoryAttemptPhaseCompletion:
        payload = self._respond(
            "complete_lesson_phase",
            attempt_id,
            accept_language=accept_language,
            timezone=timezone,
        )
        return TheoryAttemptPhaseCompletion.model_validate(payload)

    async def complete_retry_phase(
        self, attempt_id: str, *, accept_language: str, timezone: str | None
    ) -> TheoryAttemptPhaseCompletion:
        payload = self._respond(
            "complete_retry_phase",
            attempt_id,
            accept_language=accept_language,
            timezone=timezone,
        )
        return TheoryAttemptPhaseCompletion.model_validate(payload)
