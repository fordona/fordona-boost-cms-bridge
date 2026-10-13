"""Boost upstream models → API schemas.

These functions are the allowlist. Every field the frontend receives is named
here explicitly, so new upstream fields (answers above all) cannot pass through
on their own. ``aiContextSummary`` is intentionally not mapped either: it is
meant for the AI layer, not for learners.
"""

from boost_bridge.clients.boost.models import BoostLesson, BoostModule, BoostQuestion, Resource
from boost_bridge.schemas.common import Media
from boost_bridge.schemas.lessons import Lesson, LessonResource, LessonSummary
from boost_bridge.schemas.modules import Module
from boost_bridge.schemas.questions import Question, QuestionOption


def asset_url(asset_base_url: str, asset_id: str | None) -> str | None:
    # UNVERIFIED: assumes media/file ids are the public asset ids served at
    # /assets/{assetId} once published (design doc §12).
    return f"{asset_base_url}/assets/{asset_id}" if asset_id else None


def to_module(module: BoostModule, asset_base_url: str) -> Module:
    translation = module.translation
    return Module(
        id=module.id,
        version=module.version,
        locale=module.locale,
        available_locales=module.available_locales,
        title=translation.title if translation else None,
        slug=translation.slug if translation else None,
        description=translation.description if translation else None,
        icon_url=asset_url(asset_base_url, module.shared.icon_id),
        cover_image_url=asset_url(asset_base_url, module.shared.cover_image_id),
        updated_at=module.updated_at,
    )


def to_lesson_summary(lesson: BoostLesson) -> LessonSummary:
    translation = lesson.translation
    return LessonSummary(
        id=lesson.id,
        version=lesson.version,
        locale=lesson.locale,
        available_locales=lesson.available_locales,
        module_id=lesson.shared.module_id,
        title=translation.title if translation else None,
        slug=translation.slug if translation else None,
        estimated_read_minutes=lesson.shared.estimated_read_minutes,
        updated_at=lesson.updated_at,
    )


def _resource(resource: Resource, asset_base_url: str) -> LessonResource:
    return LessonResource(
        type=resource.type,
        url=f"{asset_base_url}/assets/{resource.file_id}",
        placement=resource.placement,
    )


def to_lesson(lesson: BoostLesson, asset_base_url: str) -> Lesson:
    summary = to_lesson_summary(lesson)
    return Lesson(
        **summary.model_dump(),
        content_html=lesson.translation.content_html if lesson.translation else None,
        resources=[_resource(r, asset_base_url) for r in lesson.resources],
    )


def to_question(question: BoostQuestion, asset_base_url: str) -> Question:
    shared = question.shared
    translation = question.translation
    media_url = asset_url(asset_base_url, shared.media_id)
    return Question(
        id=question.id,
        version=question.version,
        locale=question.locale,
        available_locales=question.available_locales,
        type=shared.type,
        module_id=shared.module_id,
        lesson_id=shared.lesson_id,
        subject_id=shared.subject_id,
        difficulty=shared.difficulty,
        points=shared.points,
        question_text=translation.question_text if translation else None,
        options=[
            QuestionOption(id=option.id, text=option.text)
            for option in (translation.options if translation else [])
        ],
        media=Media(type=shared.media_type or "image", url=media_url) if media_url else None,
    )
