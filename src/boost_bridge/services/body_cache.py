"""Body cache for Boost's immutable revision content (Plan §13, §9.1, P6.T3).

Lesson theory and question bodies, once published at a given ``version``,
never change — a different edit always bumps the version (§13.4's own
publish-time rules). So unlike ``ContentCache`` (stale-while-revalidate, a
Postgres snapshot fallback, negative caching for 404s), a body cache entry
needs none of that machinery: a hit is valid **forever** (no TTL, no
revalidation), and a miss is always refetched from Boost — there is nothing
stale to fall back to when Boost is down, only "we don't have this exact
revision yet."

A batch of refs an attempt needs (its pinned question set) is resolved in one
pass: every ref already in Redis is served from there, and everything missing
goes into as few Boost batch calls as fit within ``batch_max_refs`` per call
(Plan §13.2: "More than 100 refs returns 422" — a normal attempt's own
question count is always far below that limit, so in practice this never
needs more than one call per attempt, exactly as the plan expects).
"""

from dataclasses import dataclass

from pydantic import ValidationError

from boost_bridge.cache.keys import body_cache_key
from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.clients.boost.client import BoostClient, BoostRequests
from boost_bridge.clients.boost.errors import (
    BoostMisconfigured,
    BoostNotFound,
    BoostTimeout,
    BoostUnavailable,
    to_app_error,
)
from boost_bridge.clients.boost.models import BoostLesson, BoostQuestion
from boost_bridge.core.clock import Clock, SystemClock
from boost_bridge.core.errors import ContentNotFoundError
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_LESSON_ENTITY = "LESSON"
_QUESTION_ENTITY = "QUESTION"


@dataclass(frozen=True, slots=True)
class QuestionRef:
    id: str
    version: str


class BodyCache:
    def __init__(
        self,
        client: BoostClient,
        redis_cache: RedisCache,
        *,
        batch_max_refs: int,
        clock: Clock | None = None,
    ) -> None:
        self._client = client
        self._redis = redis_cache
        self._batch_max_refs = batch_max_refs
        self._clock = clock or SystemClock()

    async def get_lesson_revision(self, lesson_id: str, version: str, locale: str) -> BoostLesson:
        key = body_cache_key(_LESSON_ENTITY, lesson_id, version, locale)
        entry = await self._redis.get(key)
        if entry is not None:
            try:
                return BoostLesson.model_validate(entry.payload)
            except ValidationError:
                log.warning("body_cache_entry_unparseable", key=key)

        log.debug("body_cache_miss", key=key, entity=_LESSON_ENTITY)
        try:
            payload = await self._client.fetch_raw(
                BoostRequests.lesson_revision(lesson_id, version, locale)
            )
        except BoostNotFound:
            raise ContentNotFoundError() from None
        except (BoostUnavailable, BoostTimeout, BoostMisconfigured) as exc:
            raise to_app_error(exc) from exc

        await self._redis.set_forever(key, payload, fetched_at=self._clock.now())
        return BoostLesson.model_validate(payload)

    async def get_question_revisions(
        self, refs: list[QuestionRef], locale: str
    ) -> tuple[dict[str, BoostQuestion], list[QuestionRef]]:
        """Returns ``(found-by-question-id, still-missing-refs)``.

        A ref Boost itself reports in its batch response's ``missing[]`` (the
        content doesn't exist or isn't published) ends up in the second list,
        logged here as a warning — dropping it from whatever gets built out of
        it (an attempt's served items, say) is the caller's decision, not this
        cache's.
        """
        found: dict[str, BoostQuestion] = {}
        to_fetch: list[QuestionRef] = []
        for ref in refs:
            key = body_cache_key(_QUESTION_ENTITY, ref.id, ref.version, locale)
            entry = await self._redis.get(key)
            if entry is None:
                to_fetch.append(ref)
                continue
            try:
                found[ref.id] = BoostQuestion.model_validate(entry.payload)
            except ValidationError:
                log.warning("body_cache_entry_unparseable", key=key)
                to_fetch.append(ref)

        if not to_fetch:
            return found, []

        log.debug(
            "body_cache_batch_miss",
            entity=_QUESTION_ENTITY,
            hit=len(refs) - len(to_fetch),
            miss=len(to_fetch),
        )
        still_missing: list[QuestionRef] = []
        for chunk in _chunked(to_fetch, self._batch_max_refs):
            items, missing_refs = await self._fetch_question_batch(chunk, locale)
            for item in items:
                found[item.id] = item
                if item.version:
                    key = body_cache_key(_QUESTION_ENTITY, item.id, item.version, locale)
                    await self._redis.set_forever(
                        key, item.model_dump(by_alias=True), fetched_at=self._clock.now()
                    )
            missing_ids = {ref_key.split(":", 1)[0] for ref_key in missing_refs}
            for ref in chunk:
                if ref.id in missing_ids:
                    log.warning(
                        "boost_question_revision_missing", question_id=ref.id, version=ref.version
                    )
                    still_missing.append(ref)

        return found, still_missing

    async def _fetch_question_batch(
        self, refs: list[QuestionRef], locale: str
    ) -> tuple[list[BoostQuestion], list[str]]:
        request = BoostRequests.question_revisions_batch(
            [(ref.id, ref.version) for ref in refs], locale
        )
        try:
            batch = await self._client.fetch(request)
        except (BoostUnavailable, BoostTimeout, BoostMisconfigured) as exc:
            raise to_app_error(exc) from exc
        return batch.items, batch.missing


def _chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
