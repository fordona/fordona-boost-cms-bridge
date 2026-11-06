"""The stub has no identity of its own: every token is checked against Boost (§4.5)."""

import httpx
import pytest
import respx
from fastapi.exceptions import HTTPException

from boost_stub.auth import TokenProbeCache, require_delivery_scope, require_grading_scope
from boost_stub.upstream import UpstreamClient

BASE = "https://boost.test"


@pytest.fixture
def upstream() -> UpstreamClient:
    return UpstreamClient(httpx.AsyncClient(base_url=BASE))


# --- TokenProbeCache --------------------------------------------------------------


def test_cache_starts_empty() -> None:
    cache = TokenProbeCache()
    assert cache.is_fresh("delivery", "t", now=1000.0) is False


def test_cache_is_fresh_right_after_marking() -> None:
    cache = TokenProbeCache()
    cache.mark_ok("delivery", "t", now=1000.0)
    assert cache.is_fresh("delivery", "t", now=1000.1) is True


def test_cache_expires_after_its_window() -> None:
    cache = TokenProbeCache()
    cache.mark_ok("delivery", "t", now=1000.0)
    assert cache.is_fresh("delivery", "t", now=1000.0 + 31) is False


def test_cache_is_scoped_by_token() -> None:
    cache = TokenProbeCache()
    cache.mark_ok("delivery", "token-a", now=1000.0)
    assert cache.is_fresh("delivery", "token-b", now=1000.0) is False


def test_cache_is_scoped_by_kind() -> None:
    cache = TokenProbeCache()
    cache.mark_ok("delivery", "t", now=1000.0)
    assert cache.is_fresh("grading", "t", now=1000.0) is False


def test_cache_never_stores_a_negative_result() -> None:
    # There is no mark_failed: a failed probe is simply never cached, so the
    # next request probes again rather than remembering a stale rejection.
    cache = TokenProbeCache()
    assert cache.is_fresh("delivery", "t", now=1000.0) is False


# --- require_delivery_scope --------------------------------------------------------


@respx.mock
async def test_delivery_scope_accepts_a_token_boost_accepts(upstream: UpstreamClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(200, json={"items": []})
    cache = TokenProbeCache()

    await require_delivery_scope(upstream, cache, "good-token", now=1000.0)

    assert cache.is_fresh("delivery", "good-token", now=1000.0)


@respx.mock
async def test_delivery_scope_rejects_a_token_boost_rejects(upstream: UpstreamClient) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(401)
    cache = TokenProbeCache()

    with pytest.raises(HTTPException) as exc_info:
        await require_delivery_scope(upstream, cache, "bad-token", now=1000.0)

    assert exc_info.value.status_code == 401
    assert not cache.is_fresh("delivery", "bad-token", now=1000.0)


@respx.mock
async def test_delivery_scope_does_not_probe_twice_within_the_cache_window(
    upstream: UpstreamClient,
) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules").respond(200, json={"items": []})
    cache = TokenProbeCache()

    await require_delivery_scope(upstream, cache, "t", now=1000.0)
    await require_delivery_scope(upstream, cache, "t", now=1010.0)

    assert route.call_count == 1


@respx.mock
async def test_delivery_scope_probes_again_once_the_cache_expires(upstream: UpstreamClient) -> None:
    route = respx.get(f"{BASE}/v1/delivery/modules").respond(200, json={"items": []})
    cache = TokenProbeCache()

    await require_delivery_scope(upstream, cache, "t", now=1000.0)
    await require_delivery_scope(upstream, cache, "t", now=1000.0 + 31)

    assert route.call_count == 2


# --- require_grading_scope -----------------------------------------------------------


@respx.mock
async def test_grading_scope_accepts_a_404_for_the_probe_ref(upstream: UpstreamClient) -> None:
    # The probe id is reserved and never real: a correctly-scoped token gets 404.
    respx.get(f"{BASE}/v1/grading/questions/900000000/revisions/1").respond(404)
    cache = TokenProbeCache()

    await require_grading_scope(upstream, cache, "grading-token", now=1000.0)

    assert cache.is_fresh("grading", "grading-token", now=1000.0)


@respx.mock
async def test_grading_scope_accepts_a_200_for_the_probe_ref(upstream: UpstreamClient) -> None:
    # Vanishingly unlikely in production, but a 200 is still a valid-scope answer.
    respx.get(f"{BASE}/v1/grading/questions/900000000/revisions/1").respond(200, json={})
    cache = TokenProbeCache()

    await require_grading_scope(upstream, cache, "grading-token", now=1000.0)

    assert cache.is_fresh("grading", "grading-token", now=1000.0)


@respx.mock
async def test_grading_scope_rejects_a_delivery_token(upstream: UpstreamClient) -> None:
    respx.get(f"{BASE}/v1/grading/questions/900000000/revisions/1").respond(401)
    cache = TokenProbeCache()

    with pytest.raises(HTTPException) as exc_info:
        await require_grading_scope(upstream, cache, "delivery-token", now=1000.0)

    assert exc_info.value.status_code == 401
