"""Learning Journeys (2026-11-06, question-templates' replacement, confirmed against the
production Boost OpenAPI spec: a journey orders milestones, a milestone orders challenges, and
a challenge's own ``questionIds`` is its quiz). Synthesized entirely from the generated templates
(``boost_stub.data._build_challenges``/``_build_journeys``): one challenge per lesson (the
lowest-sort template when a lesson has more than one, so this fixture data itself respects the
product's one-lesson-one-challenge assumption), grouped into one milestone per module under a
single journey.

Added to close a real gap: fordona-engine's ``ContentSyncService`` started calling
``GET /v1/delivery/learning-journeys`` unconditionally (2026-11-06), and this route not existing at
all previously aborted the engine's whole sync whenever it ran against the stub (see fordona-engine
commit ``28df9c59`` for the matching 404-tolerance fix on that side).

``chapterIds``/``questionIds`` here are the field names fordona-engine's ``BoostLearningChallenge``
client DTO expects on the delivery route (renamed from the editor API's own ``lessonIds``) — not yet
confirmed against a real Boost response by anyone, per that DTO's own Javadoc, so keep both sides
updated together if that assumption turns out wrong."""

from typing import Any

from fastapi import APIRouter, Request, Response

from boost_stub.deps import DeliveryToken, LocaleParam, Services
from boost_stub.responses import list_response

router = APIRouter(prefix="/delivery/learning-journeys", tags=["learning-journeys"])


def _challenge_item(challenge: dict[str, Any], locale: str) -> dict[str, Any]:
    return {
        "id": challenge["id"],
        "title": challenge["title"].get(locale, challenge["title"].get("sv-SE")),
        "goal": challenge["goal"].get(locale, challenge["goal"].get("sv-SE")),
        "chapterIds": [challenge["lessonId"]],
        "questionIds": challenge["questionIds"],
    }


def _milestone_item(milestone: dict[str, Any], locale: str) -> dict[str, Any]:
    return {
        "id": milestone["id"],
        "title": milestone["title"].get(locale, milestone["title"].get("sv-SE")),
        "description": milestone["description"].get(locale, milestone["description"].get("sv-SE")),
        "challenges": [_challenge_item(c, locale) for c in milestone["challenges"]],
    }


def _journey_item(journey: dict[str, Any], locale: str) -> dict[str, Any]:
    return {
        "id": journey["id"],
        "title": journey["title"].get(locale, journey["title"].get("sv-SE")),
        "description": journey["description"].get(locale, journey["description"].get("sv-SE")),
        "textLocale": locale if locale in journey["title"] else "sv-SE",
        "milestones": [_milestone_item(m, locale) for m in journey["milestones"]],
    }


@router.get("")
async def list_learning_journeys(
    request: Request, services: Services, _: DeliveryToken, locale: LocaleParam = "sv-SE"
) -> Response:
    items = [_journey_item(j, locale) for j in services.data.current.journeys.values()]
    body = {"items": items, "asOf": "2026-01-01T00:00:00Z", "locale": locale}
    return list_response(request, body)
