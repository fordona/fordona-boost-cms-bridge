"""Loads the generated stub data (``stub-data/templates.json``, ``synthetic.json``).

Written by ``scripts/generate_stub_templates.py`` (tracker P2.T2). This module
only reads them; it never writes.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMPLATES_FILE = "templates.json"
SYNTHETIC_FILE = "synthetic.json"


@dataclass(frozen=True, slots=True)
class GeneratedData:
    """Indexed view of both generated files, as of the last ``load``."""

    generation: int
    templates: dict[str, dict[str, Any]] = field(default_factory=dict)  # by template id
    templates_by_lesson: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    templates_by_module: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    synthetic_questions: dict[str, dict[str, Any]] = field(default_factory=dict)  # by question id
    synthetic_by_lesson: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Learning Journeys/Challenges and mock exams (2026-11-06) have no authoring of their own yet,
    # here or on today's Boost - synthesized straight from the loaded templates, below.
    challenges: dict[str, dict[str, Any]] = field(default_factory=dict)  # by challenge id
    journeys: dict[str, dict[str, Any]] = field(default_factory=dict)  # by journey id
    mock_exams: dict[str, dict[str, Any]] = field(default_factory=dict)  # by mock exam id

    def template_question_ids(self, template_id: str) -> list[str]:
        template = self.templates.get(template_id)
        if template is None:
            return []
        return [q["questionId"] for q in template["questions"]]

    def is_synthetic(self, question_id: str) -> bool:
        return question_id in self.synthetic_questions


def _plain_text(blocks: list[dict[str, Any]]) -> str | None:
    """The first text block's markdown, for the legacy plain-text fields (§13.4
    says ``questionText``/``options[].text`` "stay for existing consumers")."""
    for block in blocks:
        if block["type"] == "text":
            markdown: str = block["markdown"]
            return markdown
    return None


def synthetic_delivery_item(question: dict[str, Any], locale: str) -> dict[str, Any]:
    """A synthetic question in the §13.4 delivery shape (answer-free)."""
    available = question["translations"]
    translation = available.get(locale, available["sv-SE"])
    options = [
        {
            "id": option["id"],
            "text": _plain_text(option["blocks"]),
            "blocks": option["blocks"],
        }
        for option in translation["options"]
    ]
    return {
        "id": question["id"],
        "version": question["version"],
        "locale": locale,
        "shared": {
            "lessonId": question["lessonId"],
            "moduleId": question["moduleId"],
            "subjectId": question["subjectId"],
            "difficulty": question["difficulty"],
            "type": question["type"],
            "topicKey": question["topicKey"],
        },
        "translation": {
            "questionText": _plain_text(translation["prompt"]),
            "options": options,  # each {id, text, blocks}: legacy field + the new one
            "prompt": translation["prompt"],
        },
    }


def synthetic_grading_item(question: dict[str, Any]) -> dict[str, Any]:
    """A synthetic question in the §13.4 grading shape (all locales)."""
    return {
        "id": question["id"],
        "version": question["version"],
        "correctOptionId": question["correctOptionId"],
        "explanation": question["explanation"],
    }


def _build_challenges(
    templates_by_lesson: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """One challenge per lesson, synthesized from that lesson's own template(s). Picks the
    lowest-``sort`` template when a lesson has more than one, so the stub's own fixture data
    respects the product's one-lesson-one-challenge assumption (fordona-engine
    ``ContentSnapshot``, 2026-11-06) rather than handing it ambiguous data to exercise that
    assumption's own fallback with."""
    challenges: dict[str, dict[str, Any]] = {}
    for lesson_id, lesson_templates in templates_by_lesson.items():
        chosen = min(lesson_templates, key=lambda t: t["sort"])
        challenge_id = f"challenge-{chosen['id']}"
        questions = sorted(chosen["questions"], key=lambda q: q["sort"])
        challenges[challenge_id] = {
            "id": challenge_id,
            "title": chosen["titles"],
            "goal": {locale: f"Clara {title}" for locale, title in chosen["titles"].items()},
            "lessonId": lesson_id,
            "moduleId": chosen["moduleId"],
            "sort": chosen["sort"],
            "questionIds": [q["questionId"] for q in questions],
        }
    return challenges


