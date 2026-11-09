"""FastAPI dependency providers."""

from typing import Annotated, Literal

import structlog
from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fordona_connect.container import Services
from fordona_connect.core.config import SUPPORTED_LOCALES, Settings
from fordona_connect.core.context import learner_id_var, learner_token_var
from fordona_connect.core.errors import RateLimitedError, UnauthorizedError, ValidationFailedError
from fordona_connect.core.locale import UnsupportedLocaleError, resolve_locale
from fordona_connect.core.logging import get_logger
from fordona_connect.core.security import Learner
from fordona_connect.learning_journey.service import LearningJourneyService
from fordona_connect.services.theory_service import TheoryService

log = get_logger(__name__)

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


async def get_current_learner(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Learner:
    if services.verifier is None:  # AUTH_ENABLED=false, local only (enforced by Settings)
        learner = _LOCAL_LEARNER
    else:
        if credentials is None or credentials.scheme.lower() != "bearer":
            log.warning("token_rejected", reason="missing_bearer_token")
            raise UnauthorizedError()
        learner = await services.verifier.verify(credentials.credentials)
        # Only a token that passed verification is ever forwarded to Boost.
        learner_token_var.set(credentials.credentials)
    request.state.learner_sub = learner.sub
    learner_id_var.set(learner.sub)
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


def get_timezone(
    x_timezone: Annotated[str | None, Header(alias="X-Timezone", include_in_schema=False)] = None,
) -> str | None:
    """Forwarded to the engine as-is (Plan §7.4) — the engine, not the BFF, validates
    it against the IANA database.
    """
    return x_timezone


def get_theory_service(services: Annotated[Services, Depends(get_services)]) -> TheoryService:
    return services.theory


def get_learning_journey_service(
    services: Annotated[Services, Depends(get_services)],
) -> LearningJourneyService:
    return services.learning_journey


async def _enforce_rate_limit(
    kind: Literal["read", "write"], learner: Learner, services: Services
) -> None:
    result = await services.rate_limiter.check(learner.sub, kind)
    if not result.allowed:
        raise RateLimitedError(result.retry_after_seconds)


async def enforce_read_rate_limit(
    learner: Annotated[Learner, Depends(get_current_learner)],
    services: Annotated[Services, Depends(get_services)],
) -> None:
    await _enforce_rate_limit("read", learner, services)


async def enforce_write_rate_limit(
    learner: Annotated[Learner, Depends(get_current_learner)],
    services: Annotated[Services, Depends(get_services)],
) -> None:
    await _enforce_rate_limit("write", learner, services)


CurrentLearner = Annotated[Learner, Depends(get_current_learner)]
Locale = Annotated[str, Depends(get_locale)]
Timezone = Annotated[str | None, Depends(get_timezone)]
Theory = Annotated[TheoryService, Depends(get_theory_service)]
LearningJourney = Annotated[LearningJourneyService, Depends(get_learning_journey_service)]
ReadRateLimit = Annotated[None, Depends(enforce_read_rate_limit)]
WriteRateLimit = Annotated[None, Depends(enforce_write_rate_limit)]
