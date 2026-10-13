"""BoostClient against mocked upstream responses (respx)."""

import httpx
import pytest
import respx

from boost_bridge.clients.boost.client import BoostClient, BoostRequests
from boost_bridge.clients.boost.errors import (
    BoostMisconfigured,
    BoostNotFound,
    BoostTimeout,
    BoostUnavailable,
)
from boost_bridge.core.context import correlation_id_var, learner_token_var
from tests.factories import module_payload, page_payload, problem_payload, question_payload

BASE = "https://boost.test"


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.calls.append(delay)


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=BASE) as client:
        yield client  # type: ignore[misc]


@pytest.fixture
def sleep() -> RecordingSleep:
    return RecordingSleep()


@pytest.fixture
def client(http: httpx.AsyncClient, sleep: RecordingSleep) -> BoostClient:
    return BoostClient(http, token="svc-token", max_retries=2, sleep=sleep, jitter=lambda: 0.5)


@respx.mock
async def test_fetch_parses_module_and_sends_auth_and_locale(client: BoostClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())

    module = await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert module.id == "1"
    assert module.translation is not None
    assert module.translation.title == "Trafikregler"
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer svc-token"
    assert request.url.params["locale"] == "sv-SE"


@respx.mock
async def test_list_params_use_boost_names(client: BoostClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/questions").respond(
        json=page_payload([question_payload()])
    )

    page = await client.fetch(
        BoostRequests.questions("en-GB", page=2, page_size=50, lesson_id="10", ids=["3", "1", "3"])
    )

    assert page.items[0].id == "100"
    params = route.calls.last.request.url.params
    assert params["pageSize"] == "50"
    assert params["page"] == "2"
    assert params["lessonId"] == "10"
    assert params["id"] == "1,3"
    assert "moduleId" not in params


@respx.mock
async def test_answer_fields_are_not_modelled(client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/questions/100").respond(json=question_payload())

    question = await client.fetch(BoostRequests.question("100", "sv-SE"))

    dumped = question.model_dump()
    assert "correct_option_id" not in dumped["shared"]
    assert "explanation" not in dumped["translation"]


@respx.mock
async def test_flat_entity_shape_is_accepted(client: BoostClient) -> None:
    flat = {"id": "1", "version": "1", "locale": "sv-SE", "title": "Flat", "iconId": "x"}
    respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=flat)

    module = await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert module.translation is not None
    assert module.translation.title == "Flat"
    assert module.shared.icon_id == "x"


@respx.mock
async def test_forwards_correlation_id(client: BoostClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())
    token = correlation_id_var.set("cid-42")
    try:
        await client.fetch(BoostRequests.module("1", "sv-SE"))
    finally:
        correlation_id_var.reset(token)
    assert route.calls.last.request.headers["X-Correlation-ID"] == "cid-42"


@respx.mock
async def test_reuses_one_connection_pool(http: httpx.AsyncClient, client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())
    await client.fetch(BoostRequests.module("1", "sv-SE"))
    await client.fetch(BoostRequests.module("1", "sv-SE"))
    assert not http.is_closed  # the injected client is shared, never re-created per call


@respx.mock
async def test_404_is_not_found_without_retry(client: BoostClient, sleep: RecordingSleep) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/9").respond(404, json=problem_payload(404))

    with pytest.raises(BoostNotFound) as exc_info:
        await client.fetch(BoostRequests.module("9", "sv-SE"))

    assert exc_info.value.request_id == "boost-req-1"
    assert route.call_count == 1
    assert sleep.calls == []


@pytest.mark.parametrize("status", [400, 401, 403, 422])
@respx.mock
async def test_rejections_are_misconfiguration_without_retry(
    client: BoostClient, status: int
) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(status, json=problem_payload(status))

    with pytest.raises(BoostMisconfigured) as exc_info:
        await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert exc_info.value.status == status
    assert route.call_count == 1


