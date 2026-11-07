"""LearningJourneyRepository against a real Postgres (testcontainers) — migrations
0002/0003 applied via Alembic, same pattern as ``test_snapshot_repository.py``.

Needs a running Docker daemon; skips itself otherwise.
"""

import hashlib
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from boost_bridge.db.session import create_sessionmaker
from boost_bridge.learning_journey.models import (
    LearningJourneyAttempt,
    LearningJourneyAttemptQuestion,
    LearningJourneyChallenge,
    LearningJourneyMilestone,
    LearningJourneyQuestion,
    LearningJourneySession,
)
from boost_bridge.learning_journey.repository import LearningJourneyRepository

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        url = container.get_connection_url()
        _migrate(url)
        yield url


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def repository(engine: AsyncEngine) -> LearningJourneyRepository:
    return LearningJourneyRepository(create_sessionmaker(engine))


# --- Seed landed correctly -------------------------------------------------------


async def test_seed_counts_match_the_bundled_diagnostics(engine: AsyncEngine) -> None:
    import json

    diagnostics = json.loads(
        (
            ROOT
            / "src"
            / "boost_bridge"
            / "learning_journey"
            / "seed"
            / "learning_journey_mock_db.json"
        ).read_text(encoding="utf-8")
    )["diagnostics"]

    async with create_sessionmaker(engine)() as session:
        milestone_count = (await session.execute(select(LearningJourneyMilestone))).scalars().all()
        challenge_count = (await session.execute(select(LearningJourneyChallenge))).scalars().all()
        question_count = (await session.execute(select(LearningJourneyQuestion))).scalars().all()

    assert len(milestone_count) == diagnostics["milestone_count"]
    assert len(challenge_count) == diagnostics["challenge_count"]
    assert len(question_count) == diagnostics["question_count"]


async def test_a_ready_challenge_is_queryable_with_its_questions_in_order(
    repository: LearningJourneyRepository,
) -> None:
    questions = await repository.list_questions_for_challenge("ch_028")

    assert len(questions) == 12
    positions = [position for _, position in questions]
    assert positions == sorted(positions)


# --- Assignment bootstrap ---------------------------------------------------------


async def test_ensure_assignment_is_idempotent_under_repeated_calls(
    repository: LearningJourneyRepository,
) -> None:
    now = datetime.now(UTC)
    challenge_ids = [
        c.challenge_id for c in await repository.list_challenges_for_milestone("ms_008")
    ]

    first = await repository.ensure_assignment(
        app_user_id="user-1",
        journey_id="journey_001",
        journey_version=1,
        assignment_id="assignment-user-1",
        challenge_ids=challenge_ids,
        now=now,
    )
    second = await repository.ensure_assignment(
        app_user_id="user-1",
        journey_id="journey_001",
        journey_version=1,
        assignment_id="assignment-user-1",
        challenge_ids=challenge_ids,
        now=now,
    )

    assert first.assignment_id == second.assignment_id
    progress = await repository.list_progress(first.assignment_id)
    assert len(progress) == len(challenge_ids)


# --- Attempt round trip ------------------------------------------------------------


