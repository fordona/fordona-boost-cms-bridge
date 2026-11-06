"""Application factory for the Boost stub.

Run locally:  ``uv run uvicorn boost_stub.main:app --port 8080``
Docker:       ``docker build --target boost-stub`` (CLAUDE.md, plan §4.5).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import cache

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from boost_stub import __version__
from boost_stub.config import StubSettings, get_stub_settings
from boost_stub.container import ServicesFactory, build_services
from boost_stub.logging import configure_logging, get_logger
from boost_stub.routes import (
    changes,
    content,
    grading,
    learning_journeys,
    mock_exams,
    templates,
    topics,
)

log = get_logger(__name__)

STUB_HEADER = "X-Boost-Stub"


async def _boost_problem_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    if isinstance(exc.detail, dict):
        return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
    return JSONResponse(
        {
            "status": exc.status_code,
            "code": "ERROR",
            "detail": str(exc.detail),
            "requestId": None,
            "errors": None,
        },
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        {
            "status": 422,
            "code": "VALIDATION_FAILED",
            "detail": "One or more request parameters are invalid.",
            "requestId": None,
            "errors": exc.errors(),
        },
        status_code=422,
    )


def create_app(
    settings: StubSettings | None = None, services_factory: ServicesFactory = build_services
) -> FastAPI:
    settings = settings or get_stub_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with services_factory(settings) as services:
            app.state.services = services
            log.info("stub_startup", upstream=str(settings.stub_upstream_boost_url))
            yield
        log.info("stub_shutdown")

    app = FastAPI(
        title="Fordona Boost Stub",
        version=__version__,
        description="Serves the theory first-shipment §13 contract over today's Boost "
        "(plan §4.5). Dev and staging only.",
        lifespan=lifespan,
    )
    app.add_exception_handler(StarletteHTTPException, _boost_problem_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    for router in (
        changes.router,
        templates.router,
        topics.router,
        content.router,
        grading.router,
        mock_exams.router,
        learning_journeys.router,
    ):
        app.include_router(router, prefix="/v1")

    @app.middleware("http")
    async def _mark_as_stub(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers[STUB_HEADER] = "true"
        return response

    return app


@cache
def _default_app() -> FastAPI:
    return create_app()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _default_app()
    raise AttributeError(name)
