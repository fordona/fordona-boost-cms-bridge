"""Which synced content may be delivered (ported from the engine's validators).

Pure functions: no I/O, so the rules are tested on their own.
"""

from collections.abc import Collection, Set
from dataclasses import dataclass
from enum import StrEnum


class ExclusionReason(StrEnum):
    NO_OPTIONS = "NO_OPTIONS"
    DUPLICATE_OPTION_KEYS = "DUPLICATE_OPTION_KEYS"
    CORRECT_KEY_NOT_AMONG_OPTIONS = "CORRECT_KEY_NOT_AMONG_OPTIONS"
    DIFFICULTY_OUT_OF_RANGE = "DIFFICULTY_OUT_OF_RANGE"
    DOMAIN_UNKNOWN = "DOMAIN_UNKNOWN"
    LOCALE_MISSING = "LOCALE_MISSING"
    # No longer published in Boost. Not in the engine: it never noticed removals.
    REMOVED = "REMOVED"


class Level(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


@dataclass(frozen=True, slots=True)
class QuestionCandidate:
    question_id: str
    option_keys: list[str]
    correct_option_key: str | None
    difficulty: int | None
    domain_code: str | None
    locales_present: Set[str]


def validate_question(
    question: QuestionCandidate, required_locales: Collection[str]
) -> ExclusionReason | None:
    """``None`` if the question may be delivered, otherwise the first rule it breaks.

    The rules run in a fixed order, so a question breaking several always reports
    the same reason.
    """
    if not question.option_keys:
        return ExclusionReason.NO_OPTIONS
    if len(set(question.option_keys)) != len(question.option_keys):
        return ExclusionReason.DUPLICATE_OPTION_KEYS
    if question.correct_option_key is None or (
        question.correct_option_key not in question.option_keys
    ):
        return ExclusionReason.CORRECT_KEY_NOT_AMONG_OPTIONS
    if question.difficulty is None or not 1 <= question.difficulty <= 5:
        return ExclusionReason.DIFFICULTY_OUT_OF_RANGE
    if not question.domain_code or not question.domain_code.strip():
        return ExclusionReason.DOMAIN_UNKNOWN
    if not set(required_locales) <= set(question.locales_present):
        return ExclusionReason.LOCALE_MISSING
    return None


def level_for(difficulty: int) -> Level:
    """Boost's 1-5 difficulty as the app's three levels."""
    if difficulty <= 2:
        return Level.EASY
    if difficulty == 3:
        return Level.MEDIUM
    return Level.HARD


def lesson_is_visible(*, has_theory: bool, has_active_question: bool) -> bool:
    """A lesson is shown only when it has theory to read and at least one question."""
    return has_theory and has_active_question
