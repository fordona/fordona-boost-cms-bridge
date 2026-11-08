"""State machine, remediation, idempotency — against the in-memory fake repository
(no Docker needed). Uses real seed data via ``FakeLearningJourneyRepository`` so
tests exercise the actual dataset shape, not synthetic fixtures.

Fixed ids used throughout (confirmed against the bundled seed):
- ``ch_028`` (milestone ``ms_008``, position 1, ``READY`` content, 12 questions
  ``q_266``..``q_277``) — the happy-path challenge; position 1 needs no predecessor
  completed.
- ``ch_021`` (milestone ``ms_005``, position 2, ``READY`` content) — locked in these
  tests because its predecessor ``ch_020`` (position 1) is never completed here (the
  lock check is independent of content readiness, which no longer gates starting).
- ``ch_001`` (position 1, ``MISSING_MEDIA``) — the free milestone's first challenge;
  used to confirm the (removed) content-readiness gate no longer blocks starting.
"""

import uuid
from datetime import UTC, datetime

import pytest

from boost_bridge.learning_journey.errors import (
    AnswerAlreadyFinalizedError,
    AttemptIncompleteError,
    ChallengeLockedError,
    IdempotencyKeyReusedError,
    RemediationNotEligibleError,
    SubscriptionRequiredError,
    ValidationError,
)
from boost_bridge.learning_journey.service import LearningJourneyService
from tests.learning_journey.fakes import FakeEngineClient, FakeLearningJourneyRepository

USER = "kp_test_learner"
CHALLENGE = "ch_028"  # ms_008 — a paid milestone; most tests assume an active subscription
LOCKED_CHALLENGE = "ch_021"
NOT_READY_CHALLENGE = "ch_001"
FREE_CHALLENGE = "ch_001"  # ms_001 position 1 — the free milestone, bypasses the sequential lock


@pytest.fixture
def repo() -> FakeLearningJourneyRepository:
    return FakeLearningJourneyRepository()


@pytest.fixture
def engine() -> FakeEngineClient:
    return FakeEngineClient(subscribed=True)


@pytest.fixture
def service(
    repo: FakeLearningJourneyRepository, engine: FakeEngineClient
) -> LearningJourneyService:
    return LearningJourneyService(repo, engine)  # type: ignore[arg-type]


def _key() -> str:
    return str(uuid.uuid4())


async def _start(service: LearningJourneyService, *, user: str = USER, mode: str = "INITIAL"):
    body = {"challenge_id": CHALLENGE, "mode": mode}
    status, envelope = await service.start_attempt(
        user, challenge_id=CHALLENGE, mode=mode, idempotency_key=_key(), request_body=body
    )
    return status, envelope


async def _answer_all(
    service: LearningJourneyService,
    repo: FakeLearningJourneyRepository,
    attempt_id: str,
    *,
    correct_question_ids: set[str] | None = None,
) -> None:
    """Answers every question in the attempt. Questions in ``correct_question_ids``
    (default: all) get the right answer; everything else gets a deliberately wrong
    one, read straight from the frozen snapshot (white-box, not via the API)."""
    rows = sorted(
        (v for (aid, _), v in repo.attempt_questions.items() if aid == attempt_id),
        key=lambda r: r.position,
    )
    for row in rows:
        correct_id = row.answer_key_snapshot["option_ids"][0]
        if correct_question_ids is None or row.question_id in correct_question_ids:
            chosen_id = correct_id
        else:
            chosen_id = next(oid for oid in row.option_order if oid != correct_id)
        key = chr(ord("A") + row.option_order.index(chosen_id))
        body = {"question_id": row.question_id, "selected_option_keys": [key], "duration_ms": 1000}
        await service.answer(
            USER,
            attempt_id,
            question_id=row.question_id,
            selected_option_keys=[key],
            duration_ms=1000,
            idempotency_key=_key(),
            request_body=body,
        )


# --- GET /v1/learning-journey ---------------------------------------------------


async def test_get_learning_journey_bootstraps_a_brand_new_learner(
    service: LearningJourneyService,
) -> None:
    out = await service.get_learning_journey(USER)

    assert out.journey_id == "journey_001"
    assert len(out.milestones) == 10
    assert out.progress.completed_challenges == 0
    assert out.milestones[0].access.is_locked is False


