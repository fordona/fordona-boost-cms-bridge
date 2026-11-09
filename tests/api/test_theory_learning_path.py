"""GET /v1/learning-path (Plan §7.3): ETag and 304."""

from tests.conftest import Harness
from tests.factories import learning_path_payload

ETAG = '"42.17.a9f3.sv-SE"'


async def test_learning_path_returns_units_with_etag(harness: Harness) -> None:
    harness.theory.set("get_learning_path", (learning_path_payload(), ETAG, False))

    response = await harness.client.get("/v1/learning-path", headers=harness.auth())

    assert response.status_code == 200
    assert response.headers["ETag"] == ETAG
    assert response.json()["units"][0]["entries"][0]["status"] == "COMPLETED"


async def test_learning_path_passes_if_none_match_and_answers_304(harness: Harness) -> None:
    harness.theory.set("get_learning_path", (None, ETAG, True))

    response = await harness.client.get(
        "/v1/learning-path", headers={**harness.auth(), "If-None-Match": ETAG}
    )

    assert response.status_code == 304
    [call] = harness.theory.calls_to("get_learning_path")
    assert call.kwargs["if_none_match"] == ETAG
