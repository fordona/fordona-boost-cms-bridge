"""The catalogue routes that exposed the question bank and paid theory with no
entitlement check are gone for good (plan §15, R-11, R-8).

``/v1/lessons/{lessonId}`` kept its path but got a new, entitlement-checked
meaning in P6.T5 (plan §7.3) — it is no longer retired; see
``tests/api/test_theory_lessons.py`` for its own coverage. These tests keep the
*other* retired catalogue routes from coming back, and pin the full public
route table.
"""

import pytest

from fordona_connect.main import create_app
from tests.conftest import Harness, make_settings

RETIRED_PATHS = frozenset(
    {
        "/v1/questions",
        "/v1/questions/{questionId}",
        "/v1/questions/{questionId}/revisions/{version}",
        "/v1/lessons",
        "/v1/lessons/{lessonId}/questions",
        "/v1/modules",
        "/v1/modules/{moduleId}",
        "/v1/modules/{moduleId}/lessons",
    }
)

PUBLIC_THEORY_PATHS = frozenset(
    {
        "/v1/home",
        "/v1/learning-path",
        "/v1/readiness",
        "/v1/lessons/{lessonId}",
        "/v1/lessons/{lessonId}/attempts",
        "/v1/attempts/{attemptId}",
        "/v1/attempts/{attemptId}/responses",
        "/v1/attempts/{attemptId}/phases/lesson/complete",
        "/v1/attempts/{attemptId}/phases/retry/complete",
        # Mock exam browsing (2026-11-07) — read-only list/preview, added after Plan §7.3's
        # original 9-endpoint scope; not in the plan's own acceptance criterion below.
        "/v1/mock-exams",
        "/v1/mock-exams/{mockExamId}",
        # Personalized Learning Journey (2026-11-07) — a deliberately isolated, temporary
        # BFF-only feature (own snake_case/problem+json-free error envelope, own DB tables,
        # no engine/Boost calls) approved as a stopgap while the Boost/engine/mobile content
        # model mismatch is resolved. See learning_journey/__init__.py's module docstring.
        "/v1/learning-journey",
        # readiness/home (2026-11-08): new, learning-journey-only endpoints, NOT a sync of
        # the engine-backed /v1/readiness and /v1/home above — those stay untouched.
        "/v1/learning-journey/readiness",
        "/v1/learning-journey/home",
        "/v1/milestones",
        "/v1/challenges",
        "/v1/challenges/attempts",
        "/v1/challenges/attempts/{attempt_id}",
        "/v1/challenges/attempts/{attempt_id}/answers",
        "/v1/challenges/attempts/{attempt_id}/submit",
        "/v1/challenges/remediation",
    }
)


def _api_paths() -> set[str]:
    # FastAPI >= 0.14x keeps included routers as wrappers in ``app.routes``, so a
    # filter on ``APIRoute`` sees nothing. The OpenAPI document is the public view
    # of every routed operation (no route here sets include_in_schema=False).
    # ``test_route_table_matches_the_public_surface`` doubles as the positive
    # control that this set is never silently empty.
    app = create_app(make_settings())
    return set(app.openapi()["paths"])


def test_route_table_has_no_retired_path() -> None:
    assert _api_paths().isdisjoint(RETIRED_PATHS)


def test_route_table_matches_the_public_surface() -> None:
    """Plan §7.3's own acceptance criterion was exactly 9 public endpoints + health; the 2
    mock-exam-browsing routes (2026-11-07) are a deliberate, later addition beyond that scope —
    this still guards against anything *else* slipping in unnoticed."""
    assert _api_paths() == PUBLIC_THEORY_PATHS | {"/health/live", "/health/ready"}


@pytest.mark.parametrize(
    "path",
    [
        "/v1/questions",
        "/v1/questions/100",
        "/v1/questions/100/revisions/4",
        "/v1/lessons",
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
