"""GET /v1/home (Plan §7.3): one engine call, no Boost."""

import respx

from tests.conftest import ENGINE, Harness
from tests.factories import engine_envelope, home_payload


@respx.mock
async def test_home_passes_through_engine_dashboard(harness: Harness) -> None:
    route = harness.engine.get(f"{ENGINE}/internal/theory/v1/home").respond(
        json=engine_envelope(home_payload())
    )

    response = await harness.client.get(
        "/v1/home", headers={**harness.auth(), "X-Timezone": "Europe/Stockholm"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["firstName"] == "Samira"
    assert body["continue"]["action"] == "START"
    assert body["tabs"]["mockExams"]["locked"] is True
    assert route.calls.last.request.headers["x-timezone"] == "Europe/Stockholm"
    assert route.calls.last.request.headers["x-fordona-internal-token"] == "internal-secret"


async def test_home_without_token_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/home")

    assert response.status_code == 401
    assert response.json()["errorCode"] == "UNAUTHORIZED"
