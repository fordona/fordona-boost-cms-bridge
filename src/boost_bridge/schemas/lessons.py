from datetime import datetime

from pydantic import Field

from boost_bridge.schemas.common import APIModel, ContentId, Localized


class LessonResource(APIModel):
    type: str = Field(examples=["image"])
    url: str
    placement: str | None


class LessonSummary(Localized):
    """A lesson (a "chapter" in the Theory App) without its body. Used in lists."""

    id: ContentId
    version: str | None
    module_id: str | None
    title: str | None
    slug: str | None
    estimated_read_minutes: int | None
    updated_at: datetime | None = None


class Lesson(LessonSummary):
    content_html: str | None = Field(
        description="Editor-authored HTML from Boost, a trusted source. Passed through as-is."
    )
    resources: list[LessonResource]
