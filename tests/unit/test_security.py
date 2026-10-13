"""Kinde token verification and the JWKS cache."""

import base64
import json
import time

import httpx
import jwt
import pytest
import respx

from boost_bridge.core.errors import UnauthorizedError, UpstreamUnavailableError
from boost_bridge.core.security import JwksCache, TokenVerifier
from tests.auth import AUDIENCE, ISSUER, JWKS_URI, SigningKey, jwks
from tests.fakes import FakeClock

KEY = SigningKey("key-1")


@pytest.fixture
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as client:
        yield client  # type: ignore[misc]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def jwks_cache(http: httpx.AsyncClient, clock: FakeClock) -> JwksCache:
    return JwksCache(http, JWKS_URI, ttl_seconds=600, min_refresh_interval_seconds=60, clock=clock)


@pytest.fixture
def verifier(jwks_cache: JwksCache) -> TokenVerifier:
    return TokenVerifier(jwks_cache, issuer=ISSUER, audiences=["other-aud", AUDIENCE])


@respx.mock
async def test_valid_token_yields_learner(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(json=jwks(KEY))

    learner = await verifier.verify(KEY.token())

    assert learner.sub == "kp_learner123"
    assert learner.claims["iss"] == ISSUER


@respx.mock
async def test_string_audience_is_accepted(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(json=jwks(KEY))
    assert (await verifier.verify(KEY.token(aud=AUDIENCE))).sub == "kp_learner123"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 120},  # expired beyond leeway
        {"nbf": int(time.time()) + 600},  # not yet valid
        {"aud": ["someone-else"]},
        {"iss": "https://evil.kinde.com"},
        {"sub": None},
        {"exp": None},
        {"aud": None},
    ],
    ids=["expired", "nbf", "wrong-aud", "wrong-iss", "no-sub", "no-exp", "no-aud"],
)
@respx.mock
async def test_invalid_claims_are_rejected(
    verifier: TokenVerifier, overrides: dict[str, object]
) -> None:
    respx.get(JWKS_URI).respond(json=jwks(KEY))

    with pytest.raises(UnauthorizedError):
        await verifier.verify(KEY.token(**overrides))


@respx.mock
async def test_expiry_within_leeway_is_accepted(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(json=jwks(KEY))
    assert await verifier.verify(KEY.token(exp=int(time.time()) - 10))


@respx.mock
async def test_signature_from_other_key_is_rejected(verifier: TokenVerifier) -> None:
    impostor = SigningKey("key-1")  # same kid, different key material
    respx.get(JWKS_URI).respond(json=jwks(KEY))

    with pytest.raises(UnauthorizedError):
        await verifier.verify(impostor.token())


@respx.mock
async def test_hs256_token_is_rejected_without_key_lookup(verifier: TokenVerifier) -> None:
    route = respx.get(JWKS_URI).respond(json=jwks(KEY))
    forged = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        "public-key-as-hmac-secret-0123456789abcdef",
        algorithm="HS256",
        headers={"kid": "key-1"},
    )

    with pytest.raises(UnauthorizedError):
        await verifier.verify(forged)
    assert route.call_count == 0


@respx.mock
async def test_alg_none_token_is_rejected(verifier: TokenVerifier) -> None:
    def b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    token = f"{b64({'alg': 'none', 'kid': 'key-1'})}.{b64({'sub': 'x'})}."

    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
async def test_garbage_is_rejected(verifier: TokenVerifier, token: str) -> None:
    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)


@respx.mock
async def test_missing_kid_is_rejected(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(json=jwks(KEY))
    token = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60, "iat": 1},
        KEY.private,
        algorithm="RS256",
    )
    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)


# --- JWKS cache ----------------------------------------------------------------


@respx.mock
async def test_jwks_is_cached(verifier: TokenVerifier) -> None:
    route = respx.get(JWKS_URI).respond(json=jwks(KEY))

    for _ in range(5):
        await verifier.verify(KEY.token())

    assert route.call_count == 1


@respx.mock
async def test_jwks_refetched_after_ttl(verifier: TokenVerifier, clock: FakeClock) -> None:
    route = respx.get(JWKS_URI).respond(json=jwks(KEY))
    await verifier.verify(KEY.token())
    clock.advance(601)

    await verifier.verify(KEY.token())

    assert route.call_count == 2


@respx.mock
async def test_unknown_kid_triggers_rotation_refetch(
    verifier: TokenVerifier, clock: FakeClock
) -> None:
    rotated = SigningKey("key-2")
    route = respx.get(JWKS_URI).mock(
        side_effect=[
            httpx.Response(200, json=jwks(KEY)),
            httpx.Response(200, json=jwks(KEY, rotated)),
        ]
    )
    await verifier.verify(KEY.token())
    clock.advance(61)

    learner = await verifier.verify(rotated.token())

    assert learner.sub == "kp_learner123"
    assert route.call_count == 2


@respx.mock
async def test_unknown_kid_refetch_is_rate_limited(
    verifier: TokenVerifier, clock: FakeClock
) -> None:
    route = respx.get(JWKS_URI).respond(json=jwks(KEY))
    await verifier.verify(KEY.token())
    stranger = SigningKey("forged-kid")

    for _ in range(10):
        with pytest.raises(UnauthorizedError):
            await verifier.verify(stranger.token())
        clock.advance(1)

    assert route.call_count == 1  # no refetch within the 60s window


@respx.mock
async def test_jwks_outage_with_no_keys_is_503(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(503)

    with pytest.raises(UpstreamUnavailableError):
        await verifier.verify(KEY.token())


@respx.mock
async def test_jwks_outage_keeps_last_known_keys(verifier: TokenVerifier, clock: FakeClock) -> None:
    respx.get(JWKS_URI).mock(
        side_effect=[httpx.Response(200, json=jwks(KEY)), httpx.ConnectError("down")]
    )
    await verifier.verify(KEY.token())
    clock.advance(601)

    learner = await verifier.verify(KEY.token())

    assert learner.sub == "kp_learner123"


@respx.mock
async def test_jwks_without_usable_keys_is_503(verifier: TokenVerifier) -> None:
    respx.get(JWKS_URI).respond(json={"keys": [{"kty": "EC", "kid": "ec-1"}]})

    with pytest.raises(UpstreamUnavailableError):
        await verifier.verify(KEY.token())
