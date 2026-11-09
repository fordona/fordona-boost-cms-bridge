"""Async client for fordona-engine's internal learning API (``/internal/learning/v1/**``).

Service-to-service only: every call carries the shared ``X-Fordona-Internal-Token``
and the correlation id, never a learner JWT, so it also works from background jobs.
Unwraps ``Payload<T>``. Never raises a raw ``httpx`` exception: an engine RFC 7807
error surfaces as ``EnginePassthroughError`` with the engine's own fields; anything
else (timeout, connection failure, an unparseable body) becomes an ``Upstream*Error``.
"""

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from fordona_connect.clients.engine.errors import EnginePassthroughError
from fordona_connect.clients.engine.models import EnginePayload, EngineProblem
from fordona_connect.core.config import Settings
from fordona_connect.core.context import CORRELATION_ID_HEADER, get_correlation_id
from fordona_connect.core.errors import (
    AppError,
    UpstreamMisconfiguredError,
    UpstreamUnavailableError,
)
from fordona_connect.core.logging import get_logger

log = get_logger(__name__)

INTERNAL_TOKEN_HEADER = "X-Fordona-Internal-Token"  # noqa: S105 - a header name, not a secret

# What a bare (non-RFC 7807) engine rejection usually means.
_HINTS = {
    401: "the engine asked for a JWT: it does not permit /internal/learning/** yet "
    "(deploy the engine's learning platform API)",
    403: "the engine rejected X-Fordona-Internal-Token: ENGINE_INTERNAL_TOKEN here must "
    "equal the engine's THEORY_INTERNAL_TOKEN",
}


@dataclass(frozen=True, slots=True)
class EngineResponse:
    """One unwrapped engine call. ``data`` is ``Payload<T>.response``."""

    data: Any


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """The one pooled client the process uses for the engine. Closed in the lifespan."""
    return httpx.AsyncClient(
        base_url=str(settings.engine_base_url).rstrip("/"),
        timeout=httpx.Timeout(
            connect=settings.engine_read_timeout,
            read=settings.engine_read_timeout,
            write=settings.engine_read_timeout,
            pool=settings.engine_read_timeout,
        ),
        limits=httpx.Limits(
            max_connections=settings.engine_pool_max_connections,
            max_keepalive_connections=settings.engine_pool_max_connections,
            keepalive_expiry=30.0,
        ),
        headers={"Accept": "application/json", "User-Agent": "fordona-connect/0.1"},
        follow_redirects=False,
    )


class EngineClient:
    def __init__(
        self, http: httpx.AsyncClient, *, internal_token: str, default_timeout: float
    ) -> None:
        self._http = http
        self._internal_token = internal_token
        self._default_timeout = default_timeout

    @classmethod
    def from_settings(cls, http: httpx.AsyncClient, settings: Settings) -> "EngineClient":
        return cls(
            http,
            internal_token=settings.engine_internal_token.get_secret_value(),
            default_timeout=settings.engine_read_timeout,
        )

    async def get_as_service(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> EngineResponse:
        """A service-to-service GET: the internal token only, no learner JWT."""
        headers = {INTERNAL_TOKEN_HEADER: self._internal_token}
        if correlation_id := get_correlation_id():
            headers[CORRELATION_ID_HEADER] = correlation_id
        response = await self._send("GET", path, headers=headers, params=params)
        return self._unwrap(response, path)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_timeout = self._default_timeout
        try:
            return await self._http.request(
                method,
                path,
                headers=headers,
                params=params,
                timeout=httpx.Timeout(request_timeout),
            )
        except httpx.TimeoutException as exc:
            # A timeout and a connection failure both mean no response arrived; the
            # engine client does not retry.
            log.warning("engine_timeout", path=path, timeout=request_timeout)
            raise UpstreamUnavailableError() from exc
        except httpx.TransportError as exc:
            log.warning("engine_unavailable", path=path, error=repr(exc))
            raise UpstreamUnavailableError() from exc

    def _unwrap(self, response: httpx.Response, path: str) -> EngineResponse:
        if response.status_code >= 400:
            raise self._classify_error(response, path)
        try:
            payload = EnginePayload.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            log.error("engine_payload_invalid", path=path, status=response.status_code)
            raise UpstreamUnavailableError(
                "The engine returned a payload that could not be parsed"
            ) from exc
        return EngineResponse(data=payload.response)

    def _classify_error(self, response: httpx.Response, path: str) -> AppError:
        try:
            problem = EngineProblem.model_validate(response.json())
        except (ValueError, ValidationError):
            problem = None

        # A non-RFC-7807 body (e.g. a raw 403 from the engine's own internal-token
        # filter, which runs before Spring's exception handling) parses to all-None
        # fields and must not be passed through as if it were a real business error.
        if (
            problem is None
            or problem.status is None
            or problem.error_code is None
            or problem.detail is None
        ):
            if response.status_code >= 500:
                log.warning("engine_unavailable", path=path, status=response.status_code)
                return UpstreamUnavailableError()
            log.error(
                "engine_error_body_unparseable",
                path=path,
                status=response.status_code,
                hint=_HINTS.get(response.status_code),
            )
            return UpstreamMisconfiguredError(
                f"Engine {response.status_code} for {path} returned no parseable error body"
            )

        log.warning(
            "engine_error_passthrough",
            path=path,
            status=problem.status,
            error_code=problem.error_code,
        )
        return EnginePassthroughError(
            status=problem.status,
            error_code=problem.error_code,
            detail=problem.detail,
            type_path=problem.type or "",
        )