async def test_second_call_does_not_duplicate_the_assignment(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    await service.get_learning_journey(USER)
    await service.get_learning_journey(USER)

    assert len(repo.assignments) == 1


# --- GET /v1/challenges ----------------------------------------------------------


async def test_challenge_detail_hides_correct_answer_and_explanation(
    service: LearningJourneyService,
) -> None:
    out = await service.get_challenge_detail(USER, CHALLENGE)

    assert out.user_state.status == "NOT_STARTED"
    for question in out.questions:
        assert not hasattr(question, "correct_answer")
        assert not hasattr(question, "explanation")


async def test_locked_challenge_is_rejected(service: LearningJourneyService) -> None:
    with pytest.raises(ChallengeLockedError):
        await service.get_challenge_detail(USER, LOCKED_CHALLENGE)


# --- POST /v1/challenges/attempts ------------------------------------------------


async def test_start_attempt_freezes_every_question_with_shuffled_labelled_options(
    service: LearningJourneyService,
) -> None:
    status, envelope = await _start(service)

    assert status == 201
    data = envelope["data"]
    assert data["question_count"] == 12
    assert len(data["questions"]) == 12
    first = data["questions"][0]
    assert {opt["option_key"] for opt in first["options"]} == {"A", "B", "C", "D"}
    assert "correct_answer" not in first
    assert "explanation" not in first


async def test_start_attempt_on_content_not_ready_challenge_still_starts(
    service: LearningJourneyService,
) -> None:
    # The readiness gate was deliberately removed (2026-11-08): every ms_001 challenge
    # is permanently MISSING_MEDIA, so enforcing it would make the free tier
    # unattemptable end-to-end. Starting must still succeed, images or not.
    status, envelope = await service.start_attempt(
        USER,
        challenge_id=NOT_READY_CHALLENGE,
        mode="INITIAL",
        idempotency_key=_key(),
        request_body={"challenge_id": NOT_READY_CHALLENGE, "mode": "INITIAL"},
    )

    assert status == 201
    assert envelope["data"]["question_count"] == 8


async def test_voluntary_before_first_completion_is_rejected(
    service: LearningJourneyService,
) -> None:
    with pytest.raises(ValidationError):
        await _start(service, mode="VOLUNTARY")


async def test_repeated_idempotency_key_replays_the_same_response(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    key = _key()
    body = {"challenge_id": CHALLENGE, "mode": "INITIAL"}

    status1, envelope1 = await service.start_attempt(
        USER, challenge_id=CHALLENGE, mode="INITIAL", idempotency_key=key, request_body=body
    )
    status2, envelope2 = await service.start_attempt(
        USER, challenge_id=CHALLENGE, mode="INITIAL", idempotency_key=key, request_body=body
    )

    assert status1 == status2 == 201
    assert envelope1 == envelope2
    assert len(repo.attempts) == 1


async def test_idempotency_key_reused_with_different_body_conflicts(
    service: LearningJourneyService,
) -> None:
    key = _key()
    await service.start_attempt(
        USER,
        challenge_id=CHALLENGE,
        mode="INITIAL",
        idempotency_key=key,
        request_body={"challenge_id": CHALLENGE, "mode": "INITIAL"},
    )

    with pytest.raises(IdempotencyKeyReusedError):
        await service.start_attempt(
            USER,
            challenge_id=CHALLENGE,
            mode="VOLUNTARY",
            idempotency_key=key,
            request_body={"challenge_id": CHALLENGE, "mode": "VOLUNTARY"},
        )


# --- Full flows: §16 A and B of the spec -----------------------------------------


async def test_flow_a_perfect_initial_attempt_completes_with_no_remediation(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]

    await _answer_all(service, repo, attempt_id)  # every question correct

    status, envelope = await service.submit(
        USER, attempt_id, idempotency_key=_key(), request_body={}
    )

    assert status == 200
    result = envelope["data"]["result"]
    assert result["correct_count"] == 12
    assert result["score_percentage"] == 100.0
    progression = envelope["data"]["progression"]
    assert progression["status"] == "COMPLETED"
    assert progression["is_progression_complete"] is True
    remediation = envelope["data"]["remediation"]
    assert remediation["required"] is False

    progress = await service.get_challenge_detail(USER, CHALLENGE)
    assert progress.user_state.status == "COMPLETED"


async def test_flow_b_partial_initial_attempt_then_remediation_completes_regardless_of_score(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]
    all_question_ids = {q["question_id"] for q in start_envelope["data"]["questions"]}
    correct_ids = set(list(all_question_ids)[:10])  # 10/12 correct

    await _answer_all(service, repo, attempt_id, correct_question_ids=correct_ids)
    submit_status, submit_envelope = await service.submit(
        USER, attempt_id, idempotency_key=_key(), request_body={}
    )

    assert submit_status == 200
    assert submit_envelope["data"]["progression"]["status"] == "REMEDIATION_REQUIRED"
    assert submit_envelope["data"]["remediation"]["required"] is True

    rem_status, rem_envelope = await service.create_remediation(
        USER,
        challenge_id=CHALLENGE,
        source_attempt_id=attempt_id,
        idempotency_key=_key(),
        request_body={"challenge_id": CHALLENGE, "source_attempt_id": attempt_id},
    )
    assert rem_status == 201
    rem_attempt_id = rem_envelope["data"]["attempt_id"]
    assert len(rem_envelope["data"]["questions"]) == 2  # exactly the 2 missed

    # Get every remediation question wrong on purpose — must still complete.
    await _answer_all(service, repo, rem_attempt_id, correct_question_ids=set())
    final_status, final_envelope = await service.submit(
        USER, rem_attempt_id, idempotency_key=_key(), request_body={}
    )

    assert final_status == 200
    assert final_envelope["data"]["progression"]["status"] == "COMPLETED"
    assert final_envelope["data"]["progression"]["is_progression_complete"] is True

    progress = await service.get_challenge_detail(USER, CHALLENGE)
    assert progress.user_state.status == "COMPLETED"
    assert progress.user_state.remediation.completed is True


async def test_create_remediation_is_create_or_get(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]
    await _answer_all(service, repo, attempt_id, correct_question_ids=set())  # all wrong
    await service.submit(USER, attempt_id, idempotency_key=_key(), request_body={})

    body = {"challenge_id": CHALLENGE, "source_attempt_id": attempt_id}
    _, first = await service.create_remediation(
        USER,
        challenge_id=CHALLENGE,
        source_attempt_id=attempt_id,
        idempotency_key=_key(),
        request_body=body,
    )
    _, second = await service.create_remediation(
        USER,
        challenge_id=CHALLENGE,
        source_attempt_id=attempt_id,
        idempotency_key=_key(),
        request_body=body,
    )

    assert first["data"]["attempt_id"] == second["data"]["attempt_id"]
    assert first["data"]["questions"] == second["data"]["questions"]  # same frozen order
    assert len(repo.remediations) == 1


async def test_remediation_after_submitted_is_not_eligible(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]
    await _answer_all(service, repo, attempt_id, correct_question_ids=set())
    await service.submit(USER, attempt_id, idempotency_key=_key(), request_body={})

    body = {"challenge_id": CHALLENGE, "source_attempt_id": attempt_id}
    _, rem_envelope = await service.create_remediation(
        USER,
        challenge_id=CHALLENGE,
        source_attempt_id=attempt_id,
        idempotency_key=_key(),
        request_body=body,
    )
    rem_attempt_id = rem_envelope["data"]["attempt_id"]
    await _answer_all(service, repo, rem_attempt_id)
    await service.submit(USER, rem_attempt_id, idempotency_key=_key(), request_body={})

    with pytest.raises(RemediationNotEligibleError):
        await service.create_remediation(
            USER,
            challenge_id=CHALLENGE,
            source_attempt_id=attempt_id,
            idempotency_key=_key(),
            request_body=body,
        )


# --- Answer / submit edge cases ---------------------------------------------------


async def test_answering_an_already_graded_question_conflicts(
    service: LearningJourneyService, repo: FakeLearningJourneyRepository
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]
    row = next(v for (aid, _), v in repo.attempt_questions.items() if aid == attempt_id)
    question_id = row.question_id
    await service.answer(
        USER,
        attempt_id,
        question_id=question_id,
        selected_option_keys=["A"],
        duration_ms=500,
        idempotency_key=_key(),
        request_body={"question_id": question_id, "selected_option_keys": ["A"]},
    )

    with pytest.raises(AnswerAlreadyFinalizedError):
        await service.answer(
            USER,
            attempt_id,
            question_id=question_id,
            selected_option_keys=["B"],
            duration_ms=500,
            idempotency_key=_key(),
            request_body={"question_id": question_id, "selected_option_keys": ["B"]},
        )


async def test_submit_with_unanswered_questions_is_incomplete(
    service: LearningJourneyService,
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]

    with pytest.raises(AttemptIncompleteError):
        await service.submit(USER, attempt_id, idempotency_key=_key(), request_body={})


# --- GET /v1/challenges/attempts/{id} resume --------------------------------------


async def test_resume_shows_null_response_for_unanswered_question(
    service: LearningJourneyService,
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]

    out = await service.get_attempt(USER, attempt_id)

    assert out.answered_count == 0
    assert all(q.response is None for q in out.questions)


async def test_resume_preserves_the_originally_frozen_option_order(
    service: LearningJourneyService,
) -> None:
    _, start_envelope = await _start(service)
    attempt_id = start_envelope["data"]["attempt_id"]

    first = await service.get_attempt(USER, attempt_id)
    second = await service.get_attempt(USER, attempt_id)

    assert [q.options for q in first.questions] == [q.options for q in second.questions]


# --- Entitlement: free milestone vs. paid --------------------------------------


async def test_unsubscribed_user_can_view_the_free_milestone(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=False))

    out = await service.get_challenge_detail(USER, FREE_CHALLENGE)

    assert out.user_state is not None  # no SubscriptionRequiredError raised


async def test_unsubscribed_user_is_blocked_from_a_paid_challenge(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=False))

    with pytest.raises(SubscriptionRequiredError):
        await service.get_challenge_detail(USER, CHALLENGE)


