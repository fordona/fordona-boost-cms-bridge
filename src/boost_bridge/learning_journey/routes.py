"""The 9 Learning Journey endpoints (spec §2), plus 2 later additions
(``/learning-journey/readiness``, ``/learning-journey/home`` — see their own
schemas.py section header). Mounted at ``/v1`` in ``main.py``, same convention as
every other router in this BFF.

Response envelope/status codes are **not** FastAPI's ``response_model`` machinery for
the 4 state-changing POSTs — those go through the idempotency layer in ``service.py``
and return a raw ``(status_code, body)`` pair, rendered here via ``JSONResponse``. The
read-only GETs use ``response_model`` normally, wrapped in ``success_envelope``.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from boost_bridge.api.deps import (
    CurrentLearner,
    LearningJourney,
    ReadRateLimit,
    Timezone,
    WriteRateLimit,
)
from boost_bridge.learning_journey.schemas import (
    AnswerRequest,
    RemediationRequest,
    StartAttemptRequest,
    SubmitRequest,
    success_envelope,
)

router = APIRouter(tags=["learning-journey"])

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key")]


@router.get("/learning-journey")
async def get_learning_journey(
    service: LearningJourney, learner: CurrentLearner, _: ReadRateLimit
) -> JSONResponse:
    out = await service.get_learning_journey(learner.sub)
    return JSONResponse(success_envelope(out))


@router.get("/learning-journey/readiness")
async def get_learning_journey_readiness(
    service: LearningJourney, learner: CurrentLearner, _: ReadRateLimit
) -> JSONResponse:
    out = await service.get_readiness(learner.sub)
    return JSONResponse(success_envelope(out))


@router.get("/learning-journey/home")
async def get_learning_journey_home(
    service: LearningJourney, learner: CurrentLearner, _: ReadRateLimit, timezone: Timezone
) -> JSONResponse:
    out = await service.get_home(learner.sub, timezone)
    return JSONResponse(success_envelope(out))


@router.get("/milestones")
async def get_milestone(
    service: LearningJourney,
    learner: CurrentLearner,
    _: ReadRateLimit,
    milestone_id: Annotated[str, Query()],
) -> JSONResponse:
    out = await service.get_milestone_detail(learner.sub, milestone_id)
    return JSONResponse(success_envelope(out))


@router.get("/challenges")
async def get_challenge(
    service: LearningJourney,
    learner: CurrentLearner,
    _: ReadRateLimit,
    challenge_id: Annotated[str, Query()],
) -> JSONResponse:
    out = await service.get_challenge_detail(learner.sub, challenge_id)
    return JSONResponse(success_envelope(out))


@router.post("/challenges/attempts", status_code=201)
async def start_journey_attempt(
    service: LearningJourney,
    learner: CurrentLearner,
    _: WriteRateLimit,
    body: StartAttemptRequest,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    status, envelope = await service.start_attempt(
        learner.sub,
        challenge_id=body.challenge_id,
        mode=body.mode,
        idempotency_key=idempotency_key,
        request_body=body.model_dump(mode="json"),
    )
    return JSONResponse(envelope, status_code=status)


@router.get("/challenges/attempts/{attempt_id}")
async def get_journey_attempt(
    service: LearningJourney,
    learner: CurrentLearner,
    _: ReadRateLimit,
    attempt_id: str,
) -> JSONResponse:
    out = await service.get_attempt(learner.sub, attempt_id)
    return JSONResponse(success_envelope(out))


@router.post("/challenges/attempts/{attempt_id}/answers")
async def answer_journey_question(
    service: LearningJourney,
    learner: CurrentLearner,
    _: WriteRateLimit,
    attempt_id: str,
    body: AnswerRequest,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    status, envelope = await service.answer(
        learner.sub,
        attempt_id,
        question_id=body.question_id,
        selected_option_keys=body.selected_option_keys,
        duration_ms=body.duration_ms,
        idempotency_key=idempotency_key,
        request_body=body.model_dump(mode="json"),
    )
    return JSONResponse(envelope, status_code=status)


@router.post("/challenges/attempts/{attempt_id}/submit")
async def submit(
    service: LearningJourney,
    learner: CurrentLearner,
    _: WriteRateLimit,
    attempt_id: str,
    body: SubmitRequest,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    status, envelope = await service.submit(
        learner.sub,
        attempt_id,
        idempotency_key=idempotency_key,
        request_body=body.model_dump(mode="json"),
    )
    return JSONResponse(envelope, status_code=status)


@router.get("/challenges/attempts")
async def list_attempts(
    service: LearningJourney,
    learner: CurrentLearner,
    _: ReadRateLimit,
    challenge_id: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    out = await service.list_attempts(learner.sub, challenge_id=challenge_id, limit=limit)
    return JSONResponse(success_envelope(out))


@router.post("/challenges/remediation", status_code=201)
async def create_remediation(
    service: LearningJourney,
    learner: CurrentLearner,
    _: WriteRateLimit,
    body: RemediationRequest,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    status, envelope = await service.create_remediation(
        learner.sub,
        challenge_id=body.challenge_id,
        source_attempt_id=body.source_attempt_id,
        idempotency_key=idempotency_key,
        request_body=body.model_dump(mode="json"),
    )
    return JSONResponse(envelope, status_code=status)
