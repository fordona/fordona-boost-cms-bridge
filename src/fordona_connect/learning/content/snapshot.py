"""An in-memory, immutable view of the deliverable content (ported from the engine).

Request handling reads the snapshot, never the content tables. ``SnapshotProvider``
checks at most every ``freshness_seconds`` whether a newer release exists, and
rebuilds only then, so almost every call touches no database at all.
"""

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.core.logging import get_logger
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentChallengeLesson,
    ContentChallengeQuestion,
    ContentLesson,
    ContentQuestion,
    ContentQuestionRevision,
    ContentRelease,
    ContentUnit,
)
from fordona_connect.learning.retry.models import RetryPolicyRow
from fordona_connect.learning.retry.policy import PolicyRow, RetryPolicy, resolve_policy

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotUnit:
    unit_id: str
    sort: int
    title: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SnapshotLesson:
    lesson_id: str
    unit_id: str
    sort: int
    title: Mapping[str, str]
    current_version: str | None
    estimated_minutes: int | None


@dataclass(frozen=True, slots=True)
class ActiveQuestion:
    """An ACTIVE question with its current revision. Holds the answer key: internal only."""

    question_id: str
    home_lesson_id: str | None
    unit_id: str | None
    version: str
    type: str | None
    difficulty: int
    level: str
    domain_code: str
    topic_tag: str | None
    correct_option_key: str
    option_keys: Sequence[str]
    media_kinds: Sequence[str]
    explanation: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SnapshotChallenge:
    challenge_id: str
    milestone_id: str
    sort: int
    lesson_ids: Sequence[str]
    question_ids: Sequence[str]


@dataclass(frozen=True, slots=True)
class ContentSnapshot:
    release_id: int = 0
    units: Sequence[SnapshotUnit] = ()
    lessons_by_unit: Mapping[str, Sequence[SnapshotLesson]] = field(default_factory=dict)
    lesson_by_id: Mapping[str, SnapshotLesson] = field(default_factory=dict)
    question_by_id: Mapping[str, ActiveQuestion] = field(default_factory=dict)
    questions_by_lesson: Mapping[str, Sequence[ActiveQuestion]] = field(default_factory=dict)
    challenge_by_lesson: Mapping[str, SnapshotChallenge] = field(default_factory=dict)
    policy_rows: Sequence[PolicyRow] = ()

    def lessons_of(self, unit_id: str) -> Sequence[SnapshotLesson]:
        return self.lessons_by_unit.get(unit_id, ())

    def lesson(self, lesson_id: str) -> SnapshotLesson | None:
        return self.lesson_by_id.get(lesson_id)

    def question(self, question_id: str) -> ActiveQuestion | None:
        return self.question_by_id.get(question_id)

    def questions_of(self, lesson_id: str) -> Sequence[ActiveQuestion]:
        return self.questions_by_lesson.get(lesson_id, ())

    def challenge_for(self, lesson_id: str) -> SnapshotChallenge | None:
        return self.challenge_by_lesson.get(lesson_id)

    def retry_policy_for(self, unit_id: str | None, lesson_id: str | None) -> RetryPolicy:
        return resolve_policy(self.policy_rows, unit_id, lesson_id)


def build_snapshot(
    release_id: int,
    *,
    units: Sequence[SnapshotUnit],
    lessons: Sequence[SnapshotLesson],
    questions: Sequence[ActiveQuestion],
    challenges: Sequence[SnapshotChallenge],
    policy_rows: Sequence[PolicyRow],
) -> ContentSnapshot:
    lessons_by_unit: dict[str, list[SnapshotLesson]] = {}
    lesson_by_id: dict[str, SnapshotLesson] = {}
    for lesson in sorted(lessons, key=lambda lesson: lesson.sort):
        lessons_by_unit.setdefault(lesson.unit_id, []).append(lesson)
        lesson_by_id[lesson.lesson_id] = lesson

    question_by_id: dict[str, ActiveQuestion] = {}
    questions_by_lesson: dict[str, list[ActiveQuestion]] = {}
    for question in sorted(questions, key=lambda question: question.question_id):
        question_by_id[question.question_id] = question
        if question.home_lesson_id is not None:
            questions_by_lesson.setdefault(question.home_lesson_id, []).append(question)

    # A lesson claimed by two challenges is ambiguous: it is left out, and its
    # attempts fall back to the lesson's question bank.
    challenge_by_lesson: dict[str, SnapshotChallenge] = {}
    ambiguous: set[str] = set()
    for challenge in challenges:
        for lesson_id in challenge.lesson_ids:
            if lesson_id in ambiguous:
                continue
            existing = challenge_by_lesson.setdefault(lesson_id, challenge)
            if existing.challenge_id != challenge.challenge_id:
                del challenge_by_lesson[lesson_id]
                ambiguous.add(lesson_id)
                log.warning(
                    "lesson_in_several_challenges",
                    lesson_id=lesson_id,
                    challenge_id=existing.challenge_id,
                    other_challenge_id=challenge.challenge_id,
                )

    return ContentSnapshot(
        release_id=release_id,
        units=tuple(sorted(units, key=lambda unit: unit.sort)),
        lessons_by_unit={unit: tuple(items) for unit, items in lessons_by_unit.items()},
        lesson_by_id=lesson_by_id,
        question_by_id=question_by_id,
        questions_by_lesson={key: tuple(items) for key, items in questions_by_lesson.items()},
        challenge_by_lesson=challenge_by_lesson,
        policy_rows=tuple(policy_rows),
    )


