"""GET /v1/home (Plan §7.3): one backend call, no Boost."""

from tests.conftest import Harness
from tests.factories import home_payload


async def test_home_returns_the_backend_dashboard(harness: Harness) -> None:
    harness.theory.set("get_home", home_payload())

    response = await harness.client.get(
        "/v1/home", headers={**harness.auth(), "X-Timezone": "Europe/Stockholm"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["firstName"] == "Samira"
    assert body["continue"]["action"] == "START"
    assert body["tabs"]["mockExams"]["locked"] is True
    [call] = harness.theory.calls_to("get_home")
    assert call.kwargs["timezone"] == "Europe/Stockholm"


async def test_home_without_token_is_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/home")

    assert response.status_code == 401
    assert response.json()["errorCode"] == "UNAUTHORIZED"
