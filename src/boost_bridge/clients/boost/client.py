"""Async client for the Boost **delivery** API.

Only the delivery surface is used. It serves published content with answers
stripped out. Editorial routes return drafts and answers, and grading routes
need a separate credential (see design doc §2).

A call is described by a ``BoostRequest[T]`` (path, params, locale, response
model). ``fetch_raw`` executes it and returns validated JSON. The cache stores
that raw JSON, and ``BoostRequest.parse`` turns it into ``T``. Keeping the two
apart means cached data is re-parsed by the current code on every read.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from boost_bridge.clients.boost.errors import (
    BoostError,
    BoostMisconfigured,
    BoostNotFound,
    BoostTimeout,
    BoostUnavailable,
)
from boost_bridge.clients.boost.models import (
    BoostLesson,
    BoostModel,
    BoostModule,
    BoostPage,
    BoostProblem,
    BoostQuestion,
)
from boost_bridge.core.config import Settings
from boost_bridge.core.context import CORRELATION_ID_HEADER, get_correlation_id
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_BACKOFF_BASE_SECONDS = 0.1
_BACKOFF_CAP_SECONDS = 2.0
_RETRY_AFTER_CAP_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class BoostRequest[T: BoostModel]:
    """One cacheable delivery call and the model its response parses into."""

    resource: str
    path: str
    locale: str
    model: type[T]
    params: tuple[tuple[str, str], ...] = field(default=())

    def query(self) -> list[tuple[str, str | int | float | bool | None]]:
        return [("locale", self.locale), *self.params]

    def parse(self, payload: Any) -> T:
        return self.model.model_validate(payload)


def _params(**values: str | int | None) -> tuple[tuple[str, str], ...]:
    """Drop unset values and sort, so equal requests produce equal cache keys."""
    return tuple(sorted((key, str(value)) for key, value in values.items() if value is not None))


class BoostRequests:
    """Factory for every delivery call the service makes.

    Query parameter names follow Boost's spec (``pageSize``, ``moduleId`` ...).
    """

    @staticmethod
    def modules(
        locale: str, *, page: int, page_size: int, slug: str | None = None
    ) -> BoostRequest[BoostPage[BoostModule]]:
        return BoostRequest(
            resource="module_list",
            path="/v1/delivery/modules",
            locale=locale,
            model=BoostPage[BoostModule],
            params=_params(page=page, pageSize=page_size, slug=slug),
        )

    @staticmethod
    def module(module_id: str, locale: str) -> BoostRequest[BoostModule]:
        return BoostRequest(
            resource="module",
            path=f"/v1/delivery/modules/{module_id}",
            locale=locale,
            model=BoostModule,
        )

    @staticmethod
    def lessons(
        locale: str,
        *,
        page: int,
        page_size: int,
        module_id: str | None = None,
        slug: str | None = None,
    ) -> BoostRequest[BoostPage[BoostLesson]]:
        return BoostRequest(
            resource="lesson_list",
            path="/v1/delivery/lessons",
            locale=locale,
            model=BoostPage[BoostLesson],
            params=_params(page=page, pageSize=page_size, moduleId=module_id, slug=slug),
        )

    @staticmethod
    def lesson(lesson_id: str, locale: str) -> BoostRequest[BoostLesson]:
        return BoostRequest(
            resource="lesson",
            path=f"/v1/delivery/lessons/{lesson_id}",
            locale=locale,
            model=BoostLesson,
        )

    @staticmethod
    def questions(
        locale: str,
        *,
        page: int,
        page_size: int,
        module_id: str | None = None,
        lesson_id: str | None = None,
        ids: list[str] | None = None,
    ) -> BoostRequest[BoostPage[BoostQuestion]]:
        # UNVERIFIED: Boost's spec declares ``id`` as a single string. A
        # comma-separated list is assumed for batch lookup (design doc §12).
        id_filter = ",".join(sorted(set(ids))) if ids else None
        return BoostRequest(
            resource="question_list",
            path="/v1/delivery/questions",
            locale=locale,
            model=BoostPage[BoostQuestion],
            params=_params(
                page=page,
                pageSize=page_size,
                moduleId=module_id,
                lessonId=lesson_id,
                id=id_filter,
            ),
        )

    @staticmethod
    def question(question_id: str, locale: str) -> BoostRequest[BoostQuestion]:
        return BoostRequest(
            resource="question",
            path=f"/v1/delivery/questions/{question_id}",
            locale=locale,
            model=BoostQuestion,
        )

    @staticmethod
    def question_revision(
        question_id: str, version: str, locale: str
    ) -> BoostRequest[BoostQuestion]:
        return BoostRequest(
            resource="question_revision",
            path=f"/v1/delivery/questions/{question_id}/revisions/{version}",
            locale=locale,
            model=BoostQuestion,
        )


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """The one pooled client the process uses for Boost. Closed in the lifespan."""
    return httpx.AsyncClient(
        base_url=str(settings.boost_base_url).rstrip("/"),
        timeout=httpx.Timeout(
            connect=settings.boost_connect_timeout,
            read=settings.boost_read_timeout,
            write=settings.boost_read_timeout,
            pool=settings.boost_connect_timeout,
        ),
        limits=httpx.Limits(
            max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0
        ),
        headers={
            "Accept": "application/json",
            "User-Agent": "fordona-boost-cms-bridge/0.1",
        },
        follow_redirects=False,
    )


class BoostClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        token: str,
        max_retries: int = 2,
        total_budget: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._http = http
        self._auth_header = f"Bearer {token}"
        self._max_retries = max_retries
        self._total_budget = total_budget
        self._sleep = sleep
        self._jitter = jitter

    @classmethod
    def from_settings(cls, http: httpx.AsyncClient, settings: Settings) -> "BoostClient":
        return cls(
            http,
            token=settings.boost_delivery_token.get_secret_value(),
            max_retries=settings.boost_max_retries,
            total_budget=settings.boost_total_budget,
        )

    async def fetch[T: BoostModel](self, request: BoostRequest[T]) -> T:
        return request.parse(await self.fetch_raw(request))

    async def fetch_raw(self, request: BoostRequest[Any]) -> Any:
        """Execute ``request`` and return its JSON, already validated against its model.

        Raises one of the ``Boost*`` errors and never a raw httpx exception.
        The whole call, including retries and backoff, finishes within
        ``total_budget`` seconds.
        """
        try:
            async with asyncio.timeout(self._total_budget):
                payload = await self._get_with_retries(request)
        except TimeoutError as exc:
            log.warning("boost_budget_exhausted", path=request.path, budget=self._total_budget)
            raise BoostTimeout(f"Boost call exceeded {self._total_budget}s budget") from exc

        try:
            request.parse(payload)
        except ValidationError as exc:
            # A 200 we cannot understand is an upstream contract break. Treat it
            # as "unavailable" so callers fall back to the last good snapshot
            # instead of caching garbage.
            log.error(
                "boost_payload_invalid",
                path=request.path,
                resource=request.resource,
                errors=exc.errors(include_url=False, include_input=False)[:5],
            )
            raise BoostUnavailable(
                "Boost returned a payload that does not match the model"
            ) from exc
        return payload

    async def _get_with_retries(self, request: BoostRequest[Any]) -> Any:
        headers = {"Authorization": self._auth_header}
        if correlation_id := get_correlation_id():
            headers[CORRELATION_ID_HEADER] = correlation_id

        attempt = 0
        while True:
            try:
                response = await self._http.get(
                    request.path, params=request.query(), headers=headers
                )
            except httpx.TimeoutException as exc:
                error: BoostError = BoostTimeout(f"Boost timed out: {exc!r}")
                retry_after = None
            except httpx.TransportError as exc:
                error = BoostUnavailable(f"Boost unreachable: {exc!r}")
                retry_after = None
            else:
                if response.status_code == 200:
                    return self._json(response, request)
                error = self._classify(response, request)
                if response.status_code not in _RETRYABLE_STATUS:
                    raise error
                retry_after = error.retry_after if isinstance(error, BoostUnavailable) else None

            if attempt >= self._max_retries:
                raise error
            delay = self._backoff(attempt, retry_after)
            log.info(
                "boost_retry",
                path=request.path,
                attempt=attempt + 1,
                delay_s=round(delay, 3),
                reason=type(error).__name__,
                status=error.status,
            )
            await self._sleep(delay)
            attempt += 1

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, _RETRY_AFTER_CAP_SECONDS)
        ceiling: float = min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2**attempt))
        return ceiling * self._jitter()  # full jitter

    @staticmethod
    def _json(response: httpx.Response, request: BoostRequest[Any]) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            log.error("boost_non_json_response", path=request.path)
            raise BoostUnavailable("Boost returned a non-JSON body", status=200) from exc

    @staticmethod
    def _classify(
        response: httpx.Response, request: BoostRequest[Any]
    ) -> BoostNotFound | BoostMisconfigured | BoostUnavailable:
        problem = _problem(response)
        status = response.status_code
        code, request_id = problem.code, problem.request_id
        message = f"Boost {status} for {request.path}"

        if status == 404:
            return BoostNotFound(message, status=status, code=code, request_id=request_id)
        if status in _RETRYABLE_STATUS or status >= 500:
            log.warning(
                "boost_unavailable",
                path=request.path,
                status=status,
                code=code,
                boost_request_id=request_id,
            )
            return BoostUnavailable(
                message,
                retry_after=_retry_after(response),
                status=status,
                code=code,
                request_id=request_id,
            )
        # 400/401/403/409/422/428: our credential or our request is wrong.
        log.error(
            "boost_rejected_request",
            path=request.path,
            status=status,
            code=code,
            detail=problem.detail,
            boost_request_id=request_id,
        )
        return BoostMisconfigured(message, status=status, code=code, request_id=request_id)


def _problem(response: httpx.Response) -> BoostProblem:
    try:
        return BoostProblem.model_validate(response.json())
    except (ValueError, ValidationError):
        return BoostProblem()


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # HTTP-date form; fall back to our own backoff
