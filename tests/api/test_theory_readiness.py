"""GET /v1/readiness (Plan §7.3)."""

import respx

from tests.conftest import ENGINE, Harness
from tests.factories import engine_envelope, readiness_payload


@respx.mock
async def test_readiness_passes_through_engine_summary(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/readiness").respond(
        json=engine_envelope(readiness_payload())
    )

    response = await harness.client.get("/v1/readiness", headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["percent"] == 13
    assert body["units"][0]["title"] == "Fundamentals"
