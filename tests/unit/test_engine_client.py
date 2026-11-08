"""EngineClient against mocked fordona-engine responses (respx)."""

import json

import httpx
import pytest
import respx

from fordona_connect.clients.engine.client import EngineClient
from fordona_connect.clients.engine.errors import EnginePassthroughError
from fordona_connect.core.context import correlation_id_var, learner_token_var
from fordona_connect.core.errors import UpstreamMisconfiguredError, UpstreamUnavailableError

BASE = "https://engine.test"


def _payload(response: object) -> dict[str, object]:
    return {
        "code": 200,
        "status": "Success",
        "message": "Operation Successful!",
        "response": response,
    }


def _problem(
    *,
    status: int,
    error_code: str,
    detail: str = "A business rule was violated.",
    type_path: str = "theory/lesson-locked",
) -> dict[str, object]:
    return {
        "type": f"https://fordona.io/errors/{type_path}",
        "title": "Theory Lesson Locked",
        "status": status,
        "detail": detail,
        "instance": "/internal/theory/v1/lessons/1",
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


@pytest.fixture(autouse=True)
def _learner_token() -> None:
    token = learner_token_var.set("learner-jwt")
    yield
    learner_token_var.reset(token)


@respx.mock
async def test_get_forwards_headers_and_unwraps_payload(client: EngineClient) -> None:
    route = respx.get(f"{BASE}/internal/theory/v1/lessons/1").respond(
        json=_payload({"status": "CURRENT", "locked": False})
    )

    result = await client.get(
        "/internal/theory/v1/lessons/1", accept_language="en-GB", timezone="Europe/Stockholm"
    )

    assert result.data == {"status": "CURRENT", "locked": False}
    assert result.not_modified is False
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer learner-jwt"
    assert request.headers["X-Fordona-Internal-Token"] == "internal-secret"
    assert request.headers["Accept-Language"] == "en-GB"
    assert request.headers["X-Timezone"] == "Europe/Stockholm"


@respx.mock
async def test_get_omits_optional_headers_when_not_supplied(client: EngineClient) -> None:
    route = respx.get(f"{BASE}/internal/theory/v1/home").respond(json=_payload({}))

    await client.get("/internal/theory/v1/home")

    request = route.calls.last.request
    assert "Accept-Language" not in request.headers
    assert "X-Timezone" not in request.headers


@respx.mock
async def test_forwards_correlation_id(client: EngineClient) -> None:
    route = respx.get(f"{BASE}/internal/theory/v1/home").respond(json=_payload({}))
    token = correlation_id_var.set("cid-42")
    try:
        await client.get("/internal/theory/v1/home")
    finally:
        correlation_id_var.reset(token)
    assert route.calls.last.request.headers["X-Correlation-ID"] == "cid-42"


@respx.mock
async def test_post_sends_json_body_and_unwraps_response(client: EngineClient) -> None:
    route = respx.post(f"{BASE}/internal/theory/v1/lessons/1/attempts").respond(
        json=_payload({"attemptId": "a-1", "status": "IN_LESSON"})
    )

    result = await client.post("/internal/theory/v1/lessons/1/attempts", json={"requestId": "r-1"})

    assert result.data == {"attemptId": "a-1", "status": "IN_LESSON"}
    request = route.calls.last.request
    assert json.loads(request.content) == {"requestId": "r-1"}


@respx.mock
async def test_error_passthrough_preserves_engine_fields(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/lessons/1").respond(
        403,
        json=_problem(
            status=403,
            error_code="THEORY_MODULE_LOCKED",
            detail="Unit not entitled.",
            type_path="theory/module-locked",
        ),
    )

    with pytest.raises(EnginePassthroughError) as exc_info:
        await client.get("/internal/theory/v1/lessons/1")

    error = exc_info.value
    assert error.status_code == 403
    assert error.error_code == "THEORY_MODULE_LOCKED"
    assert error.detail == "Unit not entitled."
    assert error.type_path == "theory/module-locked"


@respx.mock
async def test_404_passes_through_as_engine_error(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/attempts/x").respond(
        404, json=_problem(status=404, error_code="THEORY_ATTEMPT_NOT_FOUND")
    )

    with pytest.raises(EnginePassthroughError) as exc_info:
        await client.get("/internal/theory/v1/attempts/x")

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "THEORY_ATTEMPT_NOT_FOUND"


@respx.mock
async def test_unparseable_4xx_body_is_misconfigured(client: EngineClient) -> None:
    # e.g. a raw 403 from the engine's own internal-token filter — not RFC 7807 shaped.
    respx.get(f"{BASE}/internal/theory/v1/home").respond(403, text="Forbidden")

    with pytest.raises(UpstreamMisconfiguredError):
        await client.get("/internal/theory/v1/home")


@respx.mock
async def test_unparseable_5xx_body_is_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/home").respond(503, text="Service Unavailable")

    with pytest.raises(UpstreamUnavailableError):
        await client.get("/internal/theory/v1/home")


@respx.mock
async def test_304_passes_through_without_raising(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/learning-path").respond(
        304, headers={"ETag": '"1.2.sub.sv-SE"'}
    )

    result = await client.get("/internal/theory/v1/learning-path", if_none_match='"1.2.sub.sv-SE"')

    assert result.not_modified is True
    assert result.data is None
    assert result.etag == '"1.2.sub.sv-SE"'


@respx.mock
async def test_if_none_match_header_is_forwarded(client: EngineClient) -> None:
    route = respx.get(f"{BASE}/internal/theory/v1/learning-path").respond(
        304, headers={"ETag": '"1.0.free.sv-SE"'}
    )

    await client.get("/internal/theory/v1/learning-path", if_none_match='"1.0.free.sv-SE"')

    assert route.calls.last.request.headers["If-None-Match"] == '"1.0.free.sv-SE"'


@respx.mock
async def test_200_response_returns_etag(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/learning-path").respond(
        200, json=_payload({"units": []}), headers={"ETag": '"2.0.sub.sv-SE"'}
    )

    result = await client.get("/internal/theory/v1/learning-path")

    assert result.etag == '"2.0.sub.sv-SE"'
    assert result.not_modified is False


@respx.mock
async def test_timeout_becomes_upstream_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/home").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(UpstreamUnavailableError):
        await client.get("/internal/theory/v1/home")


@respx.mock
async def test_connection_error_becomes_upstream_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/home").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await client.get("/internal/theory/v1/home")


@respx.mock
async def test_non_json_200_is_unavailable(client: EngineClient) -> None:
    respx.get(f"{BASE}/internal/theory/v1/home").respond(200, text="not json")

    with pytest.raises(UpstreamUnavailableError):
        await client.get("/internal/theory/v1/home")


@respx.mock
async def test_payload_envelope_missing_is_unavailable(client: EngineClient) -> None:
    # Missing the required Payload<T> fields (code/status) entirely.
    respx.get(f"{BASE}/internal/theory/v1/home").respond(200, json={"not": "a payload"})

    with pytest.raises(UpstreamUnavailableError):
        await client.get("/internal/theory/v1/home")


async def test_no_learner_token_is_misconfigured(http: httpx.AsyncClient) -> None:
    client = EngineClient(http, internal_token="internal-secret", default_timeout=2.0)
    token = learner_token_var.set(None)
    try:
        with pytest.raises(UpstreamMisconfiguredError):
            await client.get("/internal/theory/v1/home")
    finally:
        learner_token_var.reset(token)


@respx.mock
async def test_phase_complete_timeout_override_is_applied(client: EngineClient) -> None:
    route = respx.post(f"{BASE}/internal/theory/v1/attempts/a-1/phases/lesson/complete").respond(
        json=_payload({"status": "COMPLETED"})
    )

    await client.post(
        "/internal/theory/v1/attempts/a-1/phases/lesson/complete", timeout_override=5.0
    )

    assert route.call_count == 1
