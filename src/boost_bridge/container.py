"""Composition root: builds the process-wide services and owns their lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx

from boost_bridge.cache.attempt_refs import AttemptRefCache
from boost_bridge.cache.rate_limit import RateLimiter
from boost_bridge.cache.redis_cache import RedisCache, create_redis
from boost_bridge.clients.boost.client import BoostClient
from boost_bridge.clients.boost.client import create_http_client as create_boost_http_client
from boost_bridge.clients.engine.client import EngineClient
from boost_bridge.clients.engine.client import create_http_client as create_engine_http_client
from boost_bridge.clients.engine.theory import EngineTheoryClient
from boost_bridge.core.config import Settings
from boost_bridge.core.security import JwksCache, TokenVerifier
from boost_bridge.db.session import create_engine, ping
from boost_bridge.services.body_cache import BodyCache
from boost_bridge.services.media import build_asset_url_resolver
from boost_bridge.services.release_prefetch import ReleasePrefetchGate, ReleasePrefetchRunner
from boost_bridge.services.theory_service import TheoryService

ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class Services:
    # None only when AUTH_ENABLED=false, which Settings permits in APP_ENV=local only.
    verifier: TokenVerifier | None
    theory: TheoryService
    rate_limiter: RateLimiter
    readiness_checks: dict[str, ReadinessCheck] = field(default_factory=dict)


ServicesFactory = Callable[[Settings], AbstractAsyncContextManager[Services]]


@asynccontextmanager
async def build_services(settings: Settings) -> AsyncIterator[Services]:
    jwks_http = httpx.AsyncClient(timeout=httpx.Timeout(3.0), follow_redirects=False)
    boost_http = create_boost_http_client(settings)
    engine_http = create_engine_http_client(settings)
    redis = create_redis(settings.redis_url)
    db_engine = create_engine(settings)

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

    boost_client = BoostClient.from_settings(boost_http, settings)
    engine_client = EngineTheoryClient(
        EngineClient.from_settings(engine_http, settings),
        phase_complete_timeout=settings.engine_phase_complete_timeout,
    )
    body_cache = BodyCache(boost_client, redis_cache, batch_max_refs=settings.boost_batch_max_refs)
    attempt_refs = AttemptRefCache(redis_cache)
    resolver = build_asset_url_resolver(settings)
    prefetch_gate: ReleasePrefetchGate | None = None
    prefetch_runner: ReleasePrefetchRunner | None = None
    if settings.content_prefetch_on_release:
        prefetch_gate = ReleasePrefetchGate(redis_cache)
        prefetch_runner = ReleasePrefetchRunner(
            boost_client,
            body_cache,
            batch_max_refs=settings.boost_batch_max_refs,
            batch_delay_seconds=settings.content_prefetch_batch_delay_seconds,
        )
    theory = TheoryService(
        engine_client,
        body_cache,
        attempt_refs,
        resolver,
        prefetch_gate=prefetch_gate,
        prefetch_runner=prefetch_runner,
    )
    rate_limiter = RateLimiter(
        redis,
        read_limit_per_minute=settings.rate_limit_read_per_minute,
        write_limit_per_minute=settings.rate_limit_write_per_minute,
    )

    async def check_database() -> None:
        await ping(db_engine)

    try:
        yield Services(
            verifier=verifier,
            theory=theory,
            rate_limiter=rate_limiter,
            readiness_checks={"database": check_database, "redis": redis_cache.ping},
        )
    finally:
        await jwks_http.aclose()
        await boost_http.aclose()
        await engine_http.aclose()
        await redis.aclose()
        await db_engine.dispose()
