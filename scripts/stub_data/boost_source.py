"""Reads today's published modules, lessons and questions from Boost's delivery API.

Only what the generator needs is read: ids, a lesson's module, and a question's
lesson, subject and difficulty. Never text, never answers.

Field names follow ``fordona_connect.clients.boost.models``, which are still
inferred from Boost's docs (README, "Verifying against live Boost"). Like that
client, this accepts both the documented ``shared``/``translation`` nesting and a
flat item.
"""

from collections.abc import Iterator, Mapping
from typing import Any

import httpx

from scripts.stub_data.generator import Lesson, Question

PAGE_SIZE = 250  # Boost's documented maximum
MAX_PAGES = 400  # 100,000 items: a runaway guard, far above any real bank
LOCALE = "sv-SE"


class BoostSourceError(RuntimeError):
    pass


def _shared(item: Mapping[str, Any]) -> Mapping[str, Any]:
    shared = item.get("shared")
    return shared if isinstance(shared, Mapping) else item


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _items(http: httpx.Client, path: str) -> Iterator[Mapping[str, Any]]:
    for page in range(1, MAX_PAGES + 1):
        response = http.get(path, params={"page": page, "pageSize": PAGE_SIZE, "locale": LOCALE})
        if response.status_code != 200:
            raise BoostSourceError(
                f"GET {path} page {page} -> {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        items = body.get("items", [])
        yield from items
        if not items or page * PAGE_SIZE >= int(body.get("total", 0)):
            return
    raise BoostSourceError(f"GET {path}: more than {MAX_PAGES} pages")


def fetch(http: httpx.Client) -> tuple[list[Lesson], list[Question]]:
    """Published lessons (of published modules) and every published question."""
    module_ids = {str(m["id"]) for m in _items(http, "/v1/delivery/modules")}
    lessons = [
        Lesson(id=str(item["id"]), module_id=str(_shared(item)["moduleId"]))
        for item in _items(http, "/v1/delivery/lessons")
        if str(_shared(item).get("moduleId")) in module_ids
    ]
    questions = []
    for item in _items(http, "/v1/delivery/questions"):
        shared = _shared(item)
        questions.append(
            Question(
                id=str(item["id"]),
                lesson_id=_str_or_none(shared.get("lessonId")),
                subject_id=_str_or_none(shared.get("subjectId")),
                difficulty=_int_or_none(shared.get("difficulty")),
            )
        )
    return lessons, questions
