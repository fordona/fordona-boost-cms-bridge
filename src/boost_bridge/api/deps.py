"""FastAPI dependency providers."""

from typing import Annotated

import structlog
from fastapi import Depends, Header, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from boost_bridge.container import Services
from boost_bridge.core.config import SUPPORTED_LOCALES, Settings
from boost_bridge.core.errors import UnauthorizedError, ValidationFailedError
from boost_bridge.core.locale import UnsupportedLocaleError, resolve_locale
from boost_bridge.core.security import Learner
from boost_bridge.services.content_service import ContentService, Served

_bearer = HTTPBearer(
    auto_error=False,
    description="Kinde access token for the Theory App.",
    scheme_name="KindeBearer",
)

_LOCAL_LEARNER = Learner(sub="local-dev", claims={})


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def get_content_service(services: Annotated[Services, Depends(get_services)]) -> ContentService:
    return services.content


async def get_current_learner(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Learner:
    if services.verifier is None:  # AUTH_ENABLED=false, local only (enforced by Settings)
        learner = _LOCAL_LEARNER
    else:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise UnauthorizedError()
        learner = await services.verifier.verify(credentials.credentials)
    request.state.learner_sub = learner.sub
    structlog.contextvars.bind_contextvars(learner_sub=learner.sub)
    return learner


def get_locale(
    settings: Annotated[Settings, Depends(get_settings)],
    locale: Annotated[
        str | None,
        Query(
            description="Content locale. If omitted, `Accept-Language` decides; "
            "the default is sv-SE.",
            examples=list(SUPPORTED_LOCALES),
        ),
    ] = None,
    accept_language: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> str:
    try:
        return resolve_locale(locale, accept_language, settings.default_locale)
    except UnsupportedLocaleError as exc:
        raise ValidationFailedError(
            str(exc),
            extra={"fieldErrors": [{"field": "locale", "location": "query", "message": str(exc)}]},
        ) from None


def serve[T](response: Response, served: Served[T], locale: str) -> T:
    """Attach response headers that describe how the content was served."""
    response.headers["Content-Language"] = locale
    response.headers["Vary"] = "Accept-Language, Authorization"
    if served.stale:
        response.headers["X-Content-Stale"] = "true"
    return served.value


CurrentLearner = Annotated[Learner, Depends(get_current_learner)]
Locale = Annotated[str, Depends(get_locale)]
Content = Annotated[ContentService, Depends(get_content_service)]
PageNumber = Annotated[int, Query(ge=1, le=10_000, description="1-based page number.")]
PageSize = Annotated[
    int, Query(alias="pageSize", ge=1, le=100, description="Items per page (max 100).")
]
