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
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi import APIRouter, FastAPI

from fordona_connect.api.deps import CurrentLearner, Locale
from fordona_connect.cache.attempt_refs import AttemptRefCache
from fordona_connect.cache.rate_limit import RateLimiter
from fordona_connect.cache.redis_cache import RedisCache
from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.clients.boost.client import create_http_client as create_boost_http_client
from fordona_connect.container import Services
from fordona_connect.core.config import Settings
from fordona_connect.core.context import learner_token_var
from fordona_connect.core.security import JwksCache, TokenVerifier
from fordona_connect.db.session import create_engine, create_sessionmaker
from fordona_connect.learning_journey.repository import LearningJourneyRepository
from fordona_connect.learning_journey.service import LearningJourneyService
from fordona_connect.main import create_app
from fordona_connect.services.body_cache import BodyCache
from fordona_connect.services.media import build_asset_url_resolver
from fordona_connect.services.release_prefetch import ReleasePrefetchGate, ReleasePrefetchRunner
from fordona_connect.services.theory_service import TheoryService
from tests.auth import AUDIENCE, ISSUER, JWKS_URI, SigningKey, jwks
from tests.theory_backend import FakeTheoryBackend

BOOST = "https://boost.test"
ENGINE = "https://engine.test"
MEDIA = "https://media.test"
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
    theory: FakeTheoryBackend
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
        "engine_base_url": ENGINE,
        "engine_internal_token": "internal-secret",
        "media_cdn_base_url": MEDIA,
        "media_signing_key": "media-secret",
        # The background content sync would call Boost on its own; tests run it explicitly.
        "content_sync_interval_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def harness_factory() -> Callable[..., AbstractAsyncContextManager[Harness]]:
    @asynccontextmanager
    async def factory(**setting_overrides: object) -> AsyncIterator[Harness]:
        settings = make_settings(**setting_overrides)
        readiness: dict[str, Exception | None] = {"database": None, "redis": None}
        # The route/mapping tests drive TheoryService through an in-memory backend; the
        # local backend is covered end to end in tests/integration/test_local_backend.py.
        theory_backend = FakeTheoryBackend()

        with respx.mock(assert_all_called=False) as mock:
            mock.get(JWKS_URI).respond(json=jwks(SIGNING_KEY))

            @asynccontextmanager
            async def services_factory(s: Settings) -> AsyncIterator[Services]:
                async with (
                    httpx.AsyncClient() as jwks_http,
                    create_boost_http_client(s) as boost_http,
                ):
                    fake_redis = FakeAsyncRedis(server=FakeServer())
                    redis_cache = RedisCache(
                        fake_redis,
                        hard_ttl_seconds=s.cache_hard_ttl_seconds,
                        negative_ttl_seconds=s.cache_negative_ttl_seconds,
                    )
                    boost_client = BoostClient.from_settings(boost_http, s)
                    body_cache = BodyCache(
                        boost_client, redis_cache, batch_max_refs=s.boost_batch_max_refs
                    )
                    prefetch_gate: ReleasePrefetchGate | None = None
                    prefetch_runner: ReleasePrefetchRunner | None = None
                    if s.content_prefetch_on_release:
                        prefetch_gate = ReleasePrefetchGate(redis_cache)
                        prefetch_runner = ReleasePrefetchRunner(
                            boost_client,
                            body_cache,
                            batch_max_refs=s.boost_batch_max_refs,
                            batch_delay_seconds=s.content_prefetch_batch_delay_seconds,
                        )
                    theory = TheoryService(
                        theory_backend,
                        body_cache,
                        AttemptRefCache(redis_cache),
                        build_asset_url_resolver(s),
                        prefetch_gate=prefetch_gate,
                        prefetch_runner=prefetch_runner,
                    )
                    rate_limiter = RateLimiter(
                        fake_redis,
                        read_limit_per_minute=s.rate_limit_read_per_minute,
                        write_limit_per_minute=s.rate_limit_write_per_minute,
                    )
                    # Real (lazy — never actually connects unless a test calls it)
                    # learning_journey wiring, matching container.py. Tests that
                    # exercise it replace ``harness.app.state.services.learning_journey``
                    # with ``FakeLearningJourneyRepository``-backed service instead.
                    db_engine = create_engine(s)
                    from tests.learning_journey.fakes import (
                        FakeLearningJourneyRepository,
                        FakeSubscriptions,
                    )

                    content = FakeLearningJourneyRepository()
                    learning_journey = LearningJourneyService(
                        LearningJourneyRepository(create_sessionmaker(db_engine)),
                        content,
                        FakeSubscriptions(),
                    )

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
                        theory=theory,
                        learning_journey=learning_journey,
                        rate_limiter=rate_limiter,
                        readiness_checks={name: check(name) for name in readiness},
                    )

            app: FastAPI = create_app(settings, services_factory)
            app.include_router(_probe)
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    yield Harness(app, client, mock, theory_backend, readiness)

    return factory


@pytest.fixture
async def harness(
    harness_factory: Callable[..., AbstractAsyncContextManager[Harness]],
) -> AsyncIterator[Harness]:
    async with harness_factory() as h:
        yield h
