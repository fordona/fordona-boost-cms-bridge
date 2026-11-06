"""Loading the generated files, and shaping a synthetic question for delivery/grading."""

import json
from pathlib import Path
from typing import Any

from scripts.stub_data.generator import Lesson, Question, generate

from boost_stub.data import load, synthetic_delivery_item, synthetic_grading_item


def test_load_with_no_files_is_empty(tmp_path: Path) -> None:
    data = load(tmp_path)

    assert data.generation == 0
    assert data.templates == {}
    assert data.synthetic_questions == {}


def test_load_indexes_templates_by_lesson_and_module(tmp_path: Path) -> None:
    output = generate(
        [Lesson("10", "1"), Lesson("20", "2")],
        [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(9)],
    )
    (tmp_path / "templates.json").write_text(json.dumps(output.templates), encoding="utf-8")
    (tmp_path / "synthetic.json").write_text(json.dumps(output.synthetic), encoding="utf-8")

    data = load(tmp_path)

    assert data.generation == output.templates["generation"]
    template = next(iter(data.templates.values()))
    assert data.templates_by_lesson["10"] == [template]
    assert data.templates_by_module["1"] == [template]
    assert data.template_question_ids(template["id"]) == [
        q["questionId"] for q in template["questions"]
    ]
    # lesson "20" has no real questions, so it is topped up entirely with synthetic ones
    assert data.synthetic_by_lesson["20"]
    assert all(data.is_synthetic(q["id"]) for q in data.synthetic_by_lesson["20"])


def test_load_synthesizes_one_challenge_per_lesson(tmp_path: Path) -> None:
    output = generate(
        [Lesson("10", "1"), Lesson("20", "2")],
        [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(9)],
    )
    (tmp_path / "templates.json").write_text(json.dumps(output.templates), encoding="utf-8")
    (tmp_path / "synthetic.json").write_text(json.dumps(output.synthetic), encoding="utf-8")

    data = load(tmp_path)

    assert set(data.challenges) == {f"challenge-{t['id']}" for t in data.templates.values()}
    for template in data.templates.values():
        challenge = data.challenges[f"challenge-{template['id']}"]
        assert challenge["lessonId"] == template["lessonId"]
        assert challenge["moduleId"] == template["moduleId"]
        assert challenge["questionIds"] == [q["questionId"] for q in template["questions"]]


def test_load_picks_the_lowest_sort_template_when_a_lesson_has_two(tmp_path: Path) -> None:
    """A lesson with two templates must still synthesize exactly one challenge — the engine's
    ContentSnapshot assumes one lesson maps to at most one challenge, and this stub's own fixture
    data should never hand it a violation to exercise that assumption's fallback with."""
    # template_count(16) == 2
    questions = [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(16)]
    output = generate([Lesson("10", "1")], questions)
    (tmp_path / "templates.json").write_text(json.dumps(output.templates), encoding="utf-8")
    (tmp_path / "synthetic.json").write_text(json.dumps(output.synthetic), encoding="utf-8")

    data = load(tmp_path)

    lesson_templates = data.templates_by_lesson["10"]
    assert len(lesson_templates) >= 2, "precondition: lesson '10' needs more than one template"
    challenges_for_lesson = [c for c in data.challenges.values() if c["lessonId"] == "10"]
    assert len(challenges_for_lesson) == 1
    chosen = min(lesson_templates, key=lambda t: t["sort"])
    assert challenges_for_lesson[0]["id"] == f"challenge-{chosen['id']}"


def test_load_groups_challenges_into_one_milestone_per_module_under_a_single_journey(
    tmp_path: Path,
) -> None:
    output = generate(
        [Lesson("10", "1"), Lesson("20", "2")],
        [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(9)],
    )
    (tmp_path / "templates.json").write_text(json.dumps(output.templates), encoding="utf-8")
    (tmp_path / "synthetic.json").write_text(json.dumps(output.synthetic), encoding="utf-8")

    data = load(tmp_path)

    assert len(data.journeys) == 1
    journey = next(iter(data.journeys.values()))
    module_ids = {m["id"] for m in journey["milestones"]}
    assert module_ids == {"milestone-1", "milestone-2"}
    all_challenge_ids = {c["id"] for m in journey["milestones"] for c in m["challenges"]}
    assert all_challenge_ids == set(data.challenges)


