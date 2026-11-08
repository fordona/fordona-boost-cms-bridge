"""Release prefetch (Plan §9.1, §9.4, P6.T7): warm the body cache right after a
publish instead of making the first learner per question pay the Boost round
trip.

**How a "new release" is detected — a BFF-only design, no engine change
needed.** The plan says "the sync's release id is exposed to the BFF for
this", and it already is: every learning-path response's `ETag` (and the same
string under `home`'s `learningPathEtag`) is `{releaseId}.{progressVersion}.
{entitlementHash}.{locale}` (Plan §7.3/§7.4). There is no dedicated,
BFF-pollable endpoint for the release id on its own — confirmed by reading the
engine source: the only HTTP path that returns one is the platform-admin-gated
`GET /v1/platform/theory/content-report`, a heavyweight back-office report,
not a poll target, and out of this BFF-only task's reach anyway. So rather
than inventing a new engine endpoint (cross-repo, outside P6.T7's `Repo: BFF`
scope), this piggybacks on the release id the BFF already receives as normal
traffic flows through `home`/`learning-path`, with no extra engine calls of
its own.

``ReleasePrefetchGate`` does the cheap, synchronous dedup (one Redis
``SET NX``) every `home`/`learning-path` call can afford to pay even when
nothing changed. ``ReleasePrefetchRunner`` does the actual work — paging
through Boost's full lesson/question lists and warming ``BodyCache`` for each,
batched and paced — on a fire-and-forget background task, off the request
that happened to notice the release change.
"""

import asyncio
from collections.abc import Iterator

from fordona_connect.cache.redis_cache import RedisCache
from fordona_connect.clients.boost.client import BoostClient, BoostRequests
from fordona_connect.core.config import SUPPORTED_LOCALES
from fordona_connect.core.logging import get_logger
from fordona_connect.services.body_cache import BodyCache, QuestionRef

log = get_logger(__name__)

_PAGE_SIZE = 250
# A release id never recurs (content_release.release_id is a BIGSERIAL), so this
# only needs to be long enough that the same release doesn't re-trigger a prefetch
# from ordinary traffic while one is already warm — not a correctness bound, just
# housekeeping to bound how long an unused lock key lingers in Redis.
_LOCK_TTL_MS = 24 * 60 * 60 * 1000


def parse_release_id(etag: str) -> str | None:
    """The leading dot-separated segment of a learning-path ETag is the release id
    (Plan §7.3/§7.4's own format). Defensive: an unparseable or empty etag just
    means "don't prefetch", never an error — this is purely an optimization.
    """
    bare = etag.strip('"')
    release_id = bare.split(".", 1)[0]
    return release_id or None


class ReleasePrefetchGate:
    """Cheap per-request check: is this the first caller to notice ``release_id``?"""

    def __init__(self, redis_cache: RedisCache) -> None:
        self._redis = redis_cache

    async def claim(self, etag: str) -> str | None:
        release_id = parse_release_id(etag)
        if release_id is None:
            return None
        acquired = await self._redis.try_lock(_lock_key(release_id), ttl_ms=_LOCK_TTL_MS)
        return release_id if acquired else None


def _lock_key(release_id: str) -> str:
    return f"connect:v1:prefetch-lock:{release_id}"


class ReleasePrefetchRunner:
    def __init__(
        self,
        boost_client: BoostClient,
        body_cache: BodyCache,
        *,
        batch_max_refs: int,
        batch_delay_seconds: float,
    ) -> None:
        self._boost = boost_client
        self._bodies = body_cache
        self._batch_max_refs = batch_max_refs
        self._batch_delay = batch_delay_seconds

    async def run(self, release_id: str) -> None:
        log.info("release_prefetch_started", release_id=release_id)
        try:
            for locale in SUPPORTED_LOCALES:
                await self._prefetch_lessons(locale)
                await self._prefetch_questions(locale)
        except Exception:
            log.exception("release_prefetch_failed", release_id=release_id)
            return
        log.info("release_prefetch_completed", release_id=release_id)

    async def _prefetch_lessons(self, locale: str) -> None:
        page = 1
        while True:
            result = await self._boost.fetch(
                BoostRequests.lessons(locale, page=page, page_size=_PAGE_SIZE)
            )
            for lesson in result.items:
                if lesson.version is None:
                    continue
                try:
                    await self._bodies.get_lesson_revision(lesson.id, lesson.version, locale)
                except Exception as exc:
                    log.warning(
                        "release_prefetch_lesson_failed",
                        lesson_id=lesson.id,
                        version=lesson.version,
                        error=repr(exc),
                    )
                await asyncio.sleep(self._batch_delay)
            if page * _PAGE_SIZE >= result.total:
                return
            page += 1

    async def _prefetch_questions(self, locale: str) -> None:
        refs: list[QuestionRef] = []
        page = 1
        while True:
            result = await self._boost.fetch(
                BoostRequests.questions(locale, page=page, page_size=_PAGE_SIZE)
            )
            refs.extend(
                QuestionRef(id=question.id, version=question.version)
                for question in result.items
                if question.version is not None
            )
            if page * _PAGE_SIZE >= result.total:
                break
            page += 1

        for chunk in _chunked(refs, self._batch_max_refs):
            try:
                _, missing = await self._bodies.get_question_revisions(chunk, locale)
                if missing:
                    log.warning("release_prefetch_questions_missing", count=len(missing))
            except Exception as exc:
                log.warning("release_prefetch_question_batch_failed", error=repr(exc))
            await asyncio.sleep(self._batch_delay)


def _chunked(refs: list[QuestionRef], size: int) -> Iterator[list[QuestionRef]]:
    for i in range(0, len(refs), size):
        yield refs[i : i + size]
