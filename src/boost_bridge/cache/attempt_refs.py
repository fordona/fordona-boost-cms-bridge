"""Remembers which Boost (questionId, version) a seq belongs to, per attempt.

The engine drops ``questionId``/``version`` from everything *except* the item
refs it hands back on start/resume/phase-complete (Plan §7.4: "the BFF replaces
each ref with the hydrated item and drops questionId and version"). But
``POST /v1/attempts/{attemptId}/responses`` needs exactly that pair to find the
cached question body for ``correctOption.content`` — and the engine's own
``AnswerFeedbackDTO`` carries no questionId at all, only ``seq``.

Plan §7.3's own call-count table budgets **one** engine call per route, so
re-fetching the attempt just to recover this mapping on every answer isn't an
option. Instead, hydrating an attempt's items (start/resume/phase-complete)
writes this mapping once; ``answer()`` reads it. A cold cache (eviction, a
restart between hydrate and answer) falls back to one extra
``GET .../attempts/{attemptId}`` call to repopulate it — the same
correctness-first fallback this codebase already uses for every other cache
(stale-while-revalidate, the body cache's miss path): the common case stays at
one engine call, and the rare cold case costs one more rather than ever
answering with the wrong question's body.
"""

from dataclasses import dataclass

from boost_bridge.cache.redis_cache import RedisCache
from boost_bridge.core.clock import Clock, SystemClock
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ItemRef:
    question_id: str
    version: str


def _key(attempt_id: str) -> str:
    return f"bridge:v1:attemptrefs:{attempt_id}"


class AttemptRefCache:
    """Reuses ``RedisCache``'s own hard TTL — no separate knob for this mapping."""

    def __init__(self, redis_cache: RedisCache, *, clock: Clock | None = None) -> None:
        self._redis = redis_cache
        self._clock = clock or SystemClock()

    async def remember(self, attempt_id: str, refs: dict[int, ItemRef]) -> None:
        """Merges ``refs`` (seq -> question ref) into whatever is already stored."""
        if not refs:
            return
        key = _key(attempt_id)
        existing = await self._load(key)
        existing.update({str(seq): [ref.question_id, ref.version] for seq, ref in refs.items()})
        await self._redis.set(key, existing, fetched_at=self._clock.now())

    async def get(self, attempt_id: str, seq: int) -> ItemRef | None:
        stored = await self._load(_key(attempt_id))
        entry = stored.get(str(seq))
        if entry is None:
            return None
        question_id, version = entry
        return ItemRef(question_id=question_id, version=version)

    async def _load(self, key: str) -> dict[str, list[str]]:
        entry = await self._redis.get(key)
        if entry is None or not isinstance(entry.payload, dict):
            return {}
        return dict(entry.payload)
