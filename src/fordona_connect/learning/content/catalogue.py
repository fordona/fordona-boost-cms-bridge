"""Fetching Boost's published catalogue, every locale, for one sync."""

import asyncio
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from fordona_connect.clients.boost.client import BoostClient, BoostRequest, BoostRequests
from fordona_connect.clients.boost.errors import BoostNotFound
from fordona_connect.clients.boost.grading import BoostGradingRevision
from fordona_connect.clients.boost.models import (
    BoostItems,
    BoostLearningJourney,
    BoostLesson,
    BoostMockExam,
    BoostModel,
    BoostModule,
    BoostQuestion,
)
from fordona_connect.core.logging import get_logger

log = get_logger(__name__)

# Concurrent grading calls during one sync. Only new revisions are fetched, so
# this matters on the first sync and after a large publish.
_GRADING_CONCURRENCY = 8


@dataclass(frozen=True, slots=True)
class LocaleCatalogue:
    """Everything Boost publishes, in one locale, in Boost's own list order."""

    modules: list[BoostModule]
    lessons: list[BoostLesson]
    questions: list[BoostQuestion]
    mock_exams: list[BoostMockExam]
    journeys: list[BoostLearningJourney]


@dataclass(frozen=True, slots=True)
class Catalogue:
    """The catalogue per locale. ``default_locale`` decides structure and order."""

    default_locale: str
    by_locale: Mapping[str, LocaleCatalogue]

    @property
    def default(self) -> LocaleCatalogue:
        return self.by_locale[self.default_locale]


async def fetch_catalogue(
    client: BoostClient, locales: Collection[str], *, default_locale: str, page_size: int
) -> Catalogue:
    ordered = [default_locale, *(locale for locale in locales if locale != default_locale)]
    fetched = await asyncio.gather(
        *(_fetch_locale(client, locale, page_size) for locale in ordered)
    )
    return Catalogue(
        default_locale=default_locale, by_locale=dict(zip(ordered, fetched, strict=True))
    )


async def fetch_grading(
    client: BoostClient, refs: Collection[tuple[str, str]]
) -> dict[tuple[str, str], BoostGradingRevision | None]:
    """Grading revisions for ``(question_id, version)`` refs; ``None`` where Boost has none.

    Any failure other than a 404 propagates, so the sync aborts and retries later
    rather than recording a question as ungradable because of a transient error.
    """
    semaphore = asyncio.Semaphore(_GRADING_CONCURRENCY)

    async def one(ref: tuple[str, str]) -> BoostGradingRevision | None:
        async with semaphore:
            try:
                return await client.fetch(BoostRequests.grading_revision(*ref))
            except BoostNotFound:
                log.warning("grading_revision_missing", question_id=ref[0], version=ref[1])
                return None

    ordered = sorted(set(refs))
    results = await asyncio.gather(*(one(ref) for ref in ordered))
    return dict(zip(ordered, results, strict=True))


async def _fetch_locale(client: BoostClient, locale: str, page_size: int) -> LocaleCatalogue:
    modules, lessons, questions, mock_exams, journeys = await asyncio.gather(
        _all_modules(client, locale, page_size),
        _all_lessons(client, locale, page_size),
        _all_questions(client, locale, page_size),
        _optional_items(client, BoostRequests.mock_exams(locale)),
        _optional_items(client, BoostRequests.learning_journeys(locale)),
    )
    return LocaleCatalogue(
        modules=modules,
        lessons=lessons,
        questions=questions,
        mock_exams=mock_exams,
        journeys=journeys,
    )


async def _optional_items[T: BoostModel](
    client: BoostClient, request: BoostRequest[BoostItems[T]]
) -> list[T]:
    """An unpaged catalogue; a 404 means Boost has none here, not a failure."""
    try:
        return list((await client.fetch(request)).items)
    except BoostNotFound:
        log.warning("boost_catalogue_missing", resource=request.resource, locale=request.locale)
        return []


async def _all_modules(client: BoostClient, locale: str, page_size: int) -> list[BoostModule]:
    items: list[BoostModule] = []
    page = 1
    while True:
        result = await client.fetch(BoostRequests.modules(locale, page=page, page_size=page_size))
        items.extend(result.items)
        if len(result.items) < page_size or len(items) >= result.total:
            return items
        page += 1


async def _all_lessons(client: BoostClient, locale: str, page_size: int) -> list[BoostLesson]:
    items: list[BoostLesson] = []
    page = 1
    while True:
        result = await client.fetch(BoostRequests.lessons(locale, page=page, page_size=page_size))
        items.extend(result.items)
        if len(result.items) < page_size or len(items) >= result.total:
            return items
        page += 1


async def _all_questions(client: BoostClient, locale: str, page_size: int) -> list[BoostQuestion]:
    items: list[BoostQuestion] = []
    page = 1
    while True:
        result = await client.fetch(BoostRequests.questions(locale, page=page, page_size=page_size))
        items.extend(result.items)
        if len(result.items) < page_size or len(items) >= result.total:
            return items
        page += 1
