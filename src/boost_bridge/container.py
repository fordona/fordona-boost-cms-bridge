"""Composition root: builds the process-wide services and owns their lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx

from boost_bridge.cache.redis_cache import RedisCache, create_redis
from boost_bridge.clients.boost.client import BoostClient, create_http_client
from boost_bridge.core.config import Settings
from boost_bridge.core.security import JwksCache, TokenVerifier
from boost_bridge.db.session import create_engine, create_sessionmaker, ping
from boost_bridge.db.snapshot_repository import SnapshotRepository
from boost_bridge.services.content_cache import ContentCache
from boost_bridge.services.content_service import ContentService
from boost_bridge.services.sequencing import CmsOrderSequencer

ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class Services:
    content: ContentService
    # None only when AUTH_ENABLED=false, which Settings permits in APP_ENV=local only.
    verifier: TokenVerifier | None
    readiness_checks: dict[str, ReadinessCheck] = field(default_factory=dict)


ServicesFactory = Callable[[Settings], AbstractAsyncContextManager[Services]]


@asynccontextmanager
async def build_services(settings: Settings) -> AsyncIterator[Services]:
    boost_http = create_http_client(settings)
    jwks_http = httpx.AsyncClient(timeout=httpx.Timeout(3.0), follow_redirects=False)
    redis = create_redis(settings.redis_url)
    engine = create_engine(settings)

    redis_cache = RedisCache(
        redis,
        hard_ttl_seconds=settings.cache_hard_ttl_seconds,
        negative_ttl_seconds=settings.cache_negative_ttl_seconds,
    )
    cache = ContentCache(
        BoostClient.from_settings(boost_http, settings),
        redis_cache,
        SnapshotRepository(create_sessionmaker(engine)),
        soft_ttl_seconds=settings.cache_soft_ttl_seconds,
    )
    verifier = (
        TokenVerifier(
            JwksCache(jwks_http, settings.kinde_jwks_uri),
            issuer=settings.kinde_issuer_uri,
            audiences=settings.kinde_audience,
        )
        if settings.auth_enabled
        else None
    )

    async def check_database() -> None:
        await ping(engine)

    try:
        yield Services(
            # Recommendation engine slot: swap CmsOrderSequencer here (services/sequencing.py).
            content=ContentService(
                cache, CmsOrderSequencer(), asset_base_url=settings.asset_base_url
            ),
            verifier=verifier,
            readiness_checks={"database": check_database, "redis": redis_cache.ping},
        )
    finally:
        await cache.aclose()
        await boost_http.aclose()
        await jwks_http.aclose()
        await redis.aclose()
        await engine.dispose()
