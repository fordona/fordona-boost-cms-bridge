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

import asyncio
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
        """Fixed 2026-11-06, confirmed against a live boost-api-dev.fordona.dev response:
        ``GET /v1/delivery/lessons/{id}/revisions/{version}`` genuinely 404s — Boost never
        implemented a lesson-revision-pinning endpoint the way it did for questions (its own
        stub's own route comment already said as much: "today's Boost has no revision history,
        only the current lesson"). This called that non-existent endpoint directly, so every
        real lesson fetch failed with ContentNotFoundError. Now fetches the plain, current lesson
        and treats a returned version that doesn't match the requested one as not-found, the same
        semantics the stub's own 404-on-mismatch behaviour already models — a lesson that changed
        on Boost since the pinned attempt started is correctly "not this revision", not silently
        served as if nothing changed.
        """
        key = body_cache_key(_LESSON_ENTITY, lesson_id, version, locale)
        entry = await self._redis.get(key)
        if entry is not None:
            try:
                return BoostLesson.model_validate(entry.payload)
            except ValidationError:
                log.warning("body_cache_entry_unparseable", key=key)

        log.debug("body_cache_miss", key=key, entity=_LESSON_ENTITY)
        try:
            payload = await self._client.fetch_raw(BoostRequests.lesson(lesson_id, locale))
        except BoostNotFound:
            raise ContentNotFoundError() from None
        except (BoostUnavailable, BoostTimeout, BoostMisconfigured) as exc:
            raise to_app_error(exc) from exc

        lesson = BoostLesson.model_validate(payload)
        if lesson.version != version:
            log.warning(
                "lesson_revision_mismatch", lesson_id=lesson_id, wanted=version, got=lesson.version
            )
            raise ContentNotFoundError()

        await self._redis.set_forever(key, payload, fetched_at=self._clock.now())
        return lesson

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
        """Fixed 2026-11-07, confirmed against the real boost-api-dev OpenAPI spec: Boost never
        implemented the batch endpoint this used to call (``GET /v1/delivery/questions/revisions``
        isn't in its spec at all — only the single-item
        ``GET /v1/delivery/questions/{id}/revisions/{version}`` is). Every attempt start therefore
        404'd on this call with an uncaught ``BoostNotFound`` (this method only handled
        BoostUnavailable/BoostTimeout/BoostMisconfigured), surfacing as a raw 500 instead of the
        per-question "missing" this cache is meant to degrade to. Fetches each ref individually
        instead, concurrently, with the same fallback semantics ``get_lesson_revision`` already
        uses: a 404 or a version mismatch is "missing", not a crash.
        """
        results = await asyncio.gather(*(self._fetch_one_question(ref, locale) for ref in refs))
        items = [question for question in results if question is not None]
        missing = [
            f"{ref.id}:{ref.version}"
            for ref, question in zip(refs, results, strict=True)
            if question is None
        ]
        return items, missing

    async def _fetch_one_question(self, ref: QuestionRef, locale: str) -> BoostQuestion | None:
        try:
            question = await self._client.fetch(
                BoostRequests.question_revision(ref.id, ref.version, locale)
            )
        except BoostNotFound:
            return None
        except (BoostUnavailable, BoostTimeout, BoostMisconfigured) as exc:
            raise to_app_error(exc) from exc
        if question.version != ref.version:
            log.warning(
                "question_revision_mismatch",
                question_id=ref.id,
                wanted=ref.version,
                got=question.version,
            )
            return None
        return question


def _chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
