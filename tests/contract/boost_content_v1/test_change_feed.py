"""§13.2 #1 and §13.3: the cursor-based change feed.

Not checkable from outside, and therefore not tested here: commit-order safety
(no ``seq`` exposed while a lower one may still commit), at-least-once delivery
and 30-day retention. They are Boost implementation requirements.
"""

from typing import Any

import pytest

from tests.contract.boost_content_v1.assertions import (
    assert_problem,
    is_decimal_id,
    is_timestamp,
)
from tests.contract.boost_content_v1.support import ContractClient, describe

FEED = "/v1/delivery/changes"
ENTITY_TYPES = frozenset({"MODULE", "LESSON", "QUESTION_TEMPLATE", "QUESTION", "TOPIC"})
CHANGES = frozenset({"PUBLISHED", "UNPUBLISHED"})
MAX_PAGES_TO_WALK = 50


def _page(client: ContractClient, after: str, limit: int) -> dict[str, Any]:
    body: dict[str, Any] = client.get_json(FEED, {"after": after, "limit": limit})
    return body


def test_feed_page_shape(client: ContractClient) -> None:
    body = _page(client, "0", 50)

    assert set(body) >= {"items", "nextCursor", "hasMore"}, f"feed page keys: {sorted(body)}"
    assert isinstance(body["items"], list)
    assert isinstance(body["hasMore"], bool)
    assert isinstance(body["nextCursor"], str)


def test_feed_items_shape(client: ContractClient) -> None:
    items = _page(client, "0", 50)["items"]
    assert items, "precondition: the feed is empty from the start"

    for item in items:
        assert is_decimal_id(item.get("seq")), f"seq must be a decimal string: {item!r}"
        assert item.get("entityType") in ENTITY_TYPES, f"entityType: {item!r}"
        assert item.get("change") in CHANGES, f"change: {item!r}"
        assert isinstance(item.get("id"), str), f"id must be a string: {item!r}"
        assert item["id"], f"id must be non-empty: {item!r}"
        assert isinstance(item.get("version"), str), f"version must be a string: {item!r}"
        assert is_timestamp(item.get("publishedAt")), f"publishedAt: {item!r}"


def test_limit_is_respected(client: ContractClient) -> None:
    assert len(_page(client, "0", 1)["items"]) <= 1


def test_seq_strictly_increasing_across_pages(client: ContractClient) -> None:
    cursor, last_seq = "0", 0
    for _ in range(5):
        body = _page(client, cursor, 200)
        for item in body["items"]:
            seq = int(item["seq"])
            assert seq > last_seq, f"seq {seq} after {last_seq} is not strictly increasing"
            last_seq = seq
        if body["items"]:
            assert body["nextCursor"] == body["items"][-1]["seq"], (
                "nextCursor must be the last item's seq"
            )
        if not body["hasMore"]:
            break
        cursor = body["nextCursor"]


def test_reading_past_the_head_returns_an_empty_page(client: ContractClient) -> None:
    cursor = "0"
    for _ in range(MAX_PAGES_TO_WALK):
        body = _page(client, cursor, 1000)
        if not body["hasMore"]:
            break
        cursor = body["nextCursor"]
    else:
        pytest.skip(f"the feed is longer than {MAX_PAGES_TO_WALK} pages of 1000")

    head = _page(client, body["nextCursor"], 1000)

    assert head["items"] == [], "a poll at the head must return no items"
    assert head["hasMore"] is False


def test_expired_cursor_is_410(client: ContractClient) -> None:
    cursor = client.config.expired_cursor
    assert cursor, (
        "set CONTRACT_EXPIRED_CURSOR to a cursor the server must reject as expired "
        "(older than its retention); a black-box test cannot age one"
    )

    response = client.get(FEED, {"after": cursor})

    assert_problem(response, 410, "CURSOR_EXPIRED")


def test_delivery_token_is_required(client: ContractClient) -> None:
    response = client.get(FEED, {"after": "0"}, token="not-a-valid-token")

    assert response.status_code in (401, 403), describe(response)
