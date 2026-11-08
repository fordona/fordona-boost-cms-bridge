"""RateLimiter: fixed one-minute window per (kind, learner) (Plan §7.3, P6.T6)."""

from fakeredis import FakeAsyncRedis, FakeServer

from fordona_connect.cache.rate_limit import RateLimiter


def _limiter(*, read_limit: int = 2, write_limit: int = 1) -> RateLimiter:
    return RateLimiter(
        FakeAsyncRedis(server=FakeServer()),
        read_limit_per_minute=read_limit,
        write_limit_per_minute=write_limit,
    )


async def test_allows_requests_within_the_limit() -> None:
    limiter = _limiter(read_limit=2)

    first = await limiter.check("learner-1", "read")
    second = await limiter.check("learner-1", "read")

    assert first.allowed is True
    assert second.allowed is True


async def test_denies_requests_once_the_limit_is_exceeded() -> None:
    limiter = _limiter(read_limit=1)

    await limiter.check("learner-1", "read")
    third = await limiter.check("learner-1", "read")

    assert third.allowed is False
    assert third.retry_after_seconds > 0


async def test_buckets_are_separate_per_learner() -> None:
    limiter = _limiter(read_limit=1)

    await limiter.check("learner-1", "read")
    other_learner = await limiter.check("learner-2", "read")

    assert other_learner.allowed is True


async def test_buckets_are_separate_per_kind() -> None:
    limiter = _limiter(read_limit=1, write_limit=1)

    await limiter.check("learner-1", "read")
    write_result = await limiter.check("learner-1", "write")

    assert write_result.allowed is True


async def test_redis_failure_fails_open() -> None:
    limiter = _limiter(read_limit=1)

    async def _boom(*args: object, **kwargs: object) -> int:
        raise ConnectionError("redis down")

    limiter._redis.incr = _boom  # type: ignore[method-assign]

    result = await limiter.check("learner-1", "read")

    assert result.allowed is True
