"""Fail-open Redis wrapper.

Redis is an accelerator, never a dependency of correctness. Every operation
has a short socket timeout, and every failure is logged and reported as a miss,
a skipped write, or a lock not taken. None of them reach the request as an
error.
"""

import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_ENVELOPE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CacheEntry:
    payload: Any
    fetched_at: float
    negative: bool = False


def create_redis(url: str, *, socket_timeout: float = 0.5) -> "Redis":
    # No client-side retries: a retry loop around a 0.5s timeout would turn a
    # Redis outage into seconds of added latency on every request.
    return Redis.from_url(
        url,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
        health_check_interval=30,
    )


class RedisCache:
    def __init__(self, redis: "Redis", *, hard_ttl_seconds: int, negative_ttl_seconds: int) -> None:
        self._redis = redis
        self._hard_ttl = hard_ttl_seconds
        self._negative_ttl = negative_ttl_seconds

    async def get(self, key: str) -> CacheEntry | None:
        try:
            raw = await self._redis.get(key)
        except (RedisError, OSError) as exc:
            log.warning("redis_get_failed", key=key, error=repr(exc))
            return None
        if raw is None:
            return None
        try:
            envelope = json.loads(raw)
            if envelope.get("v") != _ENVELOPE_VERSION:
                return None
            return CacheEntry(
                payload=envelope.get("payload"),
                fetched_at=float(envelope["fetchedAt"]),
                negative=bool(envelope.get("negative", False)),
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            log.warning("redis_entry_corrupt", key=key)
            return None

    async def set(self, key: str, payload: Any, *, fetched_at: float) -> None:
        envelope = {"v": _ENVELOPE_VERSION, "fetchedAt": fetched_at, "payload": payload}
        await self._write(key, envelope, self._hard_ttl)

    async def set_negative(self, key: str, *, fetched_at: float) -> None:
        envelope = {"v": _ENVELOPE_VERSION, "fetchedAt": fetched_at, "negative": True}
        await self._write(key, envelope, self._negative_ttl)

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except (RedisError, OSError) as exc:
            log.warning("redis_delete_failed", key=key, error=repr(exc))

    async def try_lock(self, key: str, *, ttl_ms: int) -> bool:
        """Best-effort cross-replica lock. ``False`` when held elsewhere *or* Redis is down."""
        try:
            return bool(await self._redis.set(key, b"1", nx=True, px=ttl_ms))
        except (RedisError, OSError) as exc:
            log.warning("redis_lock_failed", key=key, error=repr(exc))
            return False

    async def ping(self) -> None:
        """Raise if Redis is unreachable. Used only by readiness."""
        await self._redis.ping()

    async def _write(self, key: str, envelope: dict[str, Any], ttl: int) -> None:
        try:
            await self._redis.set(
                key, json.dumps(envelope, separators=(",", ":"), ensure_ascii=False), ex=ttl
            )
        except (RedisError, OSError) as exc:
            log.warning("redis_set_failed", key=key, error=repr(exc))
