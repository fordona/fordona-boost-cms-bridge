"""Theory content use cases: fetch through the cache, map to API schemas."""

import asyncio
from dataclasses import dataclass

from boost_bridge.clients.boost.client import BoostRequests
from boost_bridge.clients.boost.models import BoostPage, BoostQuestion
from boost_bridge.core.logging import get_logger
from boost_bridge.core.security import Learner
from boost_bridge.schemas.common import Page
from boost_bridge.schemas.lessons import Lesson, LessonSummary
from boost_bridge.schemas.modules import Module
from boost_bridge.schemas.questions import LessonQuestions, Question
from boost_bridge.services import mappers
from boost_bridge.services.content_cache import ContentCache
from boost_bridge.services.sequencing import ContentSequencer, SequencingContext

log = get_logger(__name__)

# Boost's documented pageSize maximum is 250. A lesson's full question set is
# collected page by page up to this bound (1,000 questions), so one runaway
# lesson cannot fan out without limit.
_UPSTREAM_PAGE_SIZE = 250
_MAX_LESSON_QUESTION_PAGES = 4


@dataclass(frozen=True, slots=True)
class Served[T]:
    """A response value plus whether any part came from the degraded fallback."""

    value: T
    stale: bool


class ContentService:
    def __init__(
        self, cache: ContentCache, sequencer: ContentSequencer, *, asset_base_url: str
    ) -> None:
        self._cache = cache
        self._sequencer = sequencer
        self._assets = asset_base_url

    # --- modules -------------------------------------------------------------

    async def list_modules(
        self, locale: str, *, page: int, page_size: int, slug: str | None = None
    ) -> Served[Page[Module]]:
        result = await self._cache.get(
            BoostRequests.modules(locale, page=page, page_size=page_size, slug=slug)
        )
        upstream = result.value
        return Served(
            Page[Module](
                items=[mappers.to_module(m, self._assets) for m in upstream.items],
                total=upstream.total,
                page=upstream.page,
                page_size=upstream.page_size,
                as_of=upstream.as_of,
            ),
            result.degraded,
        )

    async def get_module(self, module_id: str, locale: str) -> Served[Module]:
        result = await self._cache.get(BoostRequests.module(module_id, locale))
        return Served(mappers.to_module(result.value, self._assets), result.degraded)

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

    # --- questions -----------------------------------------------------------

    async def list_questions(
        self,
        locale: str,
        *,
        page: int,
        page_size: int,
        module_id: str | None = None,
        lesson_id: str | None = None,
        ids: list[str] | None = None,
    ) -> Served[Page[Question]]:
        result = await self._cache.get(
            BoostRequests.questions(
                locale,
                page=page,
                page_size=page_size,
                module_id=module_id,
                lesson_id=lesson_id,
                ids=ids,
            )
        )
        return Served(self._question_page(result.value), result.degraded)

    async def get_question(self, question_id: str, locale: str) -> Served[Question]:
        result = await self._cache.get(BoostRequests.question(question_id, locale))
        return Served(mappers.to_question(result.value, self._assets), result.degraded)

    async def get_question_revision(
        self, question_id: str, version: str, locale: str
    ) -> Served[Question]:
        # Published revisions are immutable, so ordinary TTLs only ever re-confirm them.
        result = await self._cache.get(
            BoostRequests.question_revision(question_id, version, locale)
        )
        return Served(mappers.to_question(result.value, self._assets), result.degraded)

    async def lesson_questions(
        self, learner: Learner, lesson_id: str, locale: str
    ) -> Served[LessonQuestions]:
        """Every published question of a lesson, run through the sequencer."""
        first = await self._cache.get(
            BoostRequests.questions(
                locale, page=1, page_size=_UPSTREAM_PAGE_SIZE, lesson_id=lesson_id
            )
        )
        pages: list[BoostPage[BoostQuestion]] = [first.value]
        stale = first.degraded

        page_count = -(-first.value.total // _UPSTREAM_PAGE_SIZE)  # ceil
        if page_count > _MAX_LESSON_QUESTION_PAGES:
            log.warning(
                "lesson_questions_truncated",
                lesson_id=lesson_id,
                total=first.value.total,
                served=_MAX_LESSON_QUESTION_PAGES * _UPSTREAM_PAGE_SIZE,
            )
            page_count = _MAX_LESSON_QUESTION_PAGES
        if page_count > 1:
            rest = await asyncio.gather(
                *(
                    self._cache.get(
                        BoostRequests.questions(
                            locale, page=n, page_size=_UPSTREAM_PAGE_SIZE, lesson_id=lesson_id
                        )
                    )
                    for n in range(2, page_count + 1)
                )
            )
            pages.extend(r.value for r in rest)
            stale = stale or any(r.degraded for r in rest)

        candidates = [mappers.to_question(q, self._assets) for page in pages for q in page.items]
        ordered = await self._sequencer.sequence(
            learner,
            candidates,
            SequencingContext(surface="lesson", locale=locale, lesson_id=lesson_id),
        )
        # A sequencer may reorder, filter or select, but never introduce content
        # that is not published in this lesson.
        allowed = {q.id for q in candidates}
        ordered = [q for q in ordered if q.id in allowed]
        return Served(
            LessonQuestions(lesson_id=lesson_id, items=ordered, total=len(ordered)), stale
        )

    def _question_page(self, upstream: BoostPage[BoostQuestion]) -> Page[Question]:
        return Page[Question](
            items=[mappers.to_question(q, self._assets) for q in upstream.items],
            total=upstream.total,
            page=upstream.page,
            page_size=upstream.page_size,
            as_of=upstream.as_of,
        )
