"""Content validation rules (ported from the engine's QuestionValidator)."""

import pytest

from fordona_connect.learning.content.validation import (
    ExclusionReason,
    Level,
    QuestionCandidate,
    lesson_is_visible,
    level_for,
    validate_question,
)

LOCALES = ("sv-SE", "en-GB")


def candidate(**overrides: object) -> QuestionCandidate:
    values: dict[str, object] = {
        "question_id": "q1",
        "option_keys": ["a", "b", "c"],
        "correct_option_key": "b",
        "difficulty": 3,
        "domain_code": "traffic",
        "locales_present": set(LOCALES),
    }
    values.update(overrides)
    return QuestionCandidate(**values)  # type: ignore[arg-type]


def test_a_complete_question_is_accepted() -> None:
    assert validate_question(candidate(), LOCALES) is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"option_keys": []}, ExclusionReason.NO_OPTIONS),
        ({"option_keys": ["a", "a"]}, ExclusionReason.DUPLICATE_OPTION_KEYS),
        ({"correct_option_key": None}, ExclusionReason.CORRECT_KEY_NOT_AMONG_OPTIONS),
        ({"correct_option_key": "z"}, ExclusionReason.CORRECT_KEY_NOT_AMONG_OPTIONS),
        ({"difficulty": 0}, ExclusionReason.DIFFICULTY_OUT_OF_RANGE),
        ({"difficulty": 6}, ExclusionReason.DIFFICULTY_OUT_OF_RANGE),
        ({"difficulty": None}, ExclusionReason.DIFFICULTY_OUT_OF_RANGE),
        ({"domain_code": " "}, ExclusionReason.DOMAIN_UNKNOWN),
        ({"domain_code": None}, ExclusionReason.DOMAIN_UNKNOWN),
        ({"locales_present": {"sv-SE"}}, ExclusionReason.LOCALE_MISSING),
    ],
)
def test_each_rule_excludes_with_its_reason(
    overrides: dict[str, object], reason: ExclusionReason
) -> None:
    assert validate_question(candidate(**overrides), LOCALES) is reason


def test_the_first_broken_rule_wins() -> None:
    broken = candidate(option_keys=["a", "a"], difficulty=9, domain_code=None)
    assert validate_question(broken, LOCALES) is ExclusionReason.DUPLICATE_OPTION_KEYS


@pytest.mark.parametrize(
    ("difficulty", "level"),
    [(1, Level.EASY), (2, Level.EASY), (3, Level.MEDIUM), (4, Level.HARD), (5, Level.HARD)],
)
def test_difficulty_maps_to_three_levels(difficulty: int, level: Level) -> None:
    assert level_for(difficulty) is level


@pytest.mark.parametrize(
    ("theory", "question", "visible"),
    [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
)
def test_a_lesson_needs_theory_and_a_question(theory: bool, question: bool, visible: bool) -> None:
    assert lesson_is_visible(has_theory=theory, has_active_question=question) is visible
