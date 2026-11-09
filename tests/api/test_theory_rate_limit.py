"""Per-learner rate limiting end to end (Plan §7.3, P6.T6)."""

import respx

from tests.conftest import Harness
from tests.factories import home_payload, readiness_payload


@respx.mock
async def test_exceeding_the_read_limit_is_429_with_retry_after(harness_factory: object) -> None:
    async with harness_factory(  # type: ignore[operator]
        rate_limit_read_per_minute=1
    ) as harness:
        harness: Harness
        harness.theory.set("get_home", home_payload())

        first = await harness.client.get("/v1/home", headers=harness.auth())
        second = await harness.client.get("/v1/home", headers=harness.auth())

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["errorCode"] == "RATE_LIMITED"
        assert int(second.headers["Retry-After"]) > 0


@respx.mock
async def test_read_and_write_limits_are_separate_buckets(harness_factory: object) -> None:
    async with harness_factory(  # type: ignore[operator]
        rate_limit_read_per_minute=1, rate_limit_write_per_minute=1
    ) as harness:
        harness: Harness
        harness.theory.set("get_home", home_payload())
        harness.theory.set(
            "start_attempt",
            {"attemptId": "1", "status": "IN_LESSON", "attemptNo": 1, "items": []},
        )

        read_response = await harness.client.get("/v1/home", headers=harness.auth())
        write_response = await harness.client.post(
            "/v1/lessons/12/attempts",
            json={"requestId": "33333333-3333-3333-3333-333333333333"},
            headers=harness.auth(),
        )

        assert read_response.status_code == 200
        assert write_response.status_code == 200


@respx.mock
async def test_buckets_are_separate_per_learner(harness_factory: object) -> None:
    async with harness_factory(  # type: ignore[operator]
        rate_limit_read_per_minute=1
    ) as harness:
        harness: Harness
        harness.theory.set("get_readiness", readiness_payload())

        first_learner = await harness.client.get(
            "/v1/readiness", headers=harness.auth(sub="learner-a")
        )
        second_learner = await harness.client.get(
            "/v1/readiness", headers=harness.auth(sub="learner-b")
        )

        assert first_learner.status_code == 200
        assert second_learner.status_code == 200
