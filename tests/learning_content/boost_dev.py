"""Serves the captured Boost dev catalogue (``tests/fixtures/boost_dev_catalogue.json``)
through respx, in Boost's delivery and grading shapes."""

import json
from pathlib import Path
from typing import Any

import httpx
import respx

BASE = "https://boost-dev.test"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "boost_dev_catalogue.json"


def load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _page(request: httpx.Request, items: list[dict[str, Any]]) -> httpx.Response:
    page = int(request.url.params.get("page", 1))
    size = int(request.url.params.get("pageSize", 250))
    chunk = items[(page - 1) * size : page * size]
    return httpx.Response(
        200, json={"items": chunk, "total": len(items), "page": page, "pageSize": size}
    )


class BoostDev:
    def __init__(self) -> None:
        self.data = load()
        self.grading_calls = 0

    def question(self, question_id: str) -> dict[str, Any]:
        return next(q for q in self.data["questions"] if q["id"] == question_id)

    def _module(self, module: dict[str, Any], locale: str) -> dict[str, Any]:
        return {
            "id": module["id"],
            "version": module["version"],
            "translation": {"title": module["title"][locale]},
        }

    def _chapter(self, chapter: dict[str, Any], locale: str) -> dict[str, Any]:
        return {
            "id": chapter["id"],
            "version": chapter["version"],
            "shared": {
                "moduleId": chapter["moduleId"],
                "estimatedReadMinutes": chapter["estimatedReadMinutes"],
            },
            "translation": {
                "title": chapter["title"][locale],
                "contentHtml": f"<h2>{chapter['title'][locale]}</h2><p>Teori.</p>",
            },
        }

    def _question(self, question: dict[str, Any], locale: str) -> dict[str, Any]:
        return {
            "id": question["id"],
            "version": question["version"],
            "shared": {
                "lessonId": question["lessonId"],
                "moduleId": question["moduleId"],
                "subjectId": question["subjectId"],
                "difficulty": question["difficulty"],
                "type": question["type"],
            },
            "translation": question["translations"][locale],
        }

    def _journey(self, journey: dict[str, Any], locale: str) -> dict[str, Any]:
        return {
            "id": journey["id"],
            "version": journey["version"],
            "title": journey["title"][locale],
            "milestones": [
                {
                    "id": m["id"],
                    "title": m["title"][locale],
                    "challenges": [
                        {
                            "id": c["id"],
                            "title": c["title"][locale],
                            "goal": c["goal"][locale],
                            "chapterIds": c["chapterIds"],
                            "questionIds": c["questionIds"],
                        }
                        for c in m["challenges"]
                    ],
                }
                for m in journey["milestones"]
            ],
        }

    def mount(self, router: respx.MockRouter) -> None:
        d = self.data

        def locale(request: httpx.Request) -> str:
            return request.url.params["locale"]

        router.get(f"{BASE}/v1/delivery/modules").mock(
            side_effect=lambda r: _page(r, [self._module(m, locale(r)) for m in d["modules"]])
        )
        router.get(url__regex=rf"{BASE}/v1/delivery/lessons/[^/]+$").mock(
            side_effect=lambda r: httpx.Response(
                200,
                json=self._chapter(
                    next(c for c in d["chapters"] if c["id"] == r.url.path.rsplit("/", 1)[-1]),
                    locale(r),
                ),
            )
        )
        router.get(f"{BASE}/v1/delivery/lessons").mock(
            side_effect=lambda r: _page(r, [self._chapter(c, locale(r)) for c in d["chapters"]])
        )
        router.get(url__regex=rf"{BASE}/v1/delivery/questions/[^/]+/revisions/[^/]+$").mock(
            side_effect=lambda r: httpx.Response(
                200, json=self._question(self.question(r.url.path.split("/")[-3]), locale(r))
            )
        )
        router.get(f"{BASE}/v1/delivery/questions").mock(
            side_effect=lambda r: _page(r, [self._question(q, locale(r)) for q in d["questions"]])
        )
        router.get(f"{BASE}/v1/delivery/mock-exams").respond(json={"items": []})
        router.get(f"{BASE}/v1/delivery/learning-journeys").mock(
            side_effect=lambda r: httpx.Response(
                200, json={"items": [self._journey(j, locale(r)) for j in d["journeys"]]}
            )
        )

        def grading(request: httpx.Request) -> httpx.Response:
            self.grading_calls += 1
            question = self.question(request.url.path.split("/")[-3])
            return httpx.Response(
                200,
                json={
                    "id": question["id"],
                    "version": question["version"],
                    "shared": {"correctOptionId": question["correctOptionId"]},
                    "translations": {
                        "sv-SE": {"explanation": "<p>Förklaring.</p>"},
                        "en-GB": {"explanation": "<p>Explanation.</p>"},
                    },
                },
            )

        router.get(url__regex=rf"{BASE}/v1/grading/questions/.+").mock(side_effect=grading)