async def test_create_attempt_then_get_attempt_and_grade_round_trips(
    repository: LearningJourneyRepository,
) -> None:
    now = datetime.now(UTC)
    challenge_ids = [
        c.challenge_id for c in await repository.list_challenges_for_milestone("ms_008")
    ]
    assignment = await repository.ensure_assignment(
        app_user_id="user-2",
        journey_id="journey_001",
        journey_version=1,
        assignment_id="assignment-user-2",
        challenge_ids=challenge_ids,
        now=now,
    )
    session = LearningJourneySession(
        session_id="session-1",
        assignment_id=assignment.assignment_id,
        app_user_id="user-2",
        challenge_id="ch_028",
        session_type="PROGRESSION",
        status="IN_PROGRESS",
        started_at=now,
    )
    await repository.create_session(session)

    number = await repository.next_challenge_attempt_number(
        assignment_id=assignment.assignment_id, challenge_id="ch_028"
    )
    assert number == 1

    attempt = LearningJourneyAttempt(
        attempt_id="attempt-1",
        session_id=session.session_id,
        assignment_id=assignment.assignment_id,
        app_user_id="user-2",
        challenge_id="ch_028",
        attempt_number=1,
        challenge_attempt_number=number,
        attempt_type="INITIAL",
        challenge_version=1,
        status="IN_PROGRESS",
        total_questions=1,
        started_at=now,
    )
    question_row = LearningJourneyAttemptQuestion(
        attempt_id=attempt.attempt_id,
        question_id="q_266",
        question_version=1,
        position=1,
        option_order=["opt_266_01", "opt_266_02", "opt_266_03", "opt_266_04"],
        answer_key_snapshot={"option_ids": ["opt_266_01"]},
        question_content_snapshot={
            "question_text": "x",
            "question_type": "SINGLE_CHOICE",
            "options": [],
        },
        source_type="ORIGINAL",
        difficulty=1,
        level="EASY",
        response_status="UNANSWERED",
    )
    await repository.create_attempt(attempt, [question_row])

    fetched = await repository.get_attempt(attempt.attempt_id)
    assert fetched is not None
    assert fetched.status == "IN_PROGRESS"

    await repository.grade_attempt_question(
        attempt_id=attempt.attempt_id,
        question_id="q_266",
        selected_option_keys=["A"],
        selected_option_ids=["opt_266_01"],
        is_correct=True,
        duration_ms=1000,
        now=now,
    )
    graded = await repository.get_attempt_question(
        attempt_id=attempt.attempt_id, question_id="q_266"
    )
    assert graded is not None
    assert graded.response_status == "GRADED"
    assert graded.is_correct is True

    await repository.mark_attempt_submitted(
        attempt_id=attempt.attempt_id,
        correct_count=1,
        incorrect_count=0,
        score_percentage=100.0,
        duration_ms=1000,
        now=now,
    )
    submitted = await repository.get_attempt(attempt.attempt_id)
    assert submitted is not None
    assert submitted.status == "SUBMITTED"
    assert submitted.score_percentage == 100.0


# --- Idempotency claim under concurrency -------------------------------------------


async def test_claim_idempotency_key_is_exclusive(repository: LearningJourneyRepository) -> None:
    # request_fingerprint is CHAR(64) (always a sha256 hexdigest in production, same
    # convention as content_snapshot.content_hash) — Postgres blank-pads anything
    # shorter, so the fixture must be a real 64-char value or the equality checks
    # below fail on trailing padding rather than on an actual mismatch.
    fingerprint = hashlib.sha256(b"fixture-body").hexdigest()
    now = datetime.now(UTC)
    first = await repository.claim_idempotency_key(
        app_user_id="user-3",
        endpoint="POST /v1/challenges/attempts",
        idempotency_key="key-1",
        request_fingerprint=fingerprint,
        now=now,
    )
    assert first is None  # this call claimed it

    second = await repository.claim_idempotency_key(
        app_user_id="user-3",
        endpoint="POST /v1/challenges/attempts",
        idempotency_key="key-1",
        request_fingerprint=fingerprint,
        now=now,
    )
    assert second is not None  # already claimed — returned for the caller to replay/compare
    assert second.request_fingerprint == fingerprint

    await repository.store_idempotent_response(
        app_user_id="user-3",
        endpoint="POST /v1/challenges/attempts",
        idempotency_key="key-1",
        response_status=201,
        response_body={"ok": True},
    )
    third = await repository.claim_idempotency_key(
        app_user_id="user-3",
        endpoint="POST /v1/challenges/attempts",
        idempotency_key="key-1",
        request_fingerprint=fingerprint,
        now=now,
    )
    assert third is not None
    assert third.response_status == 201
    assert third.response_body == {"ok": True}
