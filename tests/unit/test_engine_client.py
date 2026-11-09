"""EngineClient (service-to-service ``/internal/learning/v1/**``) against mocked responses."""

import httpx
import pytest
import respx

from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.clients.engine.errors import EnginePassthroughError
from fordona_connect.core.context import correlation_id_var, learner_token_var
from fordona_connect.core.errors import UpstreamMisconfiguredError, UpstreamUnavailableError

BASE = "https://engine.test"
LEARNER = "/internal/learning/v1/learners/kp_1"


def _payload(response: object) -> dict[str, object]:
    return {
        "code": 200,
        "status": "Success",
        "message": "Operation Successful!",
        "response": response,
    }


def _problem(*, status: int, error_code: str, detail: str = "Not found.") -> dict[str, object]:
    return {
        "type": "https://fordona.io/errors/learn/learner-not-found",
        "title": "Learner Not Found",
        "status": status,
        "detail": detail,
        "instance": LEARNER,
        "errorCode": error_code,
        "correlationId": "cid-engine-1",
    }


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=BASE) as client:
        yield client  # type: ignore[misc]


@pytest.fixture
def client(http: httpx.AsyncClient) -> EngineClient:
    return EngineClient(http, internal_token="internal-secret", default_timeout=2.0)


@respx.mock
async def test_sends_the_internal_token_and_no_learner_jwt(client: EngineClient) -> None:
    route = respx.get(f"{BASE}{LEARNER}").respond(json=_payload({"userId": "7"}))
    token = learner_token_var.set("learner-jwt")
    try:
        result = await client.get_as_service(LEARNER)
    finally:
        learner_token_var.reset(token)

    request = route.calls.last.request
    assert request.headers["x-fordona-internal-token"] == "internal-secret"
    assert "authorization" not in request.headers
    assert result.data == {"userId": "7"}


@respx.mock
async def test_query_params_and_correlation_id_are_sent(client: EngineClient) -> None:
    route = respx.get(f"{BASE}/internal/learning/v1/events").respond(json=_payload({"events": []}))
    token = correlation_id_var.set("cid-123")
    try:
        await client.get_as_service(
            "/internal/learning/v1/events", params={"after": "5", "limit": "100"}
        )
    finally:
        correlation_id_var.reset(token)

    request = route.calls.last.request
    assert request.url.params["after"] == "5"
    assert request.url.params["limit"] == "100"
    assert request.headers["x-correlation-id"] == "cid-123"


@respx.mock
async def test_rfc7807_error_passes_through_with_engine_fields(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").respond(
        404, json=_problem(status=404, error_code="LEARNER_NOT_FOUND")
    )

    with pytest.raises(EnginePassthroughError) as exc_info:
        await client.get_as_service(LEARNER)

    error = exc_info.value
    assert error.status_code == 404
    assert error.error_code == "LEARNER_NOT_FOUND"
    assert error.detail == "Not found."
    assert error.type_path == "learn/learner-not-found"


@pytest.mark.parametrize("status", [401, 403])
@respx.mock
async def test_bare_auth_rejection_is_misconfigured(client: EngineClient, status: int) -> None:
    # 401: the engine wants a JWT (no permitAll for /internal/learning/**).
    # 403: the engine's internal-token filter rejected our token.
    respx.get(f"{BASE}{LEARNER}").respond(status, text="")

    with pytest.raises(UpstreamMisconfiguredError):
        await client.get_as_service(LEARNER)


@respx.mock
async def test_unparseable_5xx_body_is_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").respond(503, text="Service Unavailable")

    with pytest.raises(UpstreamUnavailableError):
        await client.get_as_service(LEARNER)


@respx.mock
async def test_timeout_becomes_upstream_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(UpstreamUnavailableError):
        await client.get_as_service(LEARNER)


@respx.mock
async def test_connection_error_becomes_upstream_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await client.get_as_service(LEARNER)


@respx.mock
async def test_non_json_200_is_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").respond(200, text="not json")

    with pytest.raises(UpstreamUnavailableError):
        await client.get_as_service(LEARNER)


@respx.mock
async def test_payload_envelope_missing_is_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}{LEARNER}").respond(200, json={"not": "a payload"})

    with pytest.raises(UpstreamUnavailableError):
        await client.get_as_service(LEARNER)
