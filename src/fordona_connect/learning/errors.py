"""Learning errors, with the engine's error codes so clients see no change."""

from fordona_connect.core.errors import AppError, TheoryLessonLockedError, TheoryModuleLockedError

__all__ = [
    "AttemptNotFoundError",
    "ItemNotFoundError",
    "LessonNotFoundError",
    "MockExamNotFoundError",
    "OptionInvalidError",
    "PhaseClosedError",
    "PhaseIncompleteError",
    "RequestIdConflictError",
    "ResponseConflictError",
    "TheoryLessonLockedError",
    "TheoryModuleLockedError",
]


class LessonNotFoundError(AppError):
    status_code = 404
    error_code = "THEORY_ATTEMPT_LESSON_NOT_FOUND"
    type_path = "theory/lesson-not-found"


class AttemptNotFoundError(AppError):
    status_code = 404
    error_code = "THEORY_ATTEMPT_NOT_FOUND"
    type_path = "theory/attempt-not-found"


class ItemNotFoundError(AppError):
    status_code = 404
    error_code = "THEORY_ITEM_NOT_FOUND"
    type_path = "theory/item-not-found"


class RequestIdConflictError(AppError):
    status_code = 409
    error_code = "THEORY_REQUEST_ID_CONFLICT"
    type_path = "theory/request-id-conflict"


class ResponseConflictError(AppError):
    status_code = 409
    error_code = "THEORY_RESPONSE_CONFLICT"
    type_path = "theory/response-conflict"


class PhaseClosedError(AppError):
    status_code = 409
    error_code = "THEORY_PHASE_CLOSED"
    type_path = "theory/phase-closed"


class PhaseIncompleteError(AppError):
    status_code = 409
    error_code = "THEORY_PHASE_INCOMPLETE"
    type_path = "theory/phase-incomplete"


class OptionInvalidError(AppError):
    status_code = 422
    error_code = "THEORY_OPTION_INVALID"
    type_path = "theory/option-invalid"


class MockExamNotFoundError(AppError):
    status_code = 404
    error_code = "THEORY_MOCK_EXAM_NOT_FOUND"
    type_path = "theory/mock-exam-not-found"
