"""The catalogue routes that exposed the question bank are gone (plan §15, R-11).

Questions reach the app only inside a lesson attempt, chosen and checked by the
engine. These tests keep the retired routes from coming back.
"""

import pytest
from fastapi.routing import APIRoute

from boost_bridge.main import create_app
from tests.conftest import Harness, make_settings

RETIRED_PATHS = frozenset(
    {
        "/v1/questions",
        "/v1/questions/{questionId}",
        "/v1/questions/{questionId}/revisions/{version}",
        "/v1/lessons/{lessonId}/questions",
        "/v1/modules",
        "/v1/modules/{moduleId}",
        "/v1/modules/{moduleId}/lessons",
    }
)


def test_route_table_has_no_retired_path() -> None:
    app = create_app(make_settings())

    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert paths.isdisjoint(RETIRED_PATHS)


def test_route_table_has_no_question_or_module_path() -> None:
    app = create_app(make_settings())

    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert not [p for p in paths if "/questions" in p or p.startswith("/v1/modules")]


@pytest.mark.parametrize(
    "path",
    [
        "/v1/questions",
        "/v1/questions/100",
        "/v1/questions/100/revisions/4",
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
