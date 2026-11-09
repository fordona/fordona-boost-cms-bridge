"""Learning-journey content from Boost: the synced journey tables plus question bodies.

* Structure (journey, milestones, challenges, quiz order) comes from the
  ``content_*`` tables the content sync writes.
* Answer keys, difficulty and level come from the content snapshot (the synced
  question revisions).
* Question text and options come from Boost's published question bodies, through
  the shared body cache.

Only questions that are active in the snapshot and have a published body are
served; a challenge whose quiz is short of that reports itself not ready.
"""

import math
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fordona_connect.clients.boost.models import BoostQuestion, ContentBlock, TextBlock
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentChallengeLesson,
    ContentChallengeQuestion,
    ContentJourney,
    ContentMilestone,
)
from fordona_connect.learning.content.snapshot import (
    ActiveQuestion,
    ContentSnapshot,
    SnapshotProvider,
)
from fordona_connect.learning.progress.screens import title_in
from fordona_connect.learning_journey.content import (
    ChallengeContent,
    JourneyContent,
    MilestoneContent,
    QuestionContent,
)
from fordona_connect.services.body_cache import BodyCache, QuestionRef

_LEVELS = ("EASY", "MEDIUM", "HARD")
_SECONDS_PER_QUESTION = 45
_TYPES = {
    "truefalse": "TRUE_FALSE",
    "true_false": "TRUE_FALSE",
    "multi": "MULTIPLE_SELECT",
    "multiple_select": "MULTIPLE_SELECT",
}


def _version(value: str | None) -> int:
    """Boost versions are numeric strings; the journey API exposes them as integers."""
    return int(value) if value and value.isdigit() else 1


def _id_order(value: str) -> tuple[int, str]:
    return (len(value), value)


def _text(blocks: Sequence[ContentBlock]) -> str:
    return "\n\n".join(block.markdown for block in blocks if isinstance(block, TextBlock))


def _distribution(questions: Sequence[ActiveQuestion]) -> dict[str, int]:
    counts = dict.fromkeys(_LEVELS, 0)
    for question in questions:
        counts[question.level] = counts.get(question.level, 0) + 1
    return counts


