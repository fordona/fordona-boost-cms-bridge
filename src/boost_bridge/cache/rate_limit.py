"""Per-learner rate limiting (Plan §7.3, P6.T6).

A fixed one-minute window counter per ``(kind, learner sub, window)``, not a
continuously-refilling token bucket — simpler to reason about with the plain
Redis primitives this codebase already uses everywhere else (``INCR``/
``EXPIRE``, no Lua script), and it satisfies the tracker's own acceptance
bullets exactly (limit reached → 429; separate buckets per learner; separate
buckets read/write). Like ``RedisCache``, this is fail-open: a Redis error
never blocks a request, it just forgoes limiting for that one check.
"""

from dataclasses import dataclass
from time import time
from typing import Literal

from redis.asyncio import Redis
from redis.exceptions import RedisError

from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_WINDOW_SECONDS = 60
Kind = Literal["read", "write"]


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


def _window_key(kind: Kind, learner_sub: str) -> str:
    window = int(time()) // _WINDOW_SECONDS
    return f"bridge:v1:ratelimit:{kind}:{learner_sub}:{window}"


class RateLimiter:
    def __init__(
        self, redis: Redis, *, read_limit_per_minute: int, write_limit_per_minute: int
    ) -> None:
        self._redis = redis
        self._limits: dict[Kind, int] = {
            "read": read_limit_per_minute,
            "write": write_limit_per_minute,
        }

    async def check(self, learner_sub: str, kind: Kind) -> RateLimitResult:
        key = _window_key(kind, learner_sub)
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, _WINDOW_SECONDS)
        except (RedisError, OSError) as exc:
            log.warning("rate_limit_check_failed", key=key, error=repr(exc))
            return RateLimitResult(allowed=True)

        limit = self._limits[kind]
        if count <= limit:
            return RateLimitResult(allowed=True)

        try:
            ttl = await self._redis.ttl(key)
        except (RedisError, OSError):
            ttl = _WINDOW_SECONDS
        return RateLimitResult(allowed=False, retry_after_seconds=max(ttl, 1))
