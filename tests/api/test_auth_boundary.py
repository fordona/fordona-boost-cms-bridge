"""The request boundary end to end: authentication, locale, CORS, correlation, OpenAPI.

Exercised through the test-only probe route (see tests/conftest.py), which
depends on the real ``CurrentLearner`` and ``Locale`` dependencies.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from tests.conftest import PROBE_PATH, Harness

HarnessFactory = Callable[..., AbstractAsyncContextManager[Harness]]


# --- authentication ----------------------------------------------------------


async def test_missing_token_is_401_problem(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert body["errorCode"] == "UNAUTHORIZED"
    assert body["correlationId"] == response.headers["X-Correlation-ID"]


async def test_expired_token_is_401(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH, headers=harness.auth(exp=1))
    assert response.status_code == 401


async def test_non_bearer_scheme_is_401(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH, headers={"Authorization": "Basic Zm9v"})
    assert response.status_code == 401


async def test_wrong_audience_is_401(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH, headers=harness.auth(aud=["elsewhere"]))
    assert response.status_code == 401


async def test_valid_token_resolves_the_learner(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH, headers=harness.auth())

    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "kp_learner123"
    assert body["tokenForwardable"] is True  # only a verified token is ever stored


async def test_auth_disabled_locally_needs_no_token(harness_factory: HarnessFactory) -> None:
    async with harness_factory(auth_enabled=False) as h:
        response = await h.client.get(PROBE_PATH)

    assert response.status_code == 200
    assert response.json()["sub"] == "local-dev"


# --- locale ------------------------------------------------------------------


async def test_default_locale_is_swedish(harness: Harness) -> None:
    response = await harness.client.get(PROBE_PATH, headers=harness.auth())
    assert response.json()["locale"] == "sv-SE"


async def test_accept_language_selects_locale(harness: Harness) -> None:
    response = await harness.client.get(
        PROBE_PATH, headers={**harness.auth(), "Accept-Language": "en-US,en;q=0.9"}
    )
    assert response.json()["locale"] == "en-GB"


async def test_locale_query_wins_over_accept_language(harness: Harness) -> None:
    response = await harness.client.get(
        PROBE_PATH,
        params={"locale": "sv-SE"},
        headers={**harness.auth(), "Accept-Language": "en-GB"},
    )
    assert response.json()["locale"] == "sv-SE"


async def test_unsupported_locale_is_422(harness: Harness) -> None:
    response = await harness.client.get(
        PROBE_PATH, params={"locale": "de-DE"}, headers=harness.auth()
    )

    assert response.status_code == 422
    assert response.json()["fieldErrors"][0]["field"] == "locale"


# --- cross-cutting -----------------------------------------------------------


async def test_correlation_id_is_echoed(harness: Harness) -> None:
    response = await harness.client.get(
        PROBE_PATH, headers={**harness.auth(), "X-Correlation-ID": "fe-trace-7"}
    )
    assert response.headers["X-Correlation-ID"] == "fe-trace-7"


async def test_cors_preflight_allows_configured_origin(harness: Harness) -> None:
    response = await harness.client.options(
        PROBE_PATH,
        headers={
            "Origin": "https://theory.fordona.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://theory.fordona.test"


async def test_openapi_schemas_carry_no_answer_fields(harness: Harness) -> None:
    """``correctOptionId`` (Boost's own raw answer-key field name) must never appear
    anywhere. ``explanation`` is legitimate on ``ResponseFeedbackOut`` as of P6.T5
    (Plan §7.3: resolved content blocks, returned only after an answer) — but it
    must never be the raw string field Boost's own (never-modelled-as-public)
    ``explanation`` carries, so a string-typed ``explanation`` is still banned.
    """
    spec = (await harness.client.get("/openapi.json")).json()

    for schema in spec.get("components", {}).get("schemas", {}).values():
        properties = schema.get("properties", {})
        assert "correctOptionId" not in properties
        explanation = properties.get("explanation")
        if explanation is not None:
            assert explanation.get("type") != "string"