def _build_journeys(challenges: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One milestone per module, challenges ordered by their lesson's own sort, all under a single
    journey — there is no concept of more than one journey to synthesize from today's module/lesson
    data."""
    if not challenges:
        return {}
    by_module: dict[str, list[dict[str, Any]]] = {}
    for challenge in challenges.values():
        by_module.setdefault(challenge["moduleId"], []).append(challenge)

    milestones = []
    for module_id in sorted(by_module, key=lambda m: int(m) if m.isdigit() else m):
        module_challenges = sorted(by_module[module_id], key=lambda c: c["sort"])
        milestones.append(
            {
                "id": f"milestone-{module_id}",
                "title": {"sv-SE": f"Modul {module_id}", "en-GB": f"Module {module_id}"},
                "description": {},
                "challenges": module_challenges,
            }
        )
    journey_id = "journey-1"
    return {
        journey_id: {
            "id": journey_id,
            "title": {"sv-SE": "Resan mot korkortet", "en-GB": "The road to your licence"},
            "description": {},
            "milestones": milestones,
        }
    }


def _build_mock_exams(templates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One mock exam, its question list a deduplicated concatenation of every template's questions
    (in template-id order) up to ``question_count`` — there is no mock-exam authoring of its own on
    today's Boost or this stub to synthesize from instead."""
    question_count = 60
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for template in sorted(templates.values(), key=lambda t: t["id"]):
        for q in sorted(template["questions"], key=lambda q: q["sort"]):
            if q["questionId"] not in seen:
                seen.add(q["questionId"])
                ordered_ids.append(q["questionId"])

    if not ordered_ids:
        return {}
    selected = ordered_ids[:question_count]
    exam_id = "exam-1"
    return {
        exam_id: {
            "id": exam_id,
            "version": "1",
            "name": {"sv-SE": "Teoriprov A", "en-GB": "Theory Exam A"},
            "description": {"sv-SE": "Ett fullstandigt teoriprov", "en-GB": "A full theory exam"},
            "questionCount": question_count,
            "questionIds": selected,
            "complete": len(selected) >= question_count,
        }
    }


def _empty() -> GeneratedData:
    return GeneratedData(generation=0)


def load(data_dir: Path) -> GeneratedData:
    """Reads both files; an absent file is treated as empty (nothing generated yet)."""
    templates_path = data_dir / TEMPLATES_FILE
    synthetic_path = data_dir / SYNTHETIC_FILE
    if not templates_path.exists() and not synthetic_path.exists():
        return _empty()

    templates_doc: dict[str, Any] = (
        json.loads(templates_path.read_text(encoding="utf-8")) if templates_path.exists() else {}
    )
    synthetic_doc: dict[str, Any] = (
        json.loads(synthetic_path.read_text(encoding="utf-8")) if synthetic_path.exists() else {}
    )

    templates_by_id: dict[str, dict[str, Any]] = {}
    templates_by_lesson: dict[str, list[dict[str, Any]]] = {}
    templates_by_module: dict[str, list[dict[str, Any]]] = {}
    for template in templates_doc.get("templates", []):
        templates_by_id[template["id"]] = template
        templates_by_lesson.setdefault(template["lessonId"], []).append(template)
        templates_by_module.setdefault(template["moduleId"], []).append(template)

    synthetic_by_id: dict[str, dict[str, Any]] = {}
    synthetic_by_lesson: dict[str, list[dict[str, Any]]] = {}
    for question in synthetic_doc.get("questions", []):
        synthetic_by_id[question["id"]] = question
        synthetic_by_lesson.setdefault(question["lessonId"], []).append(question)

    challenges = _build_challenges(templates_by_lesson)
    return GeneratedData(
        generation=int(templates_doc.get("generation", 0)),
        templates=templates_by_id,
        templates_by_lesson=templates_by_lesson,
        templates_by_module=templates_by_module,
        synthetic_questions=synthetic_by_id,
        synthetic_by_lesson=synthetic_by_lesson,
        challenges=challenges,
        journeys=_build_journeys(challenges),
        mock_exams=_build_mock_exams(templates_by_id),
    )
