"""GET /v1/readiness (Plan §7.3)."""

from tests.conftest import Harness
from tests.factories import readiness_payload


async def test_readiness_returns_the_backend_summary(harness: Harness) -> None:
    harness.theory.set("get_readiness", readiness_payload())

    response = await harness.client.get("/v1/readiness", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["percent"] == 13
    assert body["units"][0]["title"] == "Fundamentals"
