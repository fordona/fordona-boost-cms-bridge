"""Choosing an attempt's questions (ported from the engine's selectors).

* ``lesson-bank-v1`` (default): every active question whose home is the lesson.
* ``challenge-v1``: the quiz of the learning-journey challenge linked to the
  lesson, in the challenge's order; falls back to the lesson bank when the
  lesson has no (unambiguous) challenge or the quiz has no active question.

Selection is pure: the same snapshot gives the same questions, so a lesson's
question count can be previewed without starting an attempt.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from fordona_connect.learning.content.snapshot import ContentSnapshot


class Strategy(StrEnum):
    LESSON_BANK = "lesson-bank-v1"
    CHALLENGE = "challenge-v1"


@dataclass(frozen=True, slots=True)
class QuestionRef:
    question_id: str
    version: str
    challenge_id: str | None = None


@dataclass(frozen=True, slots=True)
class Selection:
    refs: Sequence[QuestionRef]
    strategy: Strategy
    reason: str


def select_questions(snapshot: ContentSnapshot, lesson_id: str, strategy: Strategy) -> Selection:
    if strategy is Strategy.CHALLENGE:
        challenge = snapshot.challenge_for(lesson_id)
        if challenge is not None:
            refs = [
                QuestionRef(question.question_id, question.version, challenge.challenge_id)
                for question_id in challenge.question_ids
                if (question := snapshot.question(question_id)) is not None
            ]
            if refs:
                return Selection(refs, strategy, "challenge:curated-quiz")
        return _bank(snapshot, lesson_id, strategy, "no-challenge:lesson-bank-fallback")
    return _bank(snapshot, lesson_id, strategy, "lesson-bank:all-active-questions")


def _bank(snapshot: ContentSnapshot, lesson_id: str, strategy: Strategy, reason: str) -> Selection:
    questions = snapshot.questions_of(lesson_id)
    if not questions:
        return Selection((), strategy, "no-active-questions")
    return Selection(
        [QuestionRef(question.question_id, question.version) for question in questions],
        strategy,
        reason,
    )