async def test_unsubscribed_user_cannot_start_a_paid_attempt(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=False))

    with pytest.raises(SubscriptionRequiredError):
        await service.start_attempt(
            USER,
            challenge_id=CHALLENGE,
            mode="INITIAL",
            idempotency_key=_key(),
            request_body={"challenge_id": CHALLENGE, "mode": "INITIAL"},
        )


async def test_engine_failure_fails_closed_not_open(repo: FakeLearningJourneyRepository) -> None:
    class BrokenEngineClient:
        async def get(self, path: str, **kwargs: object) -> None:
            from boost_bridge.core.errors import UpstreamUnavailableError

            raise UpstreamUnavailableError()

    service = LearningJourneyService(repo, BrokenEngineClient())  # type: ignore[arg-type]

    with pytest.raises(SubscriptionRequiredError):
        await service.get_challenge_detail(USER, CHALLENGE)


async def test_learning_journey_listing_marks_paid_milestones_locked_for_free_user(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=False))

    out = await service.get_learning_journey(USER)

    free_milestone = next(m for m in out.milestones if m.milestone_id == "ms_001")
    paid_milestone = next(m for m in out.milestones if m.milestone_id == "ms_002")
    assert free_milestone.access.is_locked is False
    assert paid_milestone.access.is_locked is True
    assert paid_milestone.access.reason == "SUBSCRIPTION_REQUIRED"


