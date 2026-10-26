"""Demo suite: login/token security, exercised through the real HTTP endpoint.

tests/unit/test_security.py already proves the TokenVerifier in isolation in
much more depth. This file is the "show the supervisor" version: every test
hits GET /v1/modules/1 exactly like a real frontend request would, and shows
that the service correctly lets good tokens through and rejects every kind of
bad one at the door (401), before Boost is ever called.

Run just this file for the walkthrough:

    uv run pytest tests/demo/test_login_security_showcase.py -v
"""

import time

import jwt
import pytest

from tests.auth import AUDIENCE, ISSUER, SigningKey
from tests.conftest import BOOST, Harness
from tests.factories import module_payload

GOOD_KEY = SigningKey("test-key")  # matches the key served by the harness's JWKS mock


def _protected_route_was_never_called(harness: Harness) -> bool:
    return not [c for c in harness.boost.calls if c.request.url.host == "boost.test"]


# --- the happy path: a real, valid login token works ----------------------------


async def test_valid_kinde_token_is_accepted(harness: Harness) -> None:
    harness.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload("1"))

    response = await harness.client.get("/v1/modules/1", headers=harness.auth())

    assert response.status_code == 200
    assert response.json()["id"] == "1"


# --- no token at all -------------------------------------------------------------


async def test_no_token_is_rejected_with_401(harness: Harness) -> None:
    response = await harness.client.get("/v1/modules/1")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["errorCode"] == "UNAUTHORIZED"
    assert _protected_route_was_never_called(harness)


async def test_malformed_authorization_header_is_rejected(harness: Harness) -> None:
    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


async def test_garbage_token_is_rejected(harness: Harness) -> None:
    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


# --- an expired session ------------------------------------------------------------


async def test_expired_token_is_rejected(harness: Harness) -> None:
    response = await harness.client.get(
        "/v1/modules/1", headers=harness.auth(exp=int(time.time()) - 120)
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


# --- a token meant for someone else / somewhere else --------------------------------


async def test_token_for_a_different_audience_is_rejected(harness: Harness) -> None:
    """A token issued for a different app must not work here."""
    response = await harness.client.get(
        "/v1/modules/1", headers=harness.auth(aud=["some-other-app"])
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


async def test_token_from_a_different_issuer_is_rejected(harness: Harness) -> None:
    """A token not actually issued by our Kinde tenant must not work, even if
    it otherwise looks valid."""
    response = await harness.client.get(
        "/v1/modules/1", headers=harness.auth(iss="https://not-fordona.kinde.com")
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


# --- forged / tampered tokens -------------------------------------------------------


async def test_token_signed_by_an_impostor_key_is_rejected(harness: Harness) -> None:
    """Same key id, different private key — simulates someone trying to forge
    a token without actually having Kinde's signing key."""
    impostor = SigningKey("test-key")  # same kid as the real key, different key pair

    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": f"Bearer {impostor.token()}"}
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


async def test_hs256_algorithm_confusion_attack_is_rejected(harness: Harness) -> None:
    """Classic JWT attack: in services that use the *same* key for both RS256
    verification and HS256 signing, an attacker can reuse the RSA public key
    (freely available from the JWKS endpoint) as an HMAC secret to self-sign
    a token. A naive verifier that trusts the token's own `alg` header would
    accept it, since the HS256 signature checks out once you know that
    "secret". Our verifier never even looks at the token's own `alg` claim --
    it only ever accepts RS256 -- so any HS256 token is rejected outright,
    regardless of what it is signed with."""
    forged = jwt.encode(
        {
            "sub": "attacker",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 3600,
        },
        "guessed-or-stolen-secret-value-padded-to-32-bytes",
        algorithm="HS256",
        headers={"kid": GOOD_KEY.kid},
    )

    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


async def test_unsigned_alg_none_token_is_rejected(harness: Harness) -> None:
    """Another classic attack: a token that claims alg=none and has no
    signature at all. Must never be accepted."""
    header = jwt.utils.base64url_encode(b'{"alg":"none","typ":"JWT"}').decode()
    payload = jwt.utils.base64url_encode(
        f'{{"sub":"attacker","iss":"{ISSUER}","aud":"{AUDIENCE}"}}'.encode()
    ).decode()
    forged = f"{header}.{payload}."

    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401
    assert _protected_route_was_never_called(harness)


# --- the service never leaks an unverified token upstream ---------------------------


async def test_an_unverified_token_is_never_forwarded_to_boost(
    harness_factory: object,
) -> None:
    """Even in forward_learner_token mode (where the bridge reuses the
    learner's own token to call Boost), a token that fails our own
    verification must never reach Boost at all."""
    async with harness_factory(boost_auth_mode="forward_learner_token") as h:  # type: ignore[operator]
        route = h.boost.get(f"{BOOST}/v1/delivery/modules/1").respond(json=module_payload("1"))

        response = await h.client.get("/v1/modules/1", headers=h.auth(aud=["someone-else"]))

        assert response.status_code == 401
        assert route.call_count == 0  # Boost was never even asked


# --- credentials never show up in logs or error bodies -------------------------------


async def test_401_response_never_echoes_the_bad_token(harness: Harness) -> None:
    secret_looking_token = "Bearer eyFAKESECRETVALUESHOULDNEVERBEECHOED.back.toclient"

    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": secret_looking_token}
    )

    assert response.status_code == 401
    assert "FAKESECRETVALUE" not in response.text


@pytest.mark.parametrize("token", ["", "a", "a.b", "a.b.c.d"])
async def test_a_variety_of_garbage_inputs_all_fail_closed(harness: Harness, token: str) -> None:
    """No malformed input should ever crash the service or fall through to
    an authenticated code path — every shape of garbage must fail closed
    (401), never 500."""
    response = await harness.client.get(
        "/v1/modules/1", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
