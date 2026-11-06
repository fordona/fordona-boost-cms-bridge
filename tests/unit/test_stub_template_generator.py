"""The Boost stub's template generator (plan §4.5, tracker P2.T2)."""

from collections import Counter
from typing import Any

import pytest
from scripts.stub_data.generator import (
    FIRST_SYNTHETIC_QUESTION_ID,
    FIRST_TEMPLATE_ID,
    RESERVED_ID_START,
    Lesson,
    Output,
    Question,
    generate,
    render,
    template_count,
)
from scripts.stub_data.synthetic import CATALOGUE_SIZE, synthetic_question

from tests.contract.boost_content_v1.blocks import Context, validate_blocks, validate_locale_blocks

LEVEL = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "hard"}  # plan §4.1 default map


def _questions(lesson_id: str, count: int, *, first_id: int, subject: str = "3") -> list[Question]:
    """``count`` questions whose difficulties cycle 1..5."""
    return [
        Question(
            id=str(first_id + n),
            lesson_id=lesson_id,
            subject_id=subject,
            difficulty=n % 5 + 1,
        )
        for n in range(count)
    ]


def _templates_of(output: Output, lesson_id: str) -> list[dict[str, Any]]:
    return [t for t in output.templates["templates"] if t["lessonId"] == lesson_id]


def _member_ids(template: dict[str, Any]) -> list[str]:
    return [q["questionId"] for q in template["questions"]]


def _bank(output: Output, real: list[Question]) -> dict[str, int]:
    difficulties = {q.id: q.difficulty or 0 for q in real}
    difficulties.update({q["id"]: q["difficulty"] for q in output.synthetic["questions"]})
    return difficulties


# --- template count and dealing ------------------------------------------------


@pytest.mark.parametrize(
    ("n", "k"), [(3, 1), (7, 1), (8, 1), (15, 1), (16, 2), (23, 2), (24, 3), (40, 5)]
)
def test_template_count_is_floor_of_n_over_8_at_least_1(n: int, k: int) -> None:
    assert template_count(n) == k


@pytest.mark.parametrize(("n", "sizes"), [(16, [8, 8]), (17, [9, 8]), (26, [9, 9, 8])])
def test_remainder_is_spread_one_per_template(n: int, sizes: list[int]) -> None:
    output = generate([Lesson("10", "1")], _questions("10", n, first_id=100))

    assert [len(t["questions"]) for t in _templates_of(output, "10")] == sizes


def test_every_eligible_question_is_dealt_exactly_once() -> None:
    real = _questions("10", 29, first_id=100)

    output = generate([Lesson("10", "1")], real)

    dealt = [qid for t in _templates_of(output, "10") for qid in _member_ids(t)]
    assert sorted(dealt) == sorted(q.id for q in real)


@pytest.mark.parametrize("n", [8, 16, 17, 24, 29, 40, 47])
def test_difficulty_mix_per_template_is_within_one(n: int) -> None:
    real = _questions("10", n, first_id=100)

    output = generate([Lesson("10", "1")], real)

    difficulty = _bank(output, real)
    per_template = [
        Counter(LEVEL[difficulty[qid]] for qid in _member_ids(t))
        for t in _templates_of(output, "10")
    ]
    for level in ("easy", "medium", "hard"):
        counts = [c[level] for c in per_template]
        assert max(counts) - min(counts) <= 1, f"{level}: {counts}"


def test_members_are_ordered_by_difficulty_then_id() -> None:
    real = _questions("10", 16, first_id=100)

    output = generate([Lesson("10", "1")], real)

    difficulty = _bank(output, real)
    for template in _templates_of(output, "10"):
        keys = [(difficulty[qid], int(qid)) for qid in _member_ids(template)]
        assert keys == sorted(keys)


def test_member_sort_is_its_position() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 9, first_id=100))

    template = _templates_of(output, "10")[0]
    assert [q["sort"] for q in template["questions"]] == list(range(1, 10))


# --- thin lessons --------------------------------------------------------------


@pytest.mark.parametrize(("real_count", "synthetic_count"), [(0, 8), (1, 7), (2, 6)])
def test_thin_lesson_is_topped_up_to_eight(real_count: int, synthetic_count: int) -> None:
    output = generate([Lesson("10", "1")], _questions("10", real_count, first_id=100))

    assert len(output.synthetic["questions"]) == synthetic_count
    assert len(_templates_of(output, "10")[0]["questions"]) == 8
    assert output.report.topped_up_lessons == ["10"]


