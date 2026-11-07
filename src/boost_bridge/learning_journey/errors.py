"""Error hierarchy for the Learning Journey contract (spec §2, §14).

Deliberately **not** a subclass of ``core.errors.AppError`` — that hierarchy renders
RFC 7807 ``problem+json``, which conflicts with this spec's own
``{"success": false, "error": {code, message, details, request_id}}`` envelope. Both
handlers are registered side by side in ``main.py``; every other route in this BFF is
unaffected.

**Known, accepted edge case**: a malformed request *body* (e.g. missing required
field) on one of these routes is caught by FastAPI before a route body even runs, by
the ``RequestValidationError`` handler already registered globally in
``core/errors.py`` — that one case still renders as RFC 7807, not this envelope, since
Starlette only allows one handler per exception type and this is a pure HTTP-shape
concern, not a business-rule one. Every ``LearningJourneyError`` this package raises
itself (including re-using ``VALIDATION_ERROR`` for business-rule validation) renders
correctly in the new envelope.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from boost_bridge.core.context import get_correlation_id


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    NOT_FOUND = "NOT_FOUND"
    CHALLENGE_LOCKED = "CHALLENGE_LOCKED"
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED"
    ACTIVE_ATTEMPT_EXISTS = "ACTIVE_ATTEMPT_EXISTS"
    ANSWER_ALREADY_FINALIZED = "ANSWER_ALREADY_FINALIZED"
    ATTEMPT_NOT_ACTIVE = "ATTEMPT_NOT_ACTIVE"
    ATTEMPT_INCOMPLETE = "ATTEMPT_INCOMPLETE"
    REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
    REMEDIATION_NOT_ELIGIBLE = "REMEDIATION_NOT_ELIGIBLE"
    CONTENT_NOT_READY = "CONTENT_NOT_READY"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"


class LearningJourneyError(Exception):
    status_code: int = 500
    error_code: str = ErrorCode.VALIDATION_ERROR
    default_message: str = "An unexpected error occurred."

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class ValidationError(LearningJourneyError):
    status_code = 400
    error_code = ErrorCode.VALIDATION_ERROR
    default_message = "The request is invalid."


class UnauthenticatedError(LearningJourneyError):
    status_code = 401
    error_code = ErrorCode.UNAUTHENTICATED
    default_message = "A valid bearer token is required."


class NotFoundError(LearningJourneyError):
    status_code = 404
    error_code = ErrorCode.NOT_FOUND
    default_message = "The requested resource was not found."


class SubscriptionRequiredError(LearningJourneyError):
    status_code = 403
    error_code = ErrorCode.SUBSCRIPTION_REQUIRED
    default_message = "An active subscription is required for this content."


class ChallengeLockedError(LearningJourneyError):
    status_code = 403
    error_code = ErrorCode.CHALLENGE_LOCKED
    default_message = "This challenge is locked until the previous one is completed."


class ActiveAttemptExistsError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.ACTIVE_ATTEMPT_EXISTS
    default_message = "An attempt is already in progress for this challenge."


class AnswerAlreadyFinalizedError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.ANSWER_ALREADY_FINALIZED
    default_message = "This question has already been answered."


class AttemptNotActiveError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.ATTEMPT_NOT_ACTIVE
    default_message = "This attempt is not in progress."


class AttemptIncompleteError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.ATTEMPT_INCOMPLETE
    default_message = "Every question must be answered before submitting."


class RemediationRequiredError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.REMEDIATION_REQUIRED
    default_message = "A mandatory correction round must be completed first."


class RemediationNotEligibleError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.REMEDIATION_NOT_ELIGIBLE
    default_message = "This attempt is not eligible for remediation."


class ContentNotReadyError(LearningJourneyError):
    status_code = 422
    error_code = ErrorCode.CONTENT_NOT_READY
    default_message = "This challenge's content is not ready to be delivered."


class IdempotencyKeyReusedError(LearningJourneyError):
    status_code = 409
    error_code = ErrorCode.IDEMPOTENCY_KEY_REUSED
    default_message = "This idempotency key was already used with a different request."


def _error_response(
    *, status_code: int, error_code: str, message: str, details: dict[str, Any] | None
) -> JSONResponse:
    return JSONResponse(
        {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
                "request_id": get_correlation_id(),
            },
        },
        status_code=status_code,
    )


async def handle_learning_journey_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(
        exc, LearningJourneyError
    ):  # pragma: no cover - registration guarantees the type
        raise exc
    return _error_response(
        status_code=exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
    )


def register_learning_journey_exception_handler(app: FastAPI) -> None:
    app.add_exception_handler(LearningJourneyError, handle_learning_journey_error)