def test_load_with_no_templates_has_no_journeys_or_mock_exams(tmp_path: Path) -> None:
    data = load(tmp_path)

    assert data.challenges == {}
    assert data.journeys == {}
    assert data.mock_exams == {}


def test_load_synthesizes_a_mock_exam_from_every_template_questions(tmp_path: Path) -> None:
    output = generate(
        [Lesson("10", "1"), Lesson("20", "2")],
        [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(9)],
    )
    (tmp_path / "templates.json").write_text(json.dumps(output.templates), encoding="utf-8")
    (tmp_path / "synthetic.json").write_text(json.dumps(output.synthetic), encoding="utf-8")

    data = load(tmp_path)

    assert len(data.mock_exams) == 1
    exam = next(iter(data.mock_exams.values()))
    all_template_question_ids = {
        q["questionId"] for t in data.templates.values() for q in t["questions"]
    }
    assert set(exam["questionIds"]) <= all_template_question_ids
    assert len(exam["questionIds"]) == len(set(exam["questionIds"])), "no duplicate question ids"


def test_unknown_template_has_no_question_ids(tmp_path: Path) -> None:
    data = load(tmp_path)
    assert data.template_question_ids("999") == []


def test_is_synthetic_is_false_for_an_unknown_id(tmp_path: Path) -> None:
    data = load(tmp_path)
    assert data.is_synthetic("100") is False


# --- synthetic_delivery_item / synthetic_grading_item -----------------------------


def _synthetic_record() -> dict[str, Any]:
    output = generate([Lesson("10", "1")], [])
    return next(iter(output.synthetic["questions"]))


def test_synthetic_delivery_item_is_answer_free() -> None:
    record = _synthetic_record()

    item = synthetic_delivery_item(record, "sv-SE")

    assert "correctOptionId" not in str(item)
    assert "explanation" not in item["translation"]
    assert item["locale"] == "sv-SE"
    assert item["shared"]["topicKey"] == record["topicKey"]


def test_synthetic_delivery_item_switches_locale() -> None:
    record = _synthetic_record()

    sv = synthetic_delivery_item(record, "sv-SE")
    en = synthetic_delivery_item(record, "en-GB")

    assert sv["translation"]["prompt"] != en["translation"]["prompt"]
    assert sv["translation"]["prompt"][0]["markdown"].startswith("[DEMO]")


def test_synthetic_delivery_item_falls_back_to_swedish_for_an_unknown_locale() -> None:
    record = _synthetic_record()

    item = synthetic_delivery_item(record, "de-DE")

    assert (
        item["translation"]["prompt"]
        == synthetic_delivery_item(record, "sv-SE")["translation"]["prompt"]
    )


def test_synthetic_delivery_item_keeps_option_blocks_and_legacy_text() -> None:
    record = _synthetic_record()

    item = synthetic_delivery_item(record, "sv-SE")

    options = item["translation"]["options"]
    assert all("blocks" in o for o in options)
    assert any(o["text"] is not None for o in options)  # at least one text-bearing option


def test_synthetic_grading_item_has_the_answer_key() -> None:
    """correctOptionId is nested under shared and explanation under translations.{locale} -
    the real Boost shape, confirmed 2026-11-06 (see synthetic_grading_item's own docstring)."""
    record = _synthetic_record()

    item = synthetic_grading_item(record)

    assert item["shared"]["correctOptionId"] == record["correctOptionId"]
    assert set(item["translations"]) == {"sv-SE", "en-GB"}
    assert item["translations"]["sv-SE"]["explanation"] == record["explanation"]["sv-SE"]
