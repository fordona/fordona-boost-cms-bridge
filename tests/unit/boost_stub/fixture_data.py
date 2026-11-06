"""A small, self-consistent Boost dataset for the stub's live acceptance test.

Two modules; one "rich" lesson with enough real questions to need no
top-up, and two "thin" lessons that the template generator fills out with
synthetic questions — so the stub serves both kinds of content.
"""

from typing import Any

from scripts.stub_data.generator import Lesson, Question

MODULE_1 = "1"
MODULE_2 = "2"
LESSON_RICH = "10"  # module 1, 9 real questions
LESSON_THIN = "11"  # module 1, 1 real question
LESSON_2 = "20"  # module 2, 2 real questions

LESSON_MODULE = {LESSON_RICH: MODULE_1, LESSON_THIN: MODULE_1, LESSON_2: MODULE_2}

QUESTIONS: list[Question] = (
    [Question(str(100 + n), LESSON_RICH, "3", n % 5 + 1) for n in range(9)]
    + [Question("200", LESSON_THIN, "3", 2)]
    + [Question("300", LESSON_2, "4", 3), Question("301", LESSON_2, "4", 1)]
)
LESSONS: list[Lesson] = [
    Lesson(LESSON_RICH, MODULE_1),
    Lesson(LESSON_THIN, MODULE_1),
    Lesson(LESSON_2, MODULE_2),
]


def modules() -> list[dict[str, Any]]:
    return [
        {
            "id": MODULE_1,
            "version": "1",
            "locale": "sv-SE",
            "shared": {},
            "translation": {"title": "Fundamentals"},
        },
        {
            "id": MODULE_2,
            "version": "1",
            "locale": "sv-SE",
            "shared": {},
            "translation": {"title": "Signs"},
        },
    ]


def lessons() -> list[dict[str, Any]]:
    return [
        {
            "id": LESSON_RICH,
            "version": "1",
            "locale": "sv-SE",
            "shared": {"moduleId": MODULE_1, "estimatedReadMinutes": 5},
            "translation": {
                "title": "Right of way",
                "slug": "right-of-way",
                "contentHtml": (
                    "<p>Give way to the right.</p>"
                    "<ul><li>Look both ways</li><li>Slow down</li></ul>"
                ),
            },
        },
        {
            "id": LESSON_THIN,
            "version": "1",
            "locale": "sv-SE",
            "shared": {"moduleId": MODULE_1},
            "translation": {
                "title": "A thin lesson",
                "slug": "thin",
                "contentHtml": "<p>Short theory.</p>",
            },
        },
        {
            "id": LESSON_2,
            "version": "1",
            "locale": "sv-SE",
            "shared": {"moduleId": MODULE_2},
            "translation": {
                "title": "Signs overview",
                "slug": "signs",
                "contentHtml": "<p>Road signs.</p>",
            },
        },
    ]


def questions() -> list[dict[str, Any]]:
    return [
        {
            "id": q.id,
            "version": "1",
            "locale": "sv-SE",
            "shared": {
                "lessonId": q.lesson_id,
                "moduleId": LESSON_MODULE[q.lesson_id or ""],
                "subjectId": q.subject_id,
                "difficulty": q.difficulty,
                "type": "mcq",
            },
            "translation": {
                "questionText": f"What applies in situation {q.id}?",
                "options": [
                    {"id": "o1", "text": "Option A"},
                    {"id": "o2", "text": "Option B"},
                    {"id": "o3", "text": "Option C"},
                ],
            },
        }
        for q in QUESTIONS
    ]


def grading() -> dict[tuple[str, str], dict[str, Any]]:
    """The real shape: correctOptionId under shared, every locale's explanation under
    translations.{locale} in one response — confirmed 2026-11-06, see grading.py's module
    docstring for why this replaced a flat, locale-scoped assumption."""
    return {
        (q.id, "1"): {
            "id": q.id,
            "version": "1",
            "shared": {"correctOptionId": "o2"},
            "translations": {
                "sv-SE": {"explanation": f"<p>Rätt svar för {q.id} är B.</p>"},
                "en-GB": {"explanation": f"<p>The correct answer for {q.id} is B.</p>"},
            },
        }
        for q in QUESTIONS
    }
