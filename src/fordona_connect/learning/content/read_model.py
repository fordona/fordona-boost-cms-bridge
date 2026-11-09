"""Turning a fetched catalogue into the rows the content tables should hold.

Pure: no I/O. The writer (``writer.py``) compares these rows with what is stored
and writes only the difference.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fordona_connect.clients.boost.grading import BoostGradingRevision
from fordona_connect.clients.boost.models import BoostLesson, BoostQuestion, ContentBlock
from fordona_connect.core.logging import get_logger
from fordona_connect.learning.content.catalogue import Catalogue
from fordona_connect.learning.content.validation import (
    QuestionCandidate,
    lesson_is_visible,
    level_for,
    validate_question,
)

log = get_logger(__name__)

Row = dict[str, Any]
RevisionRef = tuple[str, str]


@dataclass(slots=True)
class ReadModel:
    """Desired rows per table. Revisions are only the *new* ones, not yet stored."""

    units: list[Row] = field(default_factory=list)
    lessons: list[Row] = field(default_factory=list)
    questions: list[Row] = field(default_factory=list)
    new_revisions: list[Row] = field(default_factory=list)
    mock_exams: list[Row] = field(default_factory=list)
    mock_exam_questions: list[Row] = field(default_factory=list)
    journeys: list[Row] = field(default_factory=list)
    milestones: list[Row] = field(default_factory=list)
    challenges: list[Row] = field(default_factory=list)
    challenge_lessons: list[Row] = field(default_factory=list)
    challenge_questions: list[Row] = field(default_factory=list)


def refs_needing_grading(
    catalogue: Catalogue, stored_correct_keys: Mapping[RevisionRef, str]
) -> set[RevisionRef]:
    """Current question revisions whose answer key is not stored yet.

    Published revisions never change, so a stored one is never fetched again.
    """
    return {
        (question.id, question.version)
        for question in catalogue.default.questions
        if question.version and (question.id, question.version) not in stored_correct_keys
    }


def build_read_model(
    catalogue: Catalogue,
    *,
    stored_correct_keys: Mapping[RevisionRef, str],
    grading: Mapping[RevisionRef, BoostGradingRevision | None],
) -> ReadModel:
    model = ReadModel()
    locales = list(catalogue.by_locale)
    default = catalogue.default

    # --- Units: sort is the position in Boost's module list -----------------
    unit_titles = _texts_per_locale(
        (locale, module.id, module.translation.title if module.translation else None)
        for locale, cat in catalogue.by_locale.items()
        for module in cat.modules
    )
    unit_ids: set[str] = set()
    for sort, module in enumerate(_unique(default.modules), start=1):
        unit_ids.add(module.id)
        model.units.append(
            {
                "unit_id": module.id,
                "sort": sort,
                "title": unit_titles.get(module.id, {}),
                "status": "VISIBLE",
            }
        )

    # --- Lessons: sort is the position within the lesson's own unit ----------
    lesson_titles = _texts_per_locale(
        (locale, lesson.id, lesson.translation.title if lesson.translation else None)
        for locale, cat in catalogue.by_locale.items()
        for lesson in cat.lessons
    )
    lessons_with_theory = {
        lesson.id
        for cat in catalogue.by_locale.values()
        for lesson in cat.lessons
        if _has_theory(lesson)
    }
    per_unit_sort: dict[str, int] = {}
    lesson_ids: set[str] = set()
    lesson_rows: list[Row] = []
    for lesson in _unique(default.lessons):
        unit_id = lesson.shared.module_id
        if unit_id not in unit_ids:
            log.warning("content_lesson_without_unit", lesson_id=lesson.id, unit_id=unit_id)
            continue
        assert unit_id is not None
        per_unit_sort[unit_id] = per_unit_sort.get(unit_id, 0) + 1
        lesson_ids.add(lesson.id)
        lesson_rows.append(
            {
                "lesson_id": lesson.id,
                "unit_id": unit_id,
                "sort": per_unit_sort[unit_id],
                "title": lesson_titles.get(lesson.id, {}),
                "current_version": lesson.version,
                "estimated_minutes": lesson.shared.estimated_read_minutes,
            }
        )

    # --- Questions: validate; stored or freshly fetched answer key ------------
    translated_in: dict[str, set[str]] = {}
    for locale, cat in catalogue.by_locale.items():
        for question in cat.questions:
            if question.translation is not None:
                translated_in.setdefault(question.id, set()).add(locale)

    lessons_with_active_question: set[str] = set()
    for question in _unique(default.questions):
        ref = (question.id, question.version or "")
        revision = grading.get(ref)
        correct_key = stored_correct_keys.get(ref) or (
            revision.correct_option_id if revision is not None else None
        )
        option_keys = _option_keys(question)
        reason = validate_question(
            QuestionCandidate(
                question_id=question.id,
                option_keys=option_keys,
                correct_option_key=correct_key,
                difficulty=question.shared.difficulty,
                domain_code=question.shared.subject_id,
                locales_present=translated_in.get(question.id, set()),
            ),
            required_locales=locales,
        )
        home_lesson_id = question.shared.lesson_id
        model.questions.append(
            {
                "question_id": question.id,
                "home_lesson_id": home_lesson_id,
                "unit_id": question.shared.module_id,
                "current_version": question.version,
                "status": "ACTIVE" if reason is None else "EXCLUDED",
                "exclusion_reason": None if reason is None else reason.value,
            }
        )
        if reason is not None:
            continue
        if home_lesson_id:
            lessons_with_active_question.add(home_lesson_id)
        if ref not in stored_correct_keys and revision is not None:
            # Validation passed, so these are all present.
            assert correct_key is not None
            assert question.shared.difficulty is not None
            assert question.shared.subject_id is not None
            model.new_revisions.append(
                {
                    "question_id": question.id,
                    "version": question.version,
                    "type": question.shared.type,
                    "difficulty": question.shared.difficulty,
                    "level": level_for(question.shared.difficulty).value,
                    "domain_code": question.shared.subject_id,
                    "topic_tag": question.shared.topic_key,
                    "correct_option_key": correct_key,
                    "option_keys": option_keys,
                    "media_kinds": _media_kinds(question),
                    "explanation": revision.explanations(),
                }
            )

    for row in lesson_rows:
        visible = lesson_is_visible(
            has_theory=row["lesson_id"] in lessons_with_theory,
            has_active_question=row["lesson_id"] in lessons_with_active_question,
        )
        model.lessons.append({**row, "status": "VISIBLE" if visible else "HIDDEN"})

    _build_mock_exams(catalogue, model)
    _build_journeys(catalogue, model)
    return model


def _build_mock_exams(catalogue: Catalogue, model: ReadModel) -> None:
    names = _texts_per_locale(
        (locale, exam.id, exam.name)
        for locale, cat in catalogue.by_locale.items()
        for exam in cat.mock_exams
    )
    descriptions = _texts_per_locale(
        (locale, exam.id, exam.description)
        for locale, cat in catalogue.by_locale.items()
        for exam in cat.mock_exams
    )
    for exam in _unique(catalogue.default.mock_exams):
        question_ids = list(dict.fromkeys(exam.question_ids))
        model.mock_exams.append(
            {
                "mock_exam_id": exam.id,
                "name": names.get(exam.id, {}),
                "description": descriptions.get(exam.id, {}),
                "question_count": exam.question_count or len(question_ids),
                "complete": bool(exam.complete),
                "current_version": exam.version,
            }
        )
        model.mock_exam_questions.extend(
            {"mock_exam_id": exam.id, "question_id": question_id, "sort": sort}
            for sort, question_id in enumerate(question_ids, start=1)
        )


def _build_journeys(catalogue: Catalogue, model: ReadModel) -> None:
    texts: dict[str, list[tuple[str, str, str | None]]] = {
        "journey_title": [],
        "journey_description": [],
        "milestone_title": [],
        "milestone_description": [],
        "challenge_title": [],
        "challenge_goal": [],
    }
    for locale, cat in catalogue.by_locale.items():
        for journey in cat.journeys:
            texts["journey_title"].append((locale, journey.id, journey.title))
            texts["journey_description"].append((locale, journey.id, journey.description))
            for milestone in journey.milestones:
                texts["milestone_title"].append((locale, milestone.id, milestone.title))
                texts["milestone_description"].append((locale, milestone.id, milestone.description))
                for challenge in milestone.challenges:
                    texts["challenge_title"].append((locale, challenge.id, challenge.title))
                    texts["challenge_goal"].append((locale, challenge.id, challenge.goal))
    by_kind = {kind: _texts_per_locale(entries) for kind, entries in texts.items()}

    seen_milestones: set[str] = set()
    seen_challenges: set[str] = set()
    for journey in _unique(catalogue.default.journeys):
        model.journeys.append(
            {
                "journey_id": journey.id,
                "title": by_kind["journey_title"].get(journey.id, {}),
                "description": by_kind["journey_description"].get(journey.id, {}),
                "current_version": journey.version,
            }
        )
        for milestone_sort, milestone in enumerate(journey.milestones, start=1):
            if milestone.id in seen_milestones:
                log.warning("content_milestone_duplicate", milestone_id=milestone.id)
                continue
            seen_milestones.add(milestone.id)
            model.milestones.append(
                {
                    "milestone_id": milestone.id,
                    "journey_id": journey.id,
                    "sort": milestone_sort,
                    "title": by_kind["milestone_title"].get(milestone.id, {}),
                    "description": by_kind["milestone_description"].get(milestone.id, {}),
                }
            )
            for challenge_sort, challenge in enumerate(milestone.challenges, start=1):
                if challenge.id in seen_challenges:
                    log.warning("content_challenge_duplicate", challenge_id=challenge.id)
                    continue
                seen_challenges.add(challenge.id)
                model.challenges.append(
                    {
                        "challenge_id": challenge.id,
                        "milestone_id": milestone.id,
                        "sort": challenge_sort,
                        "title": by_kind["challenge_title"].get(challenge.id, {}),
                        "goal": by_kind["challenge_goal"].get(challenge.id, {}),
                    }
                )
                model.challenge_lessons.extend(
                    {"challenge_id": challenge.id, "lesson_id": lesson_id, "sort": sort}
                    for sort, lesson_id in enumerate(dict.fromkeys(challenge.chapter_ids), start=1)
                )
                model.challenge_questions.extend(
                    {"challenge_id": challenge.id, "question_id": question_id, "sort": sort}
                    for sort, question_id in enumerate(
                        dict.fromkeys(challenge.question_ids), start=1
                    )
                )


def _texts_per_locale(
    entries: Iterable[tuple[str, str, str | None]],
) -> dict[str, dict[str, str]]:
    """``(locale, id, text)`` triples as ``{id: {locale: text}}``, skipping missing text."""
    result: dict[str, dict[str, str]] = {}
    for locale, item_id, text in entries:
        if text is not None:
            result.setdefault(item_id, {})[locale] = text
    return result


def _unique[T: Any](items: Iterable[T]) -> list[T]:
    """Items in order, keeping the first of any repeated id."""
    seen: set[str] = set()
    result: list[T] = []
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            result.append(item)
    return result


def _has_theory(lesson: BoostLesson) -> bool:
    translation = lesson.translation
    if translation is None:
        return False
    return bool((translation.content_html or "").strip()) or bool(translation.blocks)


def _option_keys(question: BoostQuestion) -> list[str]:
    if question.translation is None:
        return []
    return [option.id for option in question.translation.options]


def _media_kinds(question: BoostQuestion) -> list[str]:
    """Block types present in the prompt and options, in first-seen order."""
    if question.translation is None:
        return []
    blocks: list[ContentBlock] = list(question.translation.prompt)
    for option in question.translation.options:
        blocks.extend(option.blocks)
    return list(dict.fromkeys(block.type for block in blocks))
