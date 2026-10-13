"""Error hierarchy and RFC 7807 problem+json rendering.

The response shape mirrors fordona-engine's ``GlobalExceptionHandler`` so a client
handles errors from both services the same way:
``type, title, status, detail, instance, errorCode, correlationId``.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from boost_bridge.core.context import get_correlation_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
_TYPE_BASE = "https://fordona.io/errors"


class ErrorCode:
    CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UPSTREAM_MISCONFIGURED = "UPSTREAM_MISCONFIGURED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"


class AppError(Exception):
    """Base for every error this service deliberately returns to a client."""

    status_code: int = 500
    error_code: str = ErrorCode.INTERNAL_ERROR
    type_path: str = "internal/error"
    default_detail: str = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.default_detail
        self.headers = headers or {}
        self.extra = extra or {}
        super().__init__(self.detail)


class ContentNotFoundError(AppError):
    status_code = 404
    error_code = ErrorCode.CONTENT_NOT_FOUND
    type_path = "content/not-found"
    default_detail = "The requested content does not exist or is not published."


class UnauthorizedError(AppError):
    status_code = 401
    error_code = ErrorCode.UNAUTHORIZED
    type_path = "auth/unauthorized"
    default_detail = "A valid bearer token is required."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail, headers={"WWW-Authenticate": "Bearer"})


class ValidationFailedError(AppError):
    status_code = 422
    error_code = ErrorCode.VALIDATION_FAILED
    type_path = "validation/invalid-input"
    default_detail = "The request is invalid."


class UpstreamMisconfiguredError(AppError):
    """Boost rejected *our* credential or request: a server fault, not the caller's."""

    status_code = 502
    error_code = ErrorCode.UPSTREAM_MISCONFIGURED
    type_path = "upstream/misconfigured"
    default_detail = "The content service is misconfigured. Please try again later."


class UpstreamUnavailableError(AppError):
    status_code = 503
    error_code = ErrorCode.UPSTREAM_UNAVAILABLE
    type_path = "upstream/unavailable"
    default_detail = "Content is temporarily unavailable. Please try again shortly."


class UpstreamTimeoutError(AppError):
    status_code = 504
    error_code = ErrorCode.UPSTREAM_TIMEOUT
    type_path = "upstream/timeout"
    default_detail = "The content service timed out. Please try again shortly."


def _title(error_code: str) -> str:
    return " ".join(word.capitalize() for word in error_code.split("_"))


def problem_body(
    *,
    status: int,
    error_code: str,
    type_path: str,
    detail: str,
    instance: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{_TYPE_BASE}/{type_path}",
        "title": _title(error_code),
        "status": status,
        "detail": detail,
        "instance": instance,
        "errorCode": error_code,
        "correlationId": get_correlation_id(),
    }
    if extra:
        body.update(extra)
    return body


def problem_response(
    *,
    status: int,
    error_code: str,
    type_path: str,
    detail: str,
    instance: str,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        problem_body(
            status=status,
            error_code=error_code,
            type_path=type_path,
            detail=detail,
            instance=instance,
            extra=extra,
        ),
        status_code=status,
        headers=headers,
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover - registration guarantees the type
        raise exc
    return problem_response(
        status=exc.status_code,
        error_code=exc.error_code,
        type_path=exc.type_path,
        detail=exc.detail,
        instance=request.url.path,
        headers=exc.headers,
        extra=exc.extra,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    field_errors = []
    for err in exc.errors():
        loc = tuple(err.get("loc", ("request",)))
        field_errors.append(
            {
                # loc is e.g. ("path", "questionId") or ("query", "pageSize")
                "field": ".".join(str(part) for part in loc[1:]) or str(loc[0]),
                "location": str(loc[0]),
                "message": err.get("msg", "Invalid value"),
            }
        )
    return problem_response(
        status=422,
        error_code=ErrorCode.VALIDATION_FAILED,
        type_path="validation/invalid-input",
        detail="One or more request parameters are invalid.",
        instance=request.url.path,
        extra={"fieldErrors": field_errors},
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    codes = {404: ErrorCode.NOT_FOUND, 405: ErrorCode.METHOD_NOT_ALLOWED}
    error_code = codes.get(exc.status_code, ErrorCode.HTTP_ERROR)
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = "HTTP error"
    detail = exc.detail if isinstance(exc.detail, str) else phrase
    return problem_response(
        status=exc.status_code,
        error_code=error_code,
        type_path=f"http/{exc.status_code}",
        detail=detail,
        instance=request.url.path,
        headers=dict(exc.headers) if exc.headers else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    # Unhandled exceptions are rendered by RequestContextMiddleware, which still
    # has the correlation id bound. See core/middleware.py.
