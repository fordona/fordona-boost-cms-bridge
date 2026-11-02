"""Shared pieces of the contract suite: configuration, client, data discovery.

See ``conftest.py`` for the environment variables and the "fails cleanly" rule.
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import httpx
import pytest

DEFAULT_LOCALE = "sv-SE"
MAX_BATCH_REFS = 100
MAX_PAGE_SIZE = 250


@dataclass(frozen=True)
class ContractConfig:
    base_url: str
    delivery_token: str
    grading_token: str
    expired_cursor: str | None
    locales: tuple[str, ...]


def load_config() -> ContractConfig | None:
    base_url = os.environ.get("CONTRACT_BOOST_BASE_URL", "").strip()
    if not base_url:
        return None
    missing = [
        name
        for name in ("CONTRACT_DELIVERY_TOKEN", "CONTRACT_GRADING_TOKEN")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise pytest.UsageError(
            f"CONTRACT_BOOST_BASE_URL is set but {', '.join(missing)} is not: "
            "the contract suite needs both tokens"
        )
    locales = tuple(
        loc.strip()
        for loc in os.environ.get("CONTRACT_LOCALES", "sv-SE,en-GB").split(",")
        if loc.strip()
    )
    return ContractConfig(
        base_url=base_url.rstrip("/"),
        delivery_token=os.environ["CONTRACT_DELIVERY_TOKEN"].strip(),
        grading_token=os.environ["CONTRACT_GRADING_TOKEN"].strip(),
        expired_cursor=os.environ.get("CONTRACT_EXPIRED_CURSOR", "").strip() or None,
        locales=locales,
    )


class ContractClient:
    """A thin HTTP client whose failures are test failures, not errors."""

    def __init__(self, http: httpx.Client, config: ContractConfig) -> None:
        self._http = http
        self.config = config

    def get(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        all_headers = {"Authorization": f"Bearer {token or self.config.delivery_token}"}
        all_headers.update(headers or {})
        try:
            return self._http.get(path, params=params, headers=all_headers)
        except httpx.HTTPError as exc:
            pytest.fail(f"GET {path} failed at transport level: {exc!r}", pytrace=False)

    def get_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        token: str | None = None,
        expect: int = 200,
    ) -> Any:
        response = self.get(path, params, token=token)
        assert response.status_code == expect, describe(response)
        try:
            return response.json()
        except ValueError:
            pytest.fail(f"{describe(response)}: body is not JSON", pytrace=False)

    def grading(self, path: str, params: Mapping[str, str | int] | None = None) -> httpx.Response:
        return self.get(path, params, token=self.config.grading_token)


def describe(response: httpx.Response) -> str:
    body = response.text[:300].replace("\n", " ")
    return f"{response.request.method} {response.request.url} -> {response.status_code}: {body}"


def refs_param(refs: Sequence[tuple[str, str]]) -> str:
    return ",".join(f"{qid}:{version}" for qid, version in refs)


class Discovery:
    """Finds real published content to test against, lazily and at most once.

    Starts from the first published template, because a template ties the other
    entities together: its lesson, its module, and its questions. Failures raise
    ``AssertionError`` inside the calling test (results are cached only on
    success).
    """

    def __init__(self, client: ContractClient) -> None:
        self._client = client

    @cached_property
    def template(self) -> Mapping[str, Any]:
        page = self._client.get_json(
            "/v1/delivery/question-templates",
            {"page": 1, "pageSize": MAX_PAGE_SIZE, "locale": DEFAULT_LOCALE},
        )
        items = page.get("items") if isinstance(page, Mapping) else None
        assert isinstance(items, list), "template list has no items array"
        assert items, "precondition: no published template found"
        template: Mapping[str, Any] = items[0]
        return template

    @cached_property
    def template_revision(self) -> Mapping[str, Any]:
        template = self.template
        revision: Mapping[str, Any] = self._client.get_json(
            f"/v1/delivery/question-templates/{template['id']}/revisions/{template['version']}",
            {"locale": DEFAULT_LOCALE},
        )
        return revision

    @cached_property
    def module_id(self) -> str:
        return str(self.template_revision["shared"]["moduleId"])

    @cached_property
    def lesson_id(self) -> str:
        return str(self.template_revision["shared"]["lessonId"])

    @cached_property
    def questions(self) -> list[Mapping[str, Any]]:
        """The template's questions as delivered now (current published revisions)."""
        ids = [str(q["questionId"]) for q in self.template_revision["shared"]["questions"]]
        page = self._client.get_json(
            "/v1/delivery/questions",
            {
                "id": ",".join(ids[:MAX_BATCH_REFS]),
                "pageSize": MAX_BATCH_REFS,
                "locale": DEFAULT_LOCALE,
            },
        )
        items: list[Mapping[str, Any]] = page["items"]
        assert items, "precondition: the template's questions are not delivered"
        return items

    @cached_property
    def question_refs(self) -> list[tuple[str, str]]:
        return [(str(q["id"]), str(q["version"])) for q in self.questions]

    @cached_property
    def lesson(self) -> Mapping[str, Any]:
        page = self._client.get_json(
            "/v1/delivery/lessons", {"id": self.lesson_id, "locale": DEFAULT_LOCALE}
        )
        items = page["items"]
        assert items, f"precondition: lesson {self.lesson_id} is not delivered"
        lesson: Mapping[str, Any] = items[0]
        return lesson
