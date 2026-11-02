"""Boost upstream models → API schemas.

These functions are the allowlist. Every field the frontend receives is named
here explicitly, so new upstream fields (answers above all) cannot pass through
on their own. ``aiContextSummary`` is intentionally not mapped either: it is
meant for the AI layer, not for learners.
"""

from boost_bridge.clients.boost.models import BoostEntity, BoostLesson, Resource
from boost_bridge.schemas.lessons import Lesson, LessonResource, LessonSummary


def _asset_base(entity: BoostEntity, fallback: str) -> str:
    """The item's own ``assetBaseUrl`` (Boost's documented source), else our configured prefix."""
    return (entity.asset_base_url or fallback).rstrip("/")


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
        url=f"{asset_base_url}/{resource.file_id}",
        placement=resource.placement,
    )


def to_lesson(lesson: BoostLesson, fallback_asset_base_url: str) -> Lesson:
    asset_base_url = _asset_base(lesson, fallback_asset_base_url)
    summary = to_lesson_summary(lesson)
    return Lesson(
        **summary.model_dump(),
        content_html=lesson.translation.content_html if lesson.translation else None,
        resources=[_resource(r, asset_base_url) for r in lesson.resources],
    )