async def load_snapshot(session: AsyncSession, release_id: int) -> ContentSnapshot:
    """Read the deliverable content (visible units and lessons, active questions)."""
    units = [
        SnapshotUnit(unit_id=row.unit_id, sort=row.sort, title=row.title)
        for row in await session.scalars(select(ContentUnit).where(ContentUnit.status == "VISIBLE"))
    ]
    unit_ids = {unit.unit_id for unit in units}
    lessons = [
        SnapshotLesson(
            lesson_id=row.lesson_id,
            unit_id=row.unit_id,
            sort=row.sort,
            title=row.title,
            current_version=row.current_version,
            estimated_minutes=row.estimated_minutes,
        )
        for row in await session.scalars(
            select(ContentLesson).where(ContentLesson.status == "VISIBLE")
        )
        if row.unit_id in unit_ids
    ]
    revision_rows = await session.execute(
        select(ContentQuestion, ContentQuestionRevision)
        .join(
            ContentQuestionRevision,
            (ContentQuestionRevision.question_id == ContentQuestion.question_id)
            & (ContentQuestionRevision.version == ContentQuestion.current_version),
        )
        .where(ContentQuestion.status == "ACTIVE")
    )
    questions = [
        ActiveQuestion(
            question_id=question.question_id,
            home_lesson_id=question.home_lesson_id,
            unit_id=question.unit_id,
            version=revision.version,
            type=revision.type,
            difficulty=revision.difficulty,
            level=revision.level,
            domain_code=revision.domain_code,
            topic_tag=revision.topic_tag,
            correct_option_key=revision.correct_option_key,
            option_keys=tuple(revision.option_keys),
            media_kinds=tuple(revision.media_kinds),
            explanation=revision.explanation,
        )
        for question, revision in revision_rows
    ]

    lessons_of_challenge: dict[str, list[str]] = {}
    for lesson_link in await session.scalars(
        select(ContentChallengeLesson).order_by(ContentChallengeLesson.sort)
    ):
        lessons_of_challenge.setdefault(lesson_link.challenge_id, []).append(lesson_link.lesson_id)
    questions_of_challenge: dict[str, list[str]] = {}
    for question_link in await session.scalars(
        select(ContentChallengeQuestion).order_by(ContentChallengeQuestion.sort)
    ):
        questions_of_challenge.setdefault(question_link.challenge_id, []).append(
            question_link.question_id
        )
    challenges = [
        SnapshotChallenge(
            challenge_id=row.challenge_id,
            milestone_id=row.milestone_id,
            sort=row.sort,
            lesson_ids=tuple(lessons_of_challenge.get(row.challenge_id, ())),
            question_ids=tuple(questions_of_challenge.get(row.challenge_id, ())),
        )
        for row in await session.scalars(select(ContentChallenge).order_by(ContentChallenge.sort))
    ]
    policy_rows = [
        PolicyRow(scope=row.scope, scope_id=row.scope_id, key_values=row.key_values)
        for row in await session.scalars(select(RetryPolicyRow))
    ]
    return build_snapshot(
        release_id,
        units=units,
        lessons=lessons,
        questions=questions,
        challenges=challenges,
        policy_rows=policy_rows,
    )


class SnapshotProvider:
    """Serves the current snapshot, rebuilding it when a newer release appears."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        freshness_seconds: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._freshness = freshness_seconds
        self._monotonic = monotonic
        self._snapshot = ContentSnapshot()
        self._checked_at: float | None = None
        self._lock = asyncio.Lock()
        # Bumped when retry policy rows change, so the next get() rebuilds.
        self._force = False

    def invalidate(self) -> None:
        """Rebuild on the next ``get`` (after a retry policy edit, say)."""
        self._force = True

    async def get(self) -> ContentSnapshot:
        now = self._monotonic()
        if (
            not self._force
            and self._checked_at is not None
            and now - self._checked_at < self._freshness
        ):
            return self._snapshot
        async with self._lock:
            # Another task may have refreshed while this one waited.
            if (
                not self._force
                and self._checked_at is not None
                and self._monotonic() - self._checked_at < self._freshness
            ):
                return self._snapshot
            async with self._sessionmaker() as session:
                latest = await session.scalar(select(func.max(ContentRelease.release_id)))
                if latest is not None and (self._force or latest != self._snapshot.release_id):
                    log.info(
                        "content_snapshot_rebuilding",
                        from_release=self._snapshot.release_id,
                        to_release=latest,
                    )
                    self._snapshot = await load_snapshot(session, latest)
            self._force = False
            self._checked_at = self._monotonic()
        return self._snapshot