class BoostJourneyContent:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        snapshots: SnapshotProvider,
        bodies: BodyCache,
        *,
        locale: str,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._snapshots = snapshots
        self._bodies = bodies
        self._locale = locale

    # --- journey --------------------------------------------------------------

    async def journey_id(self) -> str | None:
        async with self._sessionmaker() as session:
            ids = list(await session.scalars(select(ContentJourney.journey_id)))
        return min(ids, key=_id_order) if ids else None

    async def free_milestone_id(self) -> str | None:
        journey_id = await self.journey_id()
        if journey_id is None:
            return None
        milestones = await self.list_milestones(journey_id)
        return milestones[0].milestone_id if milestones else None

    async def get_journey_template(self, journey_id: str) -> JourneyContent | None:
        snapshot = await self._snapshots.get()
        async with self._sessionmaker() as session:
            journey = await session.get(ContentJourney, journey_id)
            if journey is None:
                return None
            milestones = list(
                await session.scalars(
                    select(ContentMilestone).where(ContentMilestone.journey_id == journey_id)
                )
            )
            quizzes = await self._quizzes(session, [m.milestone_id for m in milestones])
        challenge_ids = [c for ids in quizzes.values() for c in ids]
        questions = await self._active_quiz_questions(snapshot, challenge_ids)
        return JourneyContent(
            journey_id=journey.journey_id,
            version=_version(journey.current_version),
            title=title_in(journey.title, self._locale),
            description=title_in(journey.description, self._locale) or None,
            stats={
                "milestone_count": len(milestones),
                "challenge_count": len(challenge_ids),
                "question_count": sum(len(items) for items in questions.values()),
            },
        )

    # --- milestones -----------------------------------------------------------

    async def list_milestones(self, journey_id: str) -> Sequence[MilestoneContent]:
        async with self._sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(ContentMilestone)
                    .where(ContentMilestone.journey_id == journey_id)
                    .order_by(ContentMilestone.sort)
                )
            )
        return [await self._milestone(row) for row in rows]

    async def get_milestone(self, milestone_id: str) -> MilestoneContent | None:
        async with self._sessionmaker() as session:
            row = await session.get(ContentMilestone, milestone_id)
        return None if row is None else await self._milestone(row)

    async def _milestone(self, row: ContentMilestone) -> MilestoneContent:
        snapshot = await self._snapshots.get()
        async with self._sessionmaker() as session:
            quizzes = await self._quizzes(session, [row.milestone_id])
        challenge_ids = quizzes.get(row.milestone_id, [])
        questions = await self._active_quiz_questions(snapshot, challenge_ids)
        flat = [question for items in questions.values() for question in items]
        return MilestoneContent(
            milestone_id=row.milestone_id,
            journey_id=row.journey_id,
            position=row.sort,
            title=title_in(row.title, self._locale),
            description=title_in(row.description, self._locale) or None,
            challenge_count=len(challenge_ids),
            question_count=len(flat),
            difficulty_distribution=_distribution(flat),
        )

    # --- challenges -----------------------------------------------------------

    async def list_challenges_for_milestone(self, milestone_id: str) -> Sequence[ChallengeContent]:
        async with self._sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(ContentChallenge)
                    .where(ContentChallenge.milestone_id == milestone_id)
                    .order_by(ContentChallenge.sort)
                )
            )
        return [await self._challenge(row) for row in rows]

    async def get_challenge(self, challenge_id: str) -> ChallengeContent | None:
        async with self._sessionmaker() as session:
            row = await session.get(ContentChallenge, challenge_id)
        return None if row is None else await self._challenge(row)

    async def _challenge(self, row: ContentChallenge) -> ChallengeContent:
        snapshot = await self._snapshots.get()
        async with self._sessionmaker() as session:
            milestone = await session.get(ContentMilestone, row.milestone_id)
            journey = await session.get(ContentJourney, milestone.journey_id) if milestone else None
            lesson_ids = list(
                await session.scalars(
                    select(ContentChallengeLesson.lesson_id)
                    .where(ContentChallengeLesson.challenge_id == row.challenge_id)
                    .order_by(ContentChallengeLesson.sort)
                )
            )
            quiz_ids = await self._quiz(session, row.challenge_id)
        active = [q for qid in quiz_ids if (q := snapshot.question(qid)) is not None]
        minutes = [
            lesson.estimated_minutes
            for lesson_id in lesson_ids
            if (lesson := snapshot.lesson(lesson_id)) is not None and lesson.estimated_minutes
        ]
        estimated = (
            sum(m for m in minutes if m is not None)
            if minutes
            else math.ceil(len(active) * _SECONDS_PER_QUESTION / 60)
        )
        missing = len(quiz_ids) - len(active)
        readiness: dict[str, Any] = (
            {"status": "READY"}
            if active and missing == 0
            else {"status": "INCOMPLETE", "missing_question_count": missing}
        )
        return ChallengeContent(
            challenge_id=row.challenge_id,
            milestone_id=row.milestone_id,
            journey_id=milestone.journey_id if milestone else "",
            version=_version(journey.current_version if journey else None),
            position=row.sort,
            display_code=f"{milestone.sort if milestone else 0}.{row.sort}",
            title=title_in(row.title, self._locale),
            description=title_in(row.goal, self._locale) or None,
            estimated_minutes=estimated,
            question_count=len(active),
            difficulty_distribution=_distribution(active),
            content_readiness=readiness,
        )

    # --- questions ------------------------------------------------------------

    async def list_questions_for_challenge(
        self, challenge_id: str
    ) -> Sequence[tuple[QuestionContent, int]]:
        async with self._sessionmaker() as session:
            quiz_ids = await self._quiz(session, challenge_id)
        by_id = await self.get_questions_by_ids(quiz_ids)
        served = [by_id[qid] for qid in quiz_ids if qid in by_id]
        return [(question, position) for position, question in enumerate(served, start=1)]

    async def get_questions_by_ids(self, question_ids: Sequence[str]) -> dict[str, QuestionContent]:
        snapshot = await self._snapshots.get()
        active = [q for qid in dict.fromkeys(question_ids) if (q := snapshot.question(qid))]
        if not active:
            return {}
        bodies, _missing = await self._bodies.get_question_revisions(
            [QuestionRef(q.question_id, q.version) for q in active], self._locale
        )
        return {
            q.question_id: self._question(snapshot, q, body)
            for q in active
            if (body := bodies.get(q.question_id)) is not None
        }

    def _question(
        self, snapshot: ContentSnapshot, question: ActiveQuestion, body: BoostQuestion
    ) -> QuestionContent:
        translation = body.translation
        options = (
            [
                {
                    "option_id": option.id,
                    "text": option.text or _text(option.blocks),
                    "image_urls": [],
                    "position": position,
                }
                for position, option in enumerate(translation.options, start=1)
            ]
            if translation
            else []
        )
        text = ""
        if translation is not None:
            text = translation.question_text or _text(translation.prompt)
        home = snapshot.lesson(question.home_lesson_id) if question.home_lesson_id else None
        explanation = question.explanation
        return QuestionContent(
            question_id=question.question_id,
            question_version=_version(question.version),
            question_type=_TYPES.get((question.type or "").lower(), "SINGLE_CHOICE"),
            question_text=text,
            difficulty=question.difficulty,
            level=question.level,
            image_urls=[],
            has_image_reference="image" in question.media_kinds or bool(body.shared.media_id),
            options=options,
            correct_answer={"option_ids": [question.correct_option_key]},
            explanation=explanation.get(self._locale, explanation.get("sv-SE")),
            connected_chapters=[title_in(home.title, self._locale)] if home else [],
        )

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    async def _quiz(session: AsyncSession, challenge_id: str) -> list[str]:
        return list(
            await session.scalars(
                select(ContentChallengeQuestion.question_id)
                .where(ContentChallengeQuestion.challenge_id == challenge_id)
                .order_by(ContentChallengeQuestion.sort)
            )
        )

    @staticmethod
    async def _quizzes(session: AsyncSession, milestone_ids: list[str]) -> dict[str, list[str]]:
        """Challenge ids per milestone, in order."""
        rows = await session.execute(
            select(ContentChallenge.milestone_id, ContentChallenge.challenge_id)
            .where(ContentChallenge.milestone_id.in_(milestone_ids))
            .order_by(ContentChallenge.sort)
        )
        result: dict[str, list[str]] = {}
        for milestone_id, challenge_id in rows:
            result.setdefault(milestone_id, []).append(challenge_id)
        return result

    async def _active_quiz_questions(
        self, snapshot: ContentSnapshot, challenge_ids: list[str]
    ) -> dict[str, list[ActiveQuestion]]:
        if not challenge_ids:
            return {}
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(ContentChallengeQuestion.challenge_id, ContentChallengeQuestion.question_id)
                .where(ContentChallengeQuestion.challenge_id.in_(challenge_ids))
                .order_by(ContentChallengeQuestion.sort)
            )
            result: dict[str, list[ActiveQuestion]] = {}
            for challenge_id, question_id in rows:
                question = snapshot.question(question_id)
                if question is not None:
                    result.setdefault(challenge_id, []).append(question)
        return result
