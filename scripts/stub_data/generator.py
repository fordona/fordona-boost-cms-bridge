"""Groups today's Boost questions into stub question templates (plan §4.5).

Pure: no I/O, no clock, no randomness. The same Boost data and the same
previous output always produce byte-identical files (``render``).

Rules, from the plan and the tracker (P2.T2):

* per lesson, eligible questions are sorted by ``(difficulty, id)`` and dealt
  round-robin into ``k = max(1, floor(n / 8))`` templates, so every template gets
  the same difficulty mix and the remainder is spread one per template;
* a lesson with fewer than 3 real questions is topped up to 8 with synthetic
  ``[DEMO]`` questions (``synthetic.py``);
* template and synthetic-question ids come from the reserved range
  (``>= 9,000,000``), are stable across runs and are **never reused**: the next
  free id is carried in the output;
* a template's ``version`` changes only when its membership or order changes; a
  synthetic question's only when its content changes. ``generation`` changes only
  when anything in either file changes, so a re-run on unchanged data is a no-op.
"""

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from scripts.stub_data.synthetic import CATALOGUE_SIZE, synthetic_question

RESERVED_ID_START = 9_000_000
FIRST_TEMPLATE_ID = RESERVED_ID_START + 1
FIRST_SYNTHETIC_QUESTION_ID = 9_500_001
QUESTIONS_PER_TEMPLATE = 8
MIN_REAL_QUESTIONS = 3
TOP_UP_TO = 8
VALID_DIFFICULTIES = range(1, 6)
TEMPLATE_TITLES = {"sv-SE": "Mall {label}", "en-GB": "Template {label}"}