def test_lesson_with_three_real_questions_is_not_topped_up() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 3, first_id=100))

    assert output.synthetic["questions"] == []
    assert len(_templates_of(output, "10")[0]["questions"]) == 3


def test_synthetic_questions_belong_to_their_lesson() -> None:
    output = generate([Lesson("10", "7")], [])

    for question in output.synthetic["questions"]:
        assert (question["lessonId"], question["moduleId"]) == ("10", "7")
        assert question["topicKey"] == "lesson-10"


def test_synthetic_subject_is_the_modules_most_common() -> None:
    real = _questions("11", 3, first_id=100, subject="4") + _questions(
        "12", 1, first_id=200, subject="5"
    )

    output = generate([Lesson("10", "1"), Lesson("11", "1"), Lesson("12", "2")], real)

    subjects = {q["subjectId"] for q in output.synthetic["questions"] if q["lessonId"] == "10"}
    assert subjects == {"4"}


def test_synthetic_subject_falls_back_to_the_bank() -> None:
    real = _questions("20", 3, first_id=100, subject="6")

    output = generate([Lesson("10", "1"), Lesson("20", "2")], real)

    assert {q["subjectId"] for q in output.synthetic["questions"]} == {"6"}


def test_one_thin_lesson_demonstrates_every_block_type() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 2, first_id=100))

    assert output.report.missing_block_types == []


def test_no_thin_lesson_reports_the_missing_demo_media() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 8, first_id=100))

    assert "video" in output.report.missing_block_types


@pytest.mark.parametrize("variant", range(CATALOGUE_SIZE))
def test_every_synthetic_variant_is_valid_content(variant: int) -> None:
    question = synthetic_question(lesson_id="10", module_id="1", subject_id="3", variant=variant)
    problems: list[str] = []

    for locale, translation in question["translations"].items():
        assert translation["prompt"][0]["markdown"].startswith("[DEMO]")
        problems += validate_blocks(translation["prompt"], Context.PROMPT, path=f"{locale} prompt")
        option_ids = [o["id"] for o in translation["options"]]
        assert question["correctOptionId"] in option_ids
        for option in translation["options"]:
            problems += validate_blocks(option["blocks"], Context.OPTION, path=f"{locale} option")
    problems += validate_locale_blocks(
        question["explanation"], ["sv-SE", "en-GB"], Context.EXPLANATION, path="explanation"
    )

    assert not problems, "\n".join(problems)


def test_synthetic_option_ids_match_across_locales() -> None:
    for variant in range(CATALOGUE_SIZE):
        question = synthetic_question(
            lesson_id="10", module_id="1", subject_id="3", variant=variant
        )
        ids = {
            locale: [o["id"] for o in t["options"]]
            for locale, t in question["translations"].items()
        }
        assert ids["sv-SE"] == ids["en-GB"]


# --- ids -----------------------------------------------------------------------


def test_ids_are_in_the_reserved_range_and_distinct() -> None:
    lessons = [Lesson(str(n), "1") for n in range(10, 14)]
    real = _questions("10", 20, first_id=100) + _questions("11", 1, first_id=200)

    output = generate(lessons, real)

    template_ids = [int(t["id"]) for t in output.templates["templates"]]
    synthetic_ids = [int(q["id"]) for q in output.synthetic["questions"]]
    assert min(template_ids) >= FIRST_TEMPLATE_ID > RESERVED_ID_START
    assert min(synthetic_ids) >= FIRST_SYNTHETIC_QUESTION_ID > RESERVED_ID_START
    assert len(set(template_ids)) == len(template_ids)
    assert len(set(synthetic_ids)) == len(synthetic_ids)


def test_ids_are_decimal_strings() -> None:
    output = generate([Lesson("10", "1")], [])

    assert all(isinstance(t["id"], str) for t in output.templates["templates"])
    assert all(isinstance(q["id"], str) for q in output.synthetic["questions"])


def test_removed_template_id_is_never_reused() -> None:
    first = generate([Lesson("10", "1")], _questions("10", 16, first_id=100))
    removed = {t["id"] for t in first.templates["templates"] if t["sort"] == 2}

    shrunk = generate(
        [Lesson("10", "1")],
        _questions("10", 8, first_id=100),
        first.templates,
        first.synthetic,
    )
    regrown = generate(
        [Lesson("10", "1"), Lesson("11", "1")],
        _questions("10", 8, first_id=100) + _questions("11", 8, first_id=300),
        shrunk.templates,
        shrunk.synthetic,
    )

    assert removed.isdisjoint(t["id"] for t in shrunk.templates["templates"])
    assert removed.isdisjoint(t["id"] for t in regrown.templates["templates"])


