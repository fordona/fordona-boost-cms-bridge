"""Composition root: builds the process-wide services and owns their lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

import httpx

from fordona_connect.cache.attempt_refs import AttemptRefCache
from fordona_connect.cache.rate_limit import RateLimiter
from fordona_connect.cache.redis_cache import RedisCache, create_redis
from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.clients.boost.client import create_http_client as create_boost_http_client
from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.clients.engine.client import create_http_client as create_engine_http_client
from fordona_connect.clients.engine.theory import EngineTheoryClient
from fordona_connect.core.config import SUPPORTED_LOCALES, Settings
from fordona_connect.core.security import JwksCache, TokenVerifier
from fordona_connect.db.session import create_engine, create_sessionmaker, ping
from fordona_connect.learning.content.sync import ContentSyncRunner, ContentSyncService
from fordona_connect.learning_journey.repository import LearningJourneyRepository
from fordona_connect.learning_journey.service import LearningJourneyService
from fordona_connect.services.body_cache import BodyCache
from fordona_connect.services.media import build_asset_url_resolver
from fordona_connect.services.release_prefetch import ReleasePrefetchGate, ReleasePrefetchRunner
from fordona_connect.services.theory_service import TheoryService

ReadinessCheck = Callable[[], Awaitable[None]]

# The background content sync lists whole catalogues: generous limits per call,
# unlike request handling, which uses the tight plan timeouts.
_SYNC_READ_TIMEOUT_SECONDS = 20.0
_SYNC_CALL_BUDGET_SECONDS = 60.0


@dataclass(slots=True)
class Services:
    # None only when AUTH_ENABLED=false, which Settings permits in APP_ENV=local only.
    verifier: TokenVerifier | None
    theory: TheoryService
    learning_journey: LearningJourneyService
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
    sync_http = create_boost_http_client(settings, read_timeout=_SYNC_READ_TIMEOUT_SECONDS)
    raw_engine_client = EngineClient.from_settings(engine_http, settings)
    engine_client = EngineTheoryClient(
        raw_engine_client,
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
    db_sessionmaker = create_sessionmaker(db_engine)
    learning_journey = LearningJourneyService(
        LearningJourneyRepository(db_sessionmaker), raw_engine_client
    )

    content_sync = ContentSyncService(
        db_sessionmaker,
        BoostClient(
            sync_http,
            token=settings.boost_delivery_token.get_secret_value() or None,
            grading_token=settings.boost_grading_token.get_secret_value() or None,
            max_retries=settings.boost_max_retries,
            total_budget=_SYNC_CALL_BUDGET_SECONDS,
        ),
        locales=SUPPORTED_LOCALES,
        default_locale=SUPPORTED_LOCALES[0],
        page_size=settings.content_page_size,
    )
    sync_runner = (
        ContentSyncRunner(content_sync, settings.content_sync_interval_seconds)
        if settings.content_sync_interval_seconds > 0
        else None
    )

    async def check_database() -> None:
        await ping(db_engine)

    if sync_runner is not None:
        sync_runner.start()
    try:
        yield Services(
            verifier=verifier,
            theory=theory,
            learning_journey=learning_journey,
            rate_limiter=rate_limiter,
            readiness_checks={"database": check_database, "redis": redis_cache.ping},
        )
    finally:
        if sync_runner is not None:
            await sync_runner.stop()
        await jwks_http.aclose()
        await sync_http.aclose()
        await boost_http.aclose()
        await engine_http.aclose()
        await redis.aclose()
        await db_engine.dispose()