async def test_subscribed_user_sees_every_milestone_unlocked_by_entitlement(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=True))

    out = await service.get_learning_journey(USER)

    # ms_002 is still sequentially unreachable (nobody has completed ms_001 in this
    # test), but it must be for that reason, not a paywall, once the user is subscribed.
    paid_milestone = next(m for m in out.milestones if m.milestone_id == "ms_002")
    assert paid_milestone.access.reason == "PREREQUISITE_NOT_MET"


# --- is_content_ready — independent of access (lock/entitlement) ---------------


async def test_milestone_detail_flags_missing_media_challenges_as_not_content_ready(
    service: LearningJourneyService,
) -> None:
    out = await service.get_milestone_detail(USER, "ms_001")

    assert all(c.is_content_ready is False for c in out.challenges)
    # Confirmed independently unlocked (position 1) yet still not playable —
    # the two gates are genuinely separate, not one implying the other.
    assert out.challenges[0].access.is_locked is False


async def test_challenge_detail_exposes_content_ready_for_a_ready_challenge(
    service: LearningJourneyService,
) -> None:
    out = await service.get_challenge_detail(USER, CHALLENGE)

    assert out.is_content_ready is True


async def test_challenge_detail_exposes_content_ready_false_for_missing_media(
    repo: FakeLearningJourneyRepository,
) -> None:
    service = LearningJourneyService(repo, FakeEngineClient(subscribed=True))

    out = await service.get_challenge_detail(USER, FREE_CHALLENGE)

    assert out.is_content_ready is False


