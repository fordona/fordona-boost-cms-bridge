"""App-level fixtures.

The route tests run the real stack (routers → service → ContentCache →
BoostClient → httpx) with only the edges replaced:

* Boost and Kinde JWKS are mocked with respx,
* Redis is fakeredis,
* the snapshot store is in memory,
* readiness checks are scripted.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx
import pytest
import respx
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi import FastAPI

from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostClient
from boost_bridge.container import Services
from boost_bridge.core.config import Settings
from boost_bridge.core.security import JwksCache, TokenVerifier
from boost_bridge.main import create_app
from boost_bridge.services.content_cache import ContentCache
from boost_bridge.services.content_service import ContentService
from boost_bridge.services.sequencing import CmsOrderSequencer, ContentSequencer
from tests.auth import AUDIENCE, ISSUER, JWKS_URI, SigningKey, jwks
from tests.fakes import FakeClock, InMemorySnapshots

BOOST = "https://boost.test"
ASSETS = "https://cdn.boost.test/assets"  # fallback when an item has no assetBaseUrl
ITEM_ASSETS = "https://assets.boost.test/a"  # factories put this on modules
SIGNING_KEY = SigningKey("test-key")


@dataclass
class Harness:
    """Handles on the doubles behind a running app."""

    app: FastAPI
    client: httpx.AsyncClient
    boost: respx.MockRouter
    snapshots: InMemorySnapshots
    redis_server: FakeServer
    clock: FakeClock
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
def sequencer() -> ContentSequencer:
    return CmsOrderSequencer()


@pytest.fixture
def harness_factory(
    sequencer: ContentSequencer,
) -> Callable[..., AbstractAsyncContextManager[Harness]]:
    @asynccontextmanager
    async def factory(**setting_overrides: object) -> AsyncIterator[Harness]:
        settings = make_settings(**setting_overrides)
        snapshots = InMemorySnapshots()
        redis_server = FakeServer()
        clock = FakeClock()
        readiness: dict[str, Exception | None] = {"database": None, "redis": None}

        with respx.mock(assert_all_called=False) as mock:
            mock.get(JWKS_URI).respond(json=jwks(SIGNING_KEY))

            @asynccontextmanager
            async def services_factory(s: Settings) -> AsyncIterator[Services]:
                async with (
                    httpx.AsyncClient(base_url=BOOST) as boost_http,
                    httpx.AsyncClient() as jwks_http,
                ):
                    redis_cache = RedisCache(
                        FakeAsyncRedis(server=redis_server),
                        hard_ttl_seconds=s.cache_hard_ttl_seconds,
                        negative_ttl_seconds=s.cache_negative_ttl_seconds,
                    )
                    cache = ContentCache(
                        BoostClient.from_settings(boost_http, s),
                        redis_cache,
                        snapshots,
                        soft_ttl_seconds=s.cache_soft_ttl_seconds,
                        clock=clock,
                    )

                    def check(name: str) -> Callable[[], Awaitable[None]]:
                        async def run() -> None:
                            if (error := readiness[name]) is not None:
                                raise error

                        return run

                    yield Services(
                        content=ContentService(cache, sequencer, asset_base_url=s.asset_base_url),
                        verifier=TokenVerifier(
                            JwksCache(jwks_http, s.kinde_jwks_uri),
                            issuer=s.kinde_issuer_uri,
                            audiences=s.kinde_audience,
                        )
                        if s.auth_enabled
                        else None,
                        readiness_checks={name: check(name) for name in readiness},
                    )
                    await cache.aclose()

            app: FastAPI = create_app(settings, services_factory)
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    yield Harness(app, client, mock, snapshots, redis_server, clock, readiness)

    return factory


@pytest.fixture
async def harness(
    harness_factory: Callable[..., AbstractAsyncContextManager[Harness]],
) -> AsyncIterator[Harness]:
    async with harness_factory() as h:
        yield h
