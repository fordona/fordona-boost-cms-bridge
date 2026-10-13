"""Correlation id handling and problem+json rendering on a minimal app."""

import httpx
import pytest
from fastapi import FastAPI, Query

from boost_bridge.core.errors import (
    ContentNotFoundError,
    UpstreamUnavailableError,
    register_exception_handlers,
)
from boost_bridge.core.middleware import RequestContextMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/missing")
    async def missing() -> None:
        raise ContentNotFoundError()

    @app.get("/down")
    async def down() -> None:
        raise UpstreamUnavailableError(headers={"Retry-After": "5"})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/validated")
    async def validated(page_size: int = Query(alias="pageSize", ge=1, le=100)) -> None:
        return None

    return app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c  # type: ignore[misc]


async def test_generates_correlation_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/ok")
    assert response.status_code == 200
    assert len(response.headers["X-Correlation-ID"]) == 36


async def test_echoes_safe_correlation_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/ok", headers={"X-Correlation-ID": "abc-123"})
    assert response.headers["X-Correlation-ID"] == "abc-123"


async def test_replaces_unsafe_correlation_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/ok", headers={"X-Correlation-ID": "a b<script>"})
    assert response.headers["X-Correlation-ID"] != "a b<script>"


async def test_app_error_renders_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/missing", headers={"X-Correlation-ID": "cid-1"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body == {
        "type": "https://fordona.io/errors/content/not-found",
        "title": "Content Not Found",
        "status": 404,
        "detail": "The requested content does not exist or is not published.",
        "instance": "/missing",
        "errorCode": "CONTENT_NOT_FOUND",
        "correlationId": "cid-1",
    }


async def test_app_error_headers_are_sent(client: httpx.AsyncClient) -> None:
    response = await client.get("/down")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


async def test_unhandled_exception_is_500_without_leaking(client: httpx.AsyncClient) -> None:
    response = await client.get("/boom", headers={"X-Correlation-ID": "cid-2"})
    assert response.status_code == 500
    body = response.json()
    assert body["errorCode"] == "INTERNAL_ERROR"
    assert body["correlationId"] == "cid-2"
    assert "secret internal detail" not in response.text
    assert response.headers["X-Correlation-ID"] == "cid-2"


async def test_validation_error_is_422_with_field_errors(client: httpx.AsyncClient) -> None:
    response = await client.get("/validated", params={"pageSize": 500})
    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "VALIDATION_FAILED"
    assert body["fieldErrors"][0]["field"] == "pageSize"
    assert body["fieldErrors"][0]["location"] == "query"


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.json()["errorCode"] == "NOT_FOUND"
