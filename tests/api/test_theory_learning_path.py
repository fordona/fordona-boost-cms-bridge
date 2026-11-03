"""GET /v1/learning-path (Plan §7.3): ETag/304 relayed from the engine."""

import respx

from tests.conftest import ENGINE, Harness
from tests.factories import engine_envelope, learning_path_payload


@respx.mock
async def test_learning_path_returns_units_with_etag(harness: Harness) -> None:
    harness.engine.get(f"{ENGINE}/internal/theory/v1/learning-path").respond(
        json=engine_envelope(learning_path_payload()), headers={"ETag": '"42.17.a9f3.sv-SE"'}
    )

    response = await harness.client.get("/v1/learning-path", headers=harness.auth())

    assert response.status_code == 200
    assert response.headers["ETag"] == '"42.17.a9f3.sv-SE"'
    assert response.json()["units"][0]["entries"][0]["status"] == "COMPLETED"


@respx.mock
async def test_learning_path_forwards_if_none_match_and_relays_304(harness: Harness) -> None:
    route = harness.engine.get(f"{ENGINE}/internal/theory/v1/learning-path").respond(
        304, headers={"ETag": '"42.17.a9f3.sv-SE"'}
    )

    response = await harness.client.get(
        "/v1/learning-path", headers={**harness.auth(), "If-None-Match": '"42.17.a9f3.sv-SE"'}
    )

    assert response.status_code == 304
    assert route.calls.last.request.headers["if-none-match"] == '"42.17.a9f3.sv-SE"'
