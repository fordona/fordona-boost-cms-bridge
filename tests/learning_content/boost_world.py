"""A small fake Boost catalogue, served through respx, for content-sync tests."""

from dataclasses import dataclass, field
from typing import Any

import httpx
import respx

BASE = "https://boost.test"
LOCALES = ("sv-SE", "en-GB")


@dataclass
class FakeQuestion:
    id: str
    lesson_id: str
    module_id: str = "m1"
    version: str = "1"
    options: tuple[str, ...] = ("a", "b", "c")
    correct: str | None = "a"
    difficulty: int | None = 2
    subject_id: str | None = "traffic"
    locales: tuple[str, ...] = LOCALES


@dataclass
class FakeLesson:
    id: str
    module_id: str = "m1"
    version: str = "1"
    theory: bool = True


@dataclass
class BoostWorld:
    modules: list[str] = field(default_factory=lambda: ["m1"])
    lessons: list[FakeLesson] = field(default_factory=list)
    questions: list[FakeQuestion] = field(default_factory=list)
    mock_exams: list[dict[str, Any]] = field(default_factory=list)
    journeys: list[dict[str, Any]] = field(default_factory=list)
    grading_calls: list[str] = field(default_factory=list)

    def mount(self, router: respx.MockRouter) -> None:
        router.get(f"{BASE}/v1/delivery/modules").mock(side_effect=self._modules)
        router.get(f"{BASE}/v1/delivery/lessons").mock(side_effect=self._lessons)
        router.get(f"{BASE}/v1/delivery/questions").mock(side_effect=self._questions)
        router.get(f"{BASE}/v1/delivery/mock-exams").mock(side_effect=self._mock_exams)
        router.get(f"{BASE}/v1/delivery/learning-journeys").mock(side_effect=self._journeys)
        router.get(url__regex=rf"{BASE}/v1/grading/questions/.+").mock(side_effect=self._grading)

    # --- handlers -------------------------------------------------------

    def _modules(self, request: httpx.Request) -> httpx.Response:
        locale = request.url.params["locale"]
        items = [
            {"id": m, "version": "1", "translation": {"title": f"{m} {locale}"}}
            for m in self.modules
        ]
        return _page(request, items)

    def _lessons(self, request: httpx.Request) -> httpx.Response:
        locale = request.url.params["locale"]
        items = [
            {
                "id": lesson.id,
                "version": lesson.version,
                "shared": {"moduleId": lesson.module_id, "estimatedReadMinutes": 5},
                "translation": {
                    "title": f"{lesson.id} {locale}",
                    "contentHtml": "<p>theory</p>" if lesson.theory else "",
                },
            }
            for lesson in self.lessons
        ]
        return _page(request, items)

    def _questions(self, request: httpx.Request) -> httpx.Response:
        locale = request.url.params["locale"]
        items = [
            {
                "id": q.id,
                "version": q.version,
                "shared": {
                    "lessonId": q.lesson_id,
                    "moduleId": q.module_id,
                    "subjectId": q.subject_id,
                    "difficulty": q.difficulty,
                    "type": "mcq",
                },
                "translation": (
                    {
                        "questionText": f"{q.id}?",
                        "options": [{"id": key, "text": key} for key in q.options],
                    }
                    if locale in q.locales
                    else None
                ),
            }
            for q in self.questions
        ]
        return _page(request, items)

    def _mock_exams(self, request: httpx.Request) -> httpx.Response:
        locale = request.url.params["locale"]
        return httpx.Response(
            200,
            json={
                "items": [{**exam, "name": f"{exam['id']} {locale}"} for exam in self.mock_exams]
            },
        )

    def _journeys(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": self.journeys})

    def _grading(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer grading-token"
        _, _, _, question_id, _, version = request.url.path.strip("/").split("/")
        self.grading_calls.append(f"{question_id}@{version}")
        question = next(
            (q for q in self.questions if q.id == question_id and q.version == version), None
        )
        if question is None or question.correct is None:
            return httpx.Response(404, json={"status": 404, "code": "NOT_FOUND"})
        return httpx.Response(
            200,
            json={
                "id": question.id,
                "version": question.version,
                "shared": {"correctOptionId": question.correct},
                "translations": {
                    locale: {"explanation": f"why ({locale})"} for locale in question.locales
                },
            },
        )


def _page(request: httpx.Request, items: list[dict[str, Any]]) -> httpx.Response:
    page = int(request.url.params.get("page", 1))
    size = int(request.url.params.get("pageSize", 250))
    chunk = items[(page - 1) * size : page * size]
    return httpx.Response(
        200, json={"items": chunk, "total": len(items), "page": page, "pageSize": size}
    )