# --- GET /v1/learning-journey/readiness, /v1/learning-journey/home -------------

_FIXED_SUNDAY = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
def home_service(
    repo: FakeLearningJourneyRepository, engine: FakeEngineClient
) -> LearningJourneyService:
    return LearningJourneyService(repo, engine, now_fn=lambda: _FIXED_SUNDAY)  # type: ignore[arg-type]


async def test_readiness_with_no_activity_is_zero(
    home_service: LearningJourneyService,
) -> None:
    out = await home_service.get_readiness(USER)

    assert out.percentage == 0.0
    assert out.completed_challenges == 0
    assert out.total_challenges == 39
    assert out.best_mock_result is None  # always null — no mock-exam integration


async def test_readiness_reflects_a_completed_challenge(
    home_service: LearningJourneyService,
    repo: FakeLearningJourneyRepository,
) -> None:
    _, start_envelope = await _start(home_service)
    attempt_id = start_envelope["data"]["attempt_id"]
    await _answer_all(home_service, repo, attempt_id)
    await home_service.submit(USER, attempt_id, idempotency_key=_key(), request_body={})

    out = await home_service.get_readiness(USER)

    assert out.completed_challenges == 1
    assert round(out.percentage, 2) == round(1 / 39 * 100, 2)


async def test_home_with_no_activity_points_at_the_very_first_challenge(
    home_service: LearningJourneyService,
) -> None:
    out = await home_service.get_home(USER, "UTC")

    assert out.streak.current == 0
    assert out.streak.extended_today is False
    assert out.daily_challenge.progress == 0
    assert out.daily_challenge.completed is False
    assert len(out.week.days) == 7
    assert out.week.days[0].date == "2026-11-08"  # the fixed date is itself a Sunday
    assert out.week.days[0].status == "today"
    assert out.tabs.mock_exams.is_locked is True
    assert out.tabs.learning_path.is_locked is False
    assert out.continue_ is not None
    assert out.continue_.challenge_id == "ch_001"  # the real first challenge, content gap and all
    assert out.continue_.action == "START"
    assert out.up_next[0].challenge_id == "ch_002"


async def test_home_reflects_todays_completed_challenge(
    home_service: LearningJourneyService,
    repo: FakeLearningJourneyRepository,
) -> None:
    _, start_envelope = await _start(home_service)
    attempt_id = start_envelope["data"]["attempt_id"]
    await _answer_all(home_service, repo, attempt_id)
    await home_service.submit(USER, attempt_id, idempotency_key=_key(), request_body={})

    out = await home_service.get_home(USER, "UTC")

    assert out.streak.extended_today is True
    assert out.streak.current == 1
    assert out.daily_challenge.progress == 1
    assert out.week.days[0].done is True  # today's own slot


async def test_home_continue_switches_to_continue_action_once_attempted(
    home_service: LearningJourneyService,
    repo: FakeLearningJourneyRepository,
) -> None:
    await home_service.get_home(USER, "UTC")  # bootstraps the assignment
    assignment = next(iter(repo.assignments.values()))
    repo.progress[(assignment.assignment_id, "ch_001")].total_attempts = 1

    out = await home_service.get_home(USER, "UTC")

    assert out.continue_ is not None
    assert out.continue_.action == "CONTINUE"


async def test_home_invalid_timezone_falls_back_to_utc(
    home_service: LearningJourneyService,
) -> None:
    out = await home_service.get_home(USER, "Not/A_Real_Zone")

    assert out.week.timezone == "UTC"
