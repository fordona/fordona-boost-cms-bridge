"""Application factory.

Run locally:  ``uv run uvicorn boost_bridge.main:app --reload``
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from boost_bridge import __version__
from boost_bridge.api.router import api_router
from boost_bridge.container import ServicesFactory, build_services
from boost_bridge.core.config import Settings, get_settings
from boost_bridge.core.context import CORRELATION_ID_HEADER
from boost_bridge.core.errors import register_exception_handlers
from boost_bridge.core.logging import configure_logging, get_logger
from boost_bridge.core.middleware import RequestContextMiddleware

log = get_logger(__name__)

_DESCRIPTION = """
Published Theory content (modules, lessons a.k.a. chapters, and questions) from the
Boost CMS, for the Fordona Theory App.

* Every `/v1` route requires a Kinde bearer token.
* Locale is chosen by `?locale=` or `Accept-Language` (`sv-SE` default, `en-GB`).
* Questions are **answer-free**.
* Errors are RFC 7807 `application/problem+json`, carrying `errorCode` and `correlationId`.
* `X-Content-Stale: true` marks content served from the last-known-good copy
  while Boost is unavailable.
"""


def _operation_id(route: APIRoute) -> str:
    # Stable, readable operationIds (the handler name) for frontend client generation.
    return route.name


def create_app(
    settings: Settings | None = None, services_factory: ServicesFactory = build_services
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.effective_log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with services_factory(settings) as services:
            app.state.services = services
            log.info(
                "startup",
                env=settings.app_env.value,
                auth_enabled=settings.auth_enabled,
                boost_base_url=str(settings.boost_base_url),
            )
            yield
        log.info("shutdown")

    app = FastAPI(
        title="Fordona Theory Content API",
        version=__version__,
        description=_DESCRIPTION,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    register_exception_handlers(app)
    app.include_router(api_router)

    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_methods=["GET"],
            allow_headers=["Authorization", "Accept-Language", CORRELATION_ID_HEADER],
            expose_headers=[CORRELATION_ID_HEADER, "X-Content-Stale", "Content-Language"],
            max_age=600,
        )
    # Added last so it is outermost: every response, CORS preflights included,
    # gets a correlation id and an access-log line.
    app.add_middleware(RequestContextMiddleware)
    return app


@cache
def _default_app() -> FastAPI:
    return create_app()


def __getattr__(name: str) -> FastAPI:
    # ``uvicorn boost_bridge.main:app`` builds the app lazily, so importing this
    # module (tests, Alembic, tooling) does not read the environment.
    if name == "app":
        return _default_app()
    raise AttributeError(name)
