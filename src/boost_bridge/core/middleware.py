"""Request context middleware: correlation id, access log, last-resort error rendering.

Written as plain ASGI rather than Starlette's ``BaseHTTPMiddleware``.
``BaseHTTPMiddleware`` runs the downstream app in a separate task, which breaks
contextvar propagation and complicates background work.
"""

import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from boost_bridge.core.context import CORRELATION_ID_HEADER, correlation_id_var
from boost_bridge.core.errors import ErrorCode, problem_response
from boost_bridge.core.logging import get_logger

# Accept a caller's id only if it is short and inert. Anything else is replaced,
# so a client cannot inject newlines or megabytes into our logs.
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_HEADER_NAME = CORRELATION_ID_HEADER.lower().encode("latin-1")

access_log = get_logger("boost_bridge.access")
error_log = get_logger("boost_bridge.error")


def _incoming_correlation_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == _HEADER_NAME:
            candidate: str = value.decode("latin-1")
            if _SAFE_CORRELATION_ID.match(candidate):
                return candidate
            break
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = _incoming_correlation_id(scope)
        token = correlation_id_var.set(correlation_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((_HEADER_NAME, correlation_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            error_log.exception("unhandled_exception", path=scope.get("path"))
            if response_started:
                raise
            response = problem_response(
                status=500,
                error_code=ErrorCode.INTERNAL_ERROR,
                type_path="internal/error",
                detail="An unexpected error occurred.",
                instance=scope.get("path", ""),
            )
            await response(scope, receive, send_wrapper)
        finally:
            state = scope.get("state") or {}
            access_log.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                learner_sub=state.get("learner_sub"),
            )
            structlog.contextvars.clear_contextvars()
            correlation_id_var.reset(token)
