"""Composition root: builds the process-wide services and owns their lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx

from boost_bridge.cache.redis_cache import RedisCache, create_redis
from boost_bridge.core.config import Settings
from boost_bridge.core.security import JwksCache, TokenVerifier
from boost_bridge.db.session import create_engine, ping

ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class Services:
    # None only when AUTH_ENABLED=false, which Settings permits in APP_ENV=local only.
    verifier: TokenVerifier | None
    readiness_checks: dict[str, ReadinessCheck] = field(default_factory=dict)


ServicesFactory = Callable[[Settings], AbstractAsyncContextManager[Services]]


@asynccontextmanager
async def build_services(settings: Settings) -> AsyncIterator[Services]:
    jwks_http = httpx.AsyncClient(timeout=httpx.Timeout(3.0), follow_redirects=False)
    redis = create_redis(settings.redis_url)
    engine = create_engine(settings)

    redis_cache = RedisCache(
        redis,
        hard_ttl_seconds=settings.cache_hard_ttl_seconds,
        negative_ttl_seconds=settings.cache_negative_ttl_seconds,
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
            verifier=verifier,
            readiness_checks={"database": check_database, "redis": redis_cache.ping},
        )
    finally:
        await jwks_http.aclose()
        await redis.aclose()
        await engine.dispose()
