"""Async client for fordona-engine's internal theory API (``/internal/theory/v1/**``).

Plan §7.4: forwards the learner's own verified JWT (never a service token —
the engine derives the learner from it and only it), the shared
``X-Fordona-Internal-Token``, whatever ``Accept-Language``/``X-Timezone`` the
caller supplies, and the correlation id. Unwraps ``Payload<T>``. Never raises
a raw ``httpx`` exception: an engine RFC 7807 error surfaces as
``EnginePassthroughError`` with the engine's own fields unchanged; anything
else (timeout, connection failure, an unparseable body) becomes one of the
existing ``Upstream*Error``s Boost failures already resolve to, so a route
needs no engine-specific exception handling beyond what it already has.
"""

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from boost_bridge.clients.engine.errors import EnginePassthroughError
from boost_bridge.clients.engine.models import EnginePayload, EngineProblem
from boost_bridge.core.config import Settings
from boost_bridge.core.context import CORRELATION_ID_HEADER, get_correlation_id, learner_token_var
from boost_bridge.core.errors import AppError, UpstreamMisconfiguredError, UpstreamUnavailableError
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

INTERNAL_TOKEN_HEADER = "X-Fordona-Internal-Token"  # noqa: S105 - a header name, not a secret


@dataclass(frozen=True, slots=True)
class EngineResponse:
    """One unwrapped engine call. ``data`` is ``Payload<T>.response``, ``None`` on a 304."""

    data: Any
    etag: str | None
    not_modified: bool


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
        headers={"Accept": "application/json", "User-Agent": "fordona-boost-cms-bridge/0.1"},
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

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        accept_language: str | None = None,
        timezone: str | None = None,
        if_none_match: str | None = None,
        timeout_override: float | None = None,
    ) -> EngineResponse:
        headers = self._headers(accept_language, timezone)
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        response = await self._send(
            "GET", path, headers=headers, params=params, timeout_override=timeout_override
        )
        if response.status_code == 304:
            return EngineResponse(data=None, etag=response.headers.get("ETag"), not_modified=True)
        return self._unwrap(response, path)

    async def post(
        self,
        path: str,
        *,
        json: Any = None,
        accept_language: str | None = None,
        timezone: str | None = None,
        timeout_override: float | None = None,
    ) -> EngineResponse:
        headers = self._headers(accept_language, timezone)
        response = await self._send(
            "POST", path, headers=headers, json=json, timeout_override=timeout_override
        )
        return self._unwrap(response, path)

    def _headers(self, accept_language: str | None, timezone: str | None) -> dict[str, str]:
        headers = {
            INTERNAL_TOKEN_HEADER: self._internal_token,
            "Authorization": f"Bearer {self._credential()}",
        }
        if accept_language:
            headers["Accept-Language"] = accept_language
        if timezone:
            headers["X-Timezone"] = timezone
        if correlation_id := get_correlation_id():
            headers[CORRELATION_ID_HEADER] = correlation_id
        return headers

    def _credential(self) -> str:
        learner_token = learner_token_var.get()
        if not learner_token:
            # Programming error: an engine call outside an authenticated request.
            log.error("engine_no_credential")
            raise UpstreamMisconfiguredError("No learner token available to forward to the engine")
        return learner_token

    async def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout_override: float | None = None,
    ) -> httpx.Response:
        request_timeout = (
            timeout_override if timeout_override is not None else self._default_timeout
        )
        try:
            return await self._http.request(
                method,
                path,
                headers=headers,
                params=params,
                json=json,
                timeout=httpx.Timeout(request_timeout),
            )
        except httpx.TimeoutException as exc:
            # Plan §7.4: "an engine outage → 503 UPSTREAM_UNAVAILABLE" — a timeout and a
            # connection failure both mean no response ever arrived (no RFC 7807 body to
            # pass through either), so both resolve the same way for this client. Unlike
            # Boost's client, the engine client never distinguishes them as a separate
            # retryable-timeout case: the engine client doesn't retry at all (P6.T2 has
            # no retry requirement, unlike Boost's).
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
        return EngineResponse(
            data=payload.response, etag=response.headers.get("ETag"), not_modified=False
        )

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
            log.error("engine_error_body_unparseable", path=path, status=response.status_code)
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
