"""§13.2 #4 and §13.4: the immutable lesson revision that holds the theory."""

from typing import Any

from tests.contract.boost_content_v1.assertions import assert_immutable, assert_item
from tests.contract.boost_content_v1.blocks import Context, validate_blocks
from tests.contract.boost_content_v1.support import (
    DEFAULT_LOCALE,
    ContractClient,
    Discovery,
    describe,
)


def _revision_path(discovery: Discovery) -> str:
    lesson = discovery.lesson
    return f"/v1/delivery/lessons/{lesson['id']}/revisions/{lesson['version']}"


def _revision(client: ContractClient, discovery: Discovery) -> Any:
    return client.get_json(_revision_path(discovery), {"locale": DEFAULT_LOCALE})


def test_lesson_revision_shape(client: ContractClient, discovery: Discovery) -> None:
    revision = _revision(client, discovery)

    assert_item(revision, locale=DEFAULT_LOCALE)
    assert str(revision["id"]) == str(discovery.lesson["id"])
    assert str(revision["version"]) == str(discovery.lesson["version"])
    minutes = revision["shared"].get("estimatedReadMinutes")
    assert minutes is None or (isinstance(minutes, int) and minutes >= 0), (
        f"estimatedReadMinutes: {minutes!r}"
    )


def test_lesson_theory_is_valid_blocks(client: ContractClient, discovery: Discovery) -> None:
    translation = _revision(client, discovery).get("translation") or {}

    problems = validate_blocks(translation.get("blocks"), Context.THEORY, path="translation.blocks")

    assert not problems, "\n".join(problems)


def test_lesson_revision_is_immutably_cacheable(
    client: ContractClient, discovery: Discovery
) -> None:
    response = client.get(_revision_path(discovery), {"locale": DEFAULT_LOCALE})

    assert response.status_code == 200, describe(response)
    assert_immutable(response)


def test_unknown_lesson_revision_is_404(client: ContractClient, discovery: Discovery) -> None:
    response = client.get(
        f"/v1/delivery/lessons/{discovery.lesson['id']}/revisions/999999999",
        {"locale": DEFAULT_LOCALE},
    )

    assert response.status_code == 404, describe(response)