@dataclass(frozen=True, slots=True)
class Lesson:
    id: str
    module_id: str


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    lesson_id: str | None
    subject_id: str | None
    difficulty: int | None


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A question as the dealer sees it: real or synthetic."""

    id: str
    difficulty: int

    @property
    def sort_key(self) -> tuple[int, int]:
        return self.difficulty, int(self.id)


@dataclass
class Report:
    lessons: int = 0
    templates: int = 0
    topped_up_lessons: list[str] = field(default_factory=list)
    skipped_questions: list[str] = field(default_factory=list)
    missing_block_types: list[str] = field(default_factory=list)
    changed: bool = False


@dataclass(frozen=True)
class Output:
    templates: dict[str, Any]
    synthetic: dict[str, Any]
    report: Report


def template_count(n: int) -> int:
    return max(1, n // QUESTIONS_PER_TEMPLATE)


def deal(candidates: Sequence[_Candidate], k: int) -> list[list[_Candidate]]:
    """Round-robin over the (difficulty, id) order: question i goes to template i mod k."""
    ordered = sorted(candidates, key=lambda c: c.sort_key)
    return [ordered[index::k] for index in range(k)]


def render(document: Mapping[str, Any]) -> bytes:
    """The one serialisation used for both files, so equal content is equal bytes."""
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def _eligible(
    questions: Iterable[Question], lessons: Mapping[str, Lesson], report: Report
) -> dict[str, list[Question]]:
    by_lesson: dict[str, list[Question]] = {lesson_id: [] for lesson_id in lessons}
    for question in sorted(questions, key=lambda q: int(q.id)):
        lesson_id = question.lesson_id
        if lesson_id is None or lesson_id not in lessons:
            report.skipped_questions.append(f"{question.id}: lesson {lesson_id!r} is not published")
        elif question.difficulty not in VALID_DIFFICULTIES:
            report.skipped_questions.append(
                f"{question.id}: difficulty {question.difficulty!r} is not 1-5"
            )
        else:
            by_lesson[lesson_id].append(question)
    return by_lesson


def _subject_for(
    module_id: str, questions_by_lesson: Mapping[str, list[Question]], lessons: Mapping[str, Lesson]
) -> str | None:
    """The most common subject in the module, else in the bank (smallest id breaks ties).

    Synthetic questions need a real theory domain, or the engine's sync would
    exclude them as having an unknown domain (plan §4.4).
    """

    def most_common(subjects: Iterable[str | None]) -> str | None:
        counts = Counter(s for s in subjects if s)
        if not counts:
            return None
        return min(counts, key=lambda s: (-counts[s], int(s) if s.isdecimal() else 0, s))

    in_module = [
        q.subject_id
        for lesson_id, qs in questions_by_lesson.items()
        if lessons[lesson_id].module_id == module_id
        for q in qs
    ]
    all_questions = [q for qs in questions_by_lesson.values() for q in qs]
    return most_common(in_module) or most_common(q.subject_id for q in all_questions)


def _previous_synthetic(
    previous: Mapping[str, Any] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    if not previous:
        return {}
    return {(q["lessonId"], q["slot"]): q for q in previous.get("questions", [])}


def _previous_templates(
    previous: Mapping[str, Any] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    if not previous:
        return {}
    return {(t["lessonId"], t["sort"]): t for t in previous.get("templates", [])}


def _content(record: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in ("id", "version")}


def _bump(version: str) -> str:
    return str(int(version) + 1)


def generate(
    lessons: Sequence[Lesson],
    questions: Sequence[Question],
    previous_templates: Mapping[str, Any] | None = None,
    previous_synthetic: Mapping[str, Any] | None = None,
) -> Output:
    report = Report()
    lessons_by_id = {lesson.id: lesson for lesson in sorted(lessons, key=lambda le: int(le.id))}
    questions_by_lesson = _eligible(questions, lessons_by_id, report)
    old_synthetic = _previous_synthetic(previous_synthetic)
    old_templates = _previous_templates(previous_templates)
    next_question_id = int(
        (previous_synthetic or {}).get("nextQuestionId", FIRST_SYNTHETIC_QUESTION_ID)
    )
    next_template_id = int((previous_templates or {}).get("nextTemplateId", FIRST_TEMPLATE_ID))

    synthetic_out: list[dict[str, Any]] = []
    templates_out: list[dict[str, Any]] = []

    for lesson_id, lesson in lessons_by_id.items():
        real = questions_by_lesson[lesson_id]
        candidates = [_Candidate(q.id, q.difficulty or 0) for q in real]

        if len(real) < MIN_REAL_QUESTIONS:
            report.topped_up_lessons.append(lesson_id)
            subject_id = _subject_for(lesson.module_id, questions_by_lesson, lessons_by_id)
            for slot in range(1, TOP_UP_TO - len(real) + 1):
                content = synthetic_question(
                    lesson_id=lesson_id,
                    module_id=lesson.module_id,
                    subject_id=subject_id,
                    variant=(int(lesson_id) + slot) % CATALOGUE_SIZE,
                )
                record = {"lessonId": lesson_id, "slot": slot, **content}
                old = old_synthetic.get((lesson_id, slot))
                if old is None:
                    record_id, version = str(next_question_id), "1"
                    next_question_id += 1
                elif _content(old) == record:
                    record_id, version = old["id"], old["version"]
                else:
                    record_id, version = old["id"], _bump(old["version"])
                synthetic_out.append({"id": record_id, "version": version, **record})
                candidates.append(_Candidate(record_id, int(content["difficulty"])))

        k = template_count(len(candidates))
        for index, members in enumerate(deal(candidates, k), start=1):
            label = chr(ord("A") + index - 1) if index <= 26 else str(index)
            record = {
                "lessonId": lesson_id,
                "moduleId": lesson.module_id,
                "sort": index,
                "titles": {
                    loc: title.format(label=label) for loc, title in TEMPLATE_TITLES.items()
                },
                "questions": [
                    {"questionId": member.id, "sort": position}
                    for position, member in enumerate(members, start=1)
                ],
            }
            old = old_templates.get((lesson_id, index))
            if old is None:
                template_id, version = str(next_template_id), "1"
                next_template_id += 1
            elif _content(old) == record:
                template_id, version = old["id"], old["version"]
            else:
                template_id, version = old["id"], _bump(old["version"])
            templates_out.append({"id": template_id, "version": version, **record})

    synthetic_doc: dict[str, Any] = {
        "nextQuestionId": str(next_question_id),
        "questions": synthetic_out,
    }
    old_generation = int((previous_templates or {}).get("generation", 0))
    templates_doc: dict[str, Any] = {
        "generation": old_generation,
        "nextTemplateId": str(next_template_id),
        "templates": templates_out,
    }
    unchanged = (
        previous_templates is not None
        and previous_synthetic is not None
        and render(templates_doc) == render(previous_templates)
        and render(synthetic_doc) == render(previous_synthetic)
    )
    if not unchanged:
        templates_doc["generation"] = old_generation + 1
        report.changed = True

    report.lessons = len(lessons_by_id)
    report.templates = len(templates_out)
    report.missing_block_types = missing_block_types(synthetic_out)
    return Output(templates_doc, synthetic_doc, report)


def missing_block_types(synthetic: Sequence[Mapping[str, Any]]) -> list[str]:
    """Which §4.6 media the synthetic set fails to demonstrate (tracker P2.T2)."""
    seen: set[str] = set()
    for question in synthetic:
        for translation in question["translations"].values():
            for block in translation["prompt"]:
                seen.add(_block_kind(block))
            for option in translation["options"]:
                for block in option["blocks"]:
                    seen.add(_block_kind(block))
                    if block["type"] == "image":
                        seen.add("option_image")
        for blocks in question["explanation"].values():
            for block in blocks:
                seen.add(_block_kind(block))
    required = {
        "text",
        "image",
        "option_image",
        "animation:lottie",
        "animation:video_loop",
        "video",
        "audio",
        "rule_card",
    }
    return sorted(required - seen)


def _block_kind(block: Mapping[str, Any]) -> str:
    if block["type"] == "animation":
        return f"animation:{block['format']}"
    return str(block["type"])
