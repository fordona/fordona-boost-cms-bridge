"""OpenAPI documentation for the problem+json error responses each theory route
can return (Plan §7.3's own error-code table).

Most of these (404 THEORY_ATTEMPT_NOT_FOUND, the 409 conflict codes, 422
THEORY_OPTION_INVALID...) are never raised by this service — they are the
engine's own business exceptions, passed through unchanged by
``EnginePassthroughError``. They're documented here anyway so the published
OpenAPI tells a client what to expect from the whole round trip, not just the
BFF's own half of it.
"""

from typing import Any

from boost_bridge.core.errors import PROBLEM_CONTENT_TYPE
from boost_bridge.schemas.common import Problem


def _problem(description: str) -> dict[str, Any]:
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_CONTENT_TYPE: {}},
    }


_UPSTREAM_ERRORS: dict[int | str, dict[str, Any]] = {
    502: _problem("The engine or Boost rejected this service's own credential."),
    503: _problem("The engine or Boost is unavailable, and no cached copy exists."),
    504: _problem("The engine timed out."),
}

_AUTH_ERROR: dict[int | str, dict[str, Any]] = {
    401: _problem("Missing, invalid or expired access token.")
}

READ_ERRORS: dict[int | str, dict[str, Any]] = {**_AUTH_ERROR, **_UPSTREAM_ERRORS}

LESSON_DETAIL_ERRORS: dict[int | str, dict[str, Any]] = {
    **_AUTH_ERROR,
    403: _problem("THEORY_LESSON_LOCKED or THEORY_ATTEMPT_MODULE_LOCKED."),
    404: _problem("THEORY_ATTEMPT_LESSON_NOT_FOUND."),
    **_UPSTREAM_ERRORS,
}

ATTEMPT_START_ERRORS: dict[int | str, dict[str, Any]] = {
    **_AUTH_ERROR,
    403: _problem("THEORY_LESSON_LOCKED or THEORY_ATTEMPT_MODULE_LOCKED."),
    404: _problem("THEORY_ATTEMPT_LESSON_NOT_FOUND."),
    409: _problem("THEORY_REQUEST_ID_CONFLICT: requestId reused for a different lesson."),
    422: _problem("Invalid request body."),
    **_UPSTREAM_ERRORS,
}

ATTEMPT_GET_ERRORS: dict[int | str, dict[str, Any]] = {
    **_AUTH_ERROR,
    404: _problem("THEORY_ATTEMPT_NOT_FOUND: unknown id, or another learner's attempt."),
    **_UPSTREAM_ERRORS,
}

RESPONSE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_AUTH_ERROR,
    404: _problem("THEORY_ATTEMPT_NOT_FOUND or THEORY_ITEM_NOT_FOUND."),
    409: _problem("THEORY_RESPONSE_CONFLICT or THEORY_PHASE_CLOSED."),
    422: _problem("THEORY_OPTION_INVALID, or an invalid request body."),
    **_UPSTREAM_ERRORS,
}

PHASE_COMPLETE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_AUTH_ERROR,
    404: _problem("THEORY_ATTEMPT_NOT_FOUND."),
    409: _problem("THEORY_PHASE_INCOMPLETE: unanswered items remain."),
    **_UPSTREAM_ERRORS,
}
