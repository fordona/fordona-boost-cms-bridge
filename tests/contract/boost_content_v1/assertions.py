"""Shape assertions shared by the contract tests (plan §13.1, §13.5)."""

import re
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

import httpx

from tests.contract.boost_content_v1.support import MAX_PAGE_SIZE, describe

DECIMAL_ID = re.compile(r"^[1-9][0-9]*$")
ANSWER_KEYS = frozenset({"correctOptionId", "correctOptionKey", "explanation"})


def is_decimal_id(value: Any) -> bool:
    return isinstance(value, str) and DECIMAL_ID.match(value) is not None


def is_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def assert_page(body: Any) -> list[Mapping[str, Any]]:
    """A Boost list page ``{ items, total, page, pageSize, asOf }``; returns its items."""
    assert isinstance(body, Mapping), f"list page must be an object, got {type(body).__name__}"
    missing = {"items", "total", "page", "pageSize", "asOf"} - set(body)
    assert not missing, f"list page is missing {sorted(missing)}"
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert body["total"] >= 0
    assert isinstance(body["page"], int)
    assert body["page"] >= 1
    assert isinstance(body["pageSize"], int)
    assert 1 <= body["pageSize"] <= MAX_PAGE_SIZE
    assert is_timestamp(body["asOf"]), f"asOf is not a timestamp: {body['asOf']!r}"
    return body["items"]


def assert_item(item: Any, *, locale: str | None = None) -> None:
    """A Boost delivery item ``{ id, version, locale, shared, translation, ... }``."""
    assert isinstance(item, Mapping), "item must be an object"
    assert is_decimal_id(item.get("id")), f"id must be a decimal string: {item.get('id')!r}"
    assert isinstance(item.get("version"), str), "version must be a string"
    assert item["version"], "version is required"
    assert isinstance(item.get("shared"), Mapping), "shared must be an object"
    if locale is not None:
        assert item.get("locale") == locale, f"locale {item.get('locale')!r} != {locale!r}"


def assert_problem(response: httpx.Response, status: int, code: str | None = None) -> None:
    """Boost's error envelope ``{ status, code, detail, requestId, errors }``."""
    assert response.status_code == status, describe(response)
    body = response.json()
    assert isinstance(body, Mapping), "error body must be an object"
    assert body.get("status") == status, f"error body status {body.get('status')!r} != {status}"
    assert isinstance(body.get("code"), str), "error body needs a string 'code'"
    assert body["code"], "error body needs a non-empty 'code'"
    if code is not None:
        assert body["code"] == code, f"error code {body['code']!r} != {code!r}"


def assert_immutable(response: httpx.Response) -> None:
    """Revision endpoints: ``Cache-Control: public, max-age=31536000, immutable`` + ETag."""
    cache_control = {
        part.strip().lower() for part in response.headers.get("Cache-Control", "").split(",")
    }
    expected = {"public", "max-age=31536000", "immutable"}
    assert expected <= cache_control, (
        f"Cache-Control {response.headers.get('Cache-Control')!r} must include {sorted(expected)}"
    )
    assert response.headers.get("ETag"), "revision responses need an ETag"


def walk_keys(value: Any) -> Iterator[str]:
    """Every object key anywhere in a JSON value."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def assert_answer_free(body: Any) -> None:
    leaked = ANSWER_KEYS & set(walk_keys(body))
    assert not leaked, f"delivery response carries answer fields {sorted(leaked)}"
