"""App-level fixtures.

The API tests run the real app (middleware, error handlers, auth and locale
dependencies, health routes) with only the edges replaced:

* Kinde JWKS (and any Boost call) is mocked with respx,
* readiness checks are scripted.

Until the public theory API ships (plan §7.3, P6), the app has no ``/v1``
route. The harness therefore mounts ``PROBE_PATH``, a **test-only** route that
depends on the real ``CurrentLearner`` and ``Locale`` dependencies, so the
authentication boundary is still exercised end to end through HTTP.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx
import pytest
import respx
from fastapi import APIRouter, FastAPI

from boost_bridge.api.deps import CurrentLearner, Locale
from boost_bridge.container import Services
from boost_bridge.core.config import Settings
from boost_bridge.core.context import learner_token_var
from boost_bridge.core.security import JwksCache, TokenVerifier
from boost_bridge.main import create_app
from tests.auth import AUDIENCE, ISSUER, JWKS_URI, SigningKey, jwks

BOOST = "https://boost.test"
ASSETS = "https://cdn.boost.test/assets"  # fallback when an item has no assetBaseUrl
SIGNING_KEY = SigningKey("test-key")
PROBE_PATH = "/v1/__probe"

_probe = APIRouter()


@_probe.get(PROBE_PATH)
async def probe(learner: CurrentLearner, locale: Locale) -> dict[str, object]:
    """Echo what the auth and locale dependencies resolved for this request."""
    return {
        "sub": learner.sub,
        "locale": locale,
        "tokenForwardable": learner_token_var.get(None) is not None,
    }


@dataclass
class Harness:
    """Handles on the doubles behind a running app."""

    app: FastAPI
    client: httpx.AsyncClient
    boost: respx.MockRouter
    readiness: dict[str, Exception | None] = field(default_factory=dict)

    def auth(self, **claims: object) -> dict[str, str]:
        return {"Authorization": f"Bearer {SIGNING_KEY.token(**claims)}"}


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "local",
        "log_level": "WARNING",
        "boost_base_url": BOOST,
        "boost_asset_base_url": ASSETS,
        "boost_auth_mode": "service_token",
        "boost_delivery_token": "svc-token",
        "boost_max_retries": 0,
        "auth_enabled": True,
        "kinde_issuer_uri": ISSUER,
        "kinde_jwks_uri": JWKS_URI,
        "kinde_audience": AUDIENCE,
        "cors_allowed_origins": "https://theory.fordona.test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def harness_factory() -> Callable[..., AbstractAsyncContextManager[Harness]]:
    @asynccontextmanager
    async def factory(**setting_overrides: object) -> AsyncIterator[Harness]:
        settings = make_settings(**setting_overrides)
        readiness: dict[str, Exception | None] = {"database": None, "redis": None}

        with respx.mock(assert_all_called=False) as mock:
            mock.get(JWKS_URI).respond(json=jwks(SIGNING_KEY))

            @asynccontextmanager
            async def services_factory(s: Settings) -> AsyncIterator[Services]:
                async with httpx.AsyncClient() as jwks_http:

                    def check(name: str) -> Callable[[], Awaitable[None]]:
                        async def run() -> None:
                            if (error := readiness[name]) is not None:
                                raise error

                        return run

                    yield Services(
                        verifier=TokenVerifier(
                            JwksCache(jwks_http, s.kinde_jwks_uri),
                            issuer=s.kinde_issuer_uri,
                            audiences=s.kinde_audience,
                        )
                        if s.auth_enabled
                        else None,
                        readiness_checks={name: check(name) for name in readiness},
                    )

            app: FastAPI = create_app(settings, services_factory)
            app.include_router(_probe)
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    yield Harness(app, client, mock, readiness)

    return factory


@pytest.fixture
async def harness(
    harness_factory: Callable[..., AbstractAsyncContextManager[Harness]],
) -> AsyncIterator[Harness]:
    async with harness_factory() as h:
        yield h
