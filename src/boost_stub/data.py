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

    return GeneratedData(
        generation=int(templates_doc.get("generation", 0)),
        templates=templates_by_id,
        templates_by_lesson=templates_by_lesson,
        templates_by_module=templates_by_module,
        synthetic_questions=synthetic_by_id,
        synthetic_by_lesson=synthetic_by_lesson,
    )