# --- versions and generation -----------------------------------------------------


def test_first_run_is_generation_one_with_version_one() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 8, first_id=100))

    assert output.templates["generation"] == 1
    assert {t["version"] for t in output.templates["templates"]} == {"1"}


def test_rerun_on_unchanged_data_changes_nothing() -> None:
    lessons = [Lesson("10", "1"), Lesson("11", "1")]
    real = _questions("10", 17, first_id=100)
    first = generate(lessons, real)

    second = generate(lessons, real, first.templates, first.synthetic)

    assert render(second.templates) == render(first.templates)
    assert render(second.synthetic) == render(first.synthetic)
    assert second.report.changed is False


def test_only_the_changed_lessons_templates_get_a_new_version() -> None:
    lessons = [Lesson("10", "1"), Lesson("11", "1")]
    first = generate(lessons, _questions("10", 8, first_id=100) + _questions("11", 8, first_id=200))

    second = generate(
        lessons,
        _questions("10", 9, first_id=100) + _questions("11", 8, first_id=200),
        first.templates,
        first.synthetic,
    )

    versions = {t["lessonId"]: t["version"] for t in second.templates["templates"]}
    assert versions == {"10": "2", "11": "1"}
    assert second.templates["generation"] == 2
    ids_before = {t["lessonId"]: t["id"] for t in first.templates["templates"]}
    assert {t["lessonId"]: t["id"] for t in second.templates["templates"]} == ids_before


def test_changed_synthetic_content_bumps_its_version_and_keeps_its_id() -> None:
    lessons = [Lesson("10", "1")]
    first = generate(lessons, [])
    edited = {
        **first.synthetic,
        "questions": [
            {**q, "topicKey": "stale"} if q["slot"] == 1 else q
            for q in first.synthetic["questions"]
        ],
    }

    second = generate(lessons, [], first.templates, edited)

    slot_one = next(q for q in second.synthetic["questions"] if q["slot"] == 1)
    original = next(q for q in first.synthetic["questions"] if q["slot"] == 1)
    assert (slot_one["id"], slot_one["version"]) == (original["id"], "2")


def test_question_version_changes_do_not_touch_templates() -> None:
    # Templates hold question ids only: a new question revision is not a template change.
    lessons = [Lesson("10", "1")]
    real = _questions("10", 8, first_id=100)
    first = generate(lessons, real)

    second = generate(lessons, list(real), first.templates, first.synthetic)

    assert second.templates == first.templates


# --- determinism and input hygiene ---------------------------------------------------


def test_output_is_byte_identical_across_runs() -> None:
    lessons = [Lesson("10", "1"), Lesson("11", "2"), Lesson("12", "2")]
    real = _questions("10", 19, first_id=100) + _questions("12", 2, first_id=400)

    first = generate(lessons, real)
    second = generate(list(reversed(lessons)), list(reversed(real)))

    assert render(first.templates) == render(second.templates)
    assert render(first.synthetic) == render(second.synthetic)


def test_render_is_sorted_utf8_json_with_trailing_newline() -> None:
    data = render({"b": "Väjningsplikt", "a": 1})

    assert data == '{\n  "a": 1,\n  "b": "Väjningsplikt"\n}\n'.encode()


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        (Question("100", "99", "3", 2), "not published"),
        (Question("100", None, "3", 2), "not published"),
        (Question("100", "10", "3", None), "not 1-5"),
        (Question("100", "10", "3", 6), "not 1-5"),
    ],
)
def test_ineligible_question_is_skipped_and_reported(question: Question, reason: str) -> None:
    output = generate([Lesson("10", "1")], [question])

    assert all("100" not in _member_ids(t) for t in output.templates["templates"])
    assert len(output.report.skipped_questions) == 1
    assert reason in output.report.skipped_questions[0]


def test_every_lesson_gets_templates() -> None:
    lessons = [Lesson(str(n), "1") for n in range(10, 15)]

    output = generate(lessons, _questions("12", 30, first_id=100))

    assert {t["lessonId"] for t in output.templates["templates"]} == {
        lesson.id for lesson in lessons
    }


def test_template_titles_are_per_locale_labels() -> None:
    output = generate([Lesson("10", "1")], _questions("10", 16, first_id=100))

    titles = [t["titles"] for t in _templates_of(output, "10")]
    assert titles == [
        {"sv-SE": "Mall A", "en-GB": "Template A"},
        {"sv-SE": "Mall B", "en-GB": "Template B"},
    ]
