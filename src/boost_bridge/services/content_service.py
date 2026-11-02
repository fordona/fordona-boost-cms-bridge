"""Theory content use cases: fetch through the cache, map to API schemas."""

from dataclasses import dataclass

from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.schemas.common import Page
from boost_bridge.schemas.lessons import Lesson, LessonSummary
from boost_bridge.services import mappers
from boost_bridge.services.content_cache import ContentCache


@dataclass(frozen=True, slots=True)
class Served[T]:
    """A response value plus whether any part came from the degraded fallback."""

    value: T
    stale: bool


class ContentService:
    def __init__(self, cache: ContentCache, *, asset_base_url: str) -> None:
        self._cache = cache
        self._assets = asset_base_url

    # --- lessons -------------------------------------------------------------

    async def list_lessons(
        self,
        locale: str,
        *,
        page: int,
        page_size: int,
        module_id: str | None = None,
        slug: str | None = None,
    ) -> Served[Page[LessonSummary]]:
        result = await self._cache.get(
            BoostRequests.lessons(
                locale, page=page, page_size=page_size, module_id=module_id, slug=slug
            )
        )
        upstream = result.value
        return Served(
            Page[LessonSummary](
                items=[mappers.to_lesson_summary(lesson) for lesson in upstream.items],
                total=upstream.total,
                page=upstream.page,
                page_size=upstream.page_size,
                as_of=upstream.as_of,
            ),
            result.degraded,
        )

    async def get_lesson(self, lesson_id: str, locale: str) -> Served[Lesson]:
        result = await self._cache.get(BoostRequests.lesson(lesson_id, locale))
        return Served(mappers.to_lesson(result.value, self._assets), result.degraded)
