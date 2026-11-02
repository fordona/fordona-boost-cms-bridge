"""The catalogue routes that exposed the question bank and paid theory are gone
(plan §15, R-11, R-8).

Questions reach the app only inside a lesson attempt, chosen and checked by the
engine, and theory only after the engine's lock check. Until that public API
ships (P6), the service serves its health probes and nothing else. These tests
keep the retired routes from coming back.
"""

import pytest

from boost_bridge.main import create_app
from tests.conftest import Harness, make_settings

RETIRED_PATHS = frozenset(
    {
        "/v1/questions",
        "/v1/questions/{questionId}",
        "/v1/questions/{questionId}/revisions/{version}",
        "/v1/lessons",
        "/v1/lessons/{lessonId}",
        "/v1/lessons/{lessonId}/questions",
        "/v1/modules",
        "/v1/modules/{moduleId}",
        "/v1/modules/{moduleId}/lessons",
    }
)


def _api_paths() -> set[str]:
    # FastAPI >= 0.14x keeps included routers as wrappers in ``app.routes``, so a
    # filter on ``APIRoute`` sees nothing. The OpenAPI document is the public view
    # of every routed operation (no route here sets include_in_schema=False).
    # ``test_route_table_serves_only_health_probes`` doubles as the positive
    # control that this set is never silently empty.
    app = create_app(make_settings())
    return set(app.openapi()["paths"])


def test_route_table_has_no_retired_path() -> None:
    assert _api_paths().isdisjoint(RETIRED_PATHS)


def test_route_table_serves_only_health_probes() -> None:
    assert _api_paths() == {"/health/live", "/health/ready"}


@pytest.mark.parametrize(
    "path",
    [
        "/v1/questions",
        "/v1/questions/100",
        "/v1/questions/100/revisions/4",
        "/v1/lessons",
        "/v1/lessons/1",
        "/v1/lessons/1/questions",
        "/v1/modules",
        "/v1/modules/1",
        "/v1/modules/1/lessons",
    ],
)
async def test_retired_path_is_404_and_never_reaches_boost(harness: Harness, path: str) -> None:
    response = await harness.client.get(path, headers=harness.auth())

    assert response.status_code == 404
    assert response.json()["errorCode"] == "NOT_FOUND"
    assert not [c for c in harness.boost.calls if c.request.url.host == "boost.test"]
