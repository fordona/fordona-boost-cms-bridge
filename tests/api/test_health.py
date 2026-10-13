import asyncio

import pytest

from tests.conftest import Harness


async def test_live_needs_no_auth_or_dependencies(harness: Harness) -> None:
    harness.readiness["database"] = ConnectionError("down")

    response = await harness.client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_all_dependencies_up(harness: Harness) -> None:
    response = await harness.client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["components"]) == {"database", "redis"}
    assert all(c["status"] == "up" for c in body["components"].values())
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("database", "redis", "down"),
    [
        (ConnectionError("pg"), None, {"database"}),
        (None, ConnectionError("redis"), {"redis"}),
        (ConnectionError("pg"), ConnectionError("redis"), {"database", "redis"}),
    ],
    ids=["database-down", "redis-down", "both-down"],
)
async def test_not_ready_when_a_dependency_is_down(
    harness: Harness, database: Exception | None, redis: Exception | None, down: set[str]
) -> None:
    harness.readiness.update(database=database, redis=redis)

    response = await harness.client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert {n for n, c in body["components"].items() if c["status"] == "down"} == down
    assert body["components"][next(iter(down))]["error"] == "ConnectionError"


async def test_hanging_dependency_times_out(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from boost_bridge.api.routes import health

    monkeypatch.setattr(health, "_CHECK_TIMEOUT_SECONDS", 0.05)

    async def hang() -> None:
        await asyncio.sleep(10)

    harness.app.state.services.readiness_checks["database"] = hang

    response = await harness.client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["components"]["database"]["error"] == "Timeout"


async def test_readiness_ignores_boost(harness: Harness) -> None:
    harness.boost.route(host="boost.test").respond(503)

    response = await harness.client.get("/health/ready")

    assert response.status_code == 200
