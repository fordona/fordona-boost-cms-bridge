"""OpenAPI documentation for the problem+json error responses each route can return."""

from typing import Any

from boost_bridge.core.errors import PROBLEM_CONTENT_TYPE
from boost_bridge.schemas.common import Problem


def _problem(description: str) -> dict[str, Any]:
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_CONTENT_TYPE: {}},
    }


CONTENT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _problem("Missing, invalid or expired access token."),
    404: _problem("Content does not exist or is not published in this locale."),
    422: _problem("Invalid path, query or locale parameter."),
    502: _problem("Boost rejected the service's credential and no fallback copy exists."),
    503: _problem("Boost is unavailable and no fallback copy exists."),
    504: _problem("Boost timed out and no fallback copy exists."),
}

LIST_ERRORS: dict[int | str, dict[str, Any]] = {
    code: spec for code, spec in CONTENT_ERRORS.items() if code != 404
}