@respx.mock
async def test_retries_transient_5xx_then_succeeds(
    client: BoostClient, sleep: RecordingSleep
) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").mock(
        side_effect=[
            httpx.Response(503, json=problem_payload(503)),
            httpx.Response(502),
            httpx.Response(200, json=module_payload()),
        ]
    )

    module = await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert module.id == "1"
    assert route.call_count == 3
    # full jitter with jitter()=0.5: 0.1*2^0*0.5, 0.1*2^1*0.5
    assert sleep.calls == pytest.approx([0.05, 0.1])


@respx.mock
async def test_gives_up_after_max_retries(client: BoostClient, sleep: RecordingSleep) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(503)

    with pytest.raises(BoostUnavailable):
        await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert route.call_count == 3
    assert len(sleep.calls) == 2


@respx.mock
async def test_plain_500_is_unavailable_but_not_retried(client: BoostClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(500)

    with pytest.raises(BoostUnavailable):
        await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert route.call_count == 1


@respx.mock
async def test_honours_retry_after_with_cap(client: BoostClient, sleep: RecordingSleep) -> None:
    respx.get(f"{BASE}/v1/delivery/modules/1").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(429, headers={"Retry-After": "120"}),
            httpx.Response(200, json=module_payload()),
        ]
    )

    await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert sleep.calls == [1.0, 2.0]


@respx.mock
async def test_timeout_is_retried_then_raised(client: BoostClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules/1").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(BoostTimeout):
        await client.fetch(BoostRequests.module("1", "sv-SE"))

    assert route.call_count == 3


@respx.mock
async def test_connection_error_is_unavailable(client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules/1").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(BoostUnavailable):
        await client.fetch(BoostRequests.module("1", "sv-SE"))


@respx.mock
async def test_total_budget_bounds_the_call(http: httpx.AsyncClient) -> None:
    async def slow_sleep(_: float) -> None:
        import asyncio

        await asyncio.sleep(1)

    client = BoostClient(http, token="t", max_retries=5, total_budget=0.05, sleep=slow_sleep)
    respx.get(f"{BASE}/v1/delivery/modules/1").respond(503)

    with pytest.raises(BoostTimeout):
        await client.fetch(BoostRequests.module("1", "sv-SE"))


@respx.mock
async def test_non_json_200_is_unavailable(client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules/1").respond(200, text="<html>oops</html>")

    with pytest.raises(BoostUnavailable):
        await client.fetch(BoostRequests.module("1", "sv-SE"))


@respx.mock
async def test_payload_violating_model_is_unavailable(client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(json={"items": "not-a-list"})

    with pytest.raises(BoostUnavailable):
        await client.fetch(BoostRequests.modules("sv-SE", page=1, page_size=20))


def test_equal_requests_have_equal_params() -> None:
    a = BoostRequests.lessons("sv-SE", page=1, page_size=20, module_id="1", slug=None)
    b = BoostRequests.lessons("sv-SE", page=1, page_size=20, module_id="1")
    assert a == b


@respx.mock
async def test_forward_mode_sends_learner_token(http: httpx.AsyncClient) -> None:
    client = BoostClient(http, token=None)
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())
    token = learner_token_var.set("learner-jwt")
    try:
        await client.fetch(BoostRequests.module("1", "sv-SE"))
    finally:
        learner_token_var.reset(token)
    assert route.calls.last.request.headers["Authorization"] == "Bearer learner-jwt"


@respx.mock
async def test_forward_mode_without_learner_token_is_misconfigured(
    http: httpx.AsyncClient,
) -> None:
    client = BoostClient(http, token=None)
    route = respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())

    with pytest.raises(BoostMisconfigured):
        await client.fetch(BoostRequests.module("1", "sv-SE"))
    assert route.call_count == 0


@respx.mock
async def test_delivery_item_asset_base_url_is_parsed(client: BoostClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules/1").respond(json=module_payload())
    module = await client.fetch(BoostRequests.module("1", "sv-SE"))
    assert module.asset_base_url == "https://assets.boost.test/a/"
