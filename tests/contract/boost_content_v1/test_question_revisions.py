"""§13.2 #5 and §13.4: delivery question revisions, single and batch (answer-free)."""

from collections.abc import Mapping
from typing import Any

import pytest

from tests.contract.boost_content_v1.assertions import (
    assert_answer_free,
    assert_immutable,
    assert_item,
    assert_problem,
)
from tests.contract.boost_content_v1.blocks import Context, validate_blocks
from tests.contract.boost_content_v1.support import (
    DEFAULT_LOCALE,
    MAX_BATCH_REFS,
    ContractClient,
    Discovery,
    describe,
    refs_param,
)

BATCH = "/v1/delivery/questions/revisions"
UNKNOWN_REF = ("999999999", "1")
QUESTION_TYPES = frozenset({"mcq", "truefalse"})


def _batch(client: ContractClient, refs: list[tuple[str, str]]) -> Any:
    return client.get_json(BATCH, {"refs": refs_param(refs), "locale": DEFAULT_LOCALE})


def _question_problems(question: Mapping[str, Any]) -> list[str]:
    shared = question.get("shared") or {}
    translation = question.get("translation") or {}
    qid = question.get("id")
    problems: list[str] = []
    if not (isinstance(shared.get("topicKey"), str) and shared["topicKey"]):
        problems.append(f"question {qid}: shared.topicKey is required")
    if shared.get("type") not in QUESTION_TYPES:
        problems.append(f"question {qid}: shared.type {shared.get('type')!r}")
    difficulty = shared.get("difficulty")
    if not (isinstance(difficulty, int) and 1 <= difficulty <= 5):
        problems.append(f"question {qid}: shared.difficulty {difficulty!r} is not 1-5")
    problems += validate_blocks(
        translation.get("prompt"), Context.PROMPT, path=f"question {qid} prompt"
    )
    options = translation.get("options")
    if not isinstance(options, list) or len(options) < 2:
        problems.append(f"question {qid}: needs at least two options")
        return problems
    option_ids = [o.get("id") if isinstance(o, Mapping) else None for o in options]
    if not all(isinstance(i, str) and i for i in option_ids):
        problems.append(f"question {qid}: every option needs an 'id'")
    if len(set(option_ids)) != len(option_ids):
        problems.append(f"question {qid}: option ids must be distinct: {option_ids}")
    for n, option in enumerate(options):
        blocks = option.get("blocks") if isinstance(option, Mapping) else None
        problems += validate_blocks(blocks, Context.OPTION, path=f"question {qid} options[{n}]")
    return problems


def test_batch_returns_the_requested_revisions(
    client: ContractClient, discovery: Discovery
) -> None:
    refs = discovery.question_refs

    body = _batch(client, refs)

    returned = {(str(q["id"]), str(q["version"])) for q in body["items"]}
    assert returned == set(refs)
    assert body["missing"] == []


def test_batch_items_have_the_new_fields(client: ContractClient, discovery: Discovery) -> None:
    items = _batch(client, discovery.question_refs)["items"]

    problems = [p for item in items for p in _question_problems(item)]

    assert not problems, "\n".join(problems)


def test_batch_items_are_delivery_items(client: ContractClient, discovery: Discovery) -> None:
    for item in _batch(client, discovery.question_refs)["items"]:
        assert_item(item, locale=DEFAULT_LOCALE)


def test_batch_never_carries_answers(client: ContractClient, discovery: Discovery) -> None:
    assert_answer_free(_batch(client, discovery.question_refs))


def test_batch_reports_unknown_refs_as_missing(
    client: ContractClient, discovery: Discovery
) -> None:
    known = discovery.question_refs[0]

    body = _batch(client, [known, UNKNOWN_REF])

    assert [(str(q["id"]), str(q["version"])) for q in body["items"]] == [known]
    assert body["missing"] == [f"{UNKNOWN_REF[0]}:{UNKNOWN_REF[1]}"]


def test_batch_over_the_limit_is_422(client: ContractClient) -> None:
    refs = [(str(1_000_000 + n), "1") for n in range(MAX_BATCH_REFS + 1)]

    response = client.get(BATCH, {"refs": refs_param(refs), "locale": DEFAULT_LOCALE})

    assert_problem(response, 422)


def test_batch_is_immutably_cacheable(client: ContractClient, discovery: Discovery) -> None:
    response = client.get(
        BATCH, {"refs": refs_param(discovery.question_refs[:1]), "locale": DEFAULT_LOCALE}
    )

    assert response.status_code == 200, describe(response)
    assert_immutable(response)


def test_single_revision_is_immutably_cacheable(
    client: ContractClient, discovery: Discovery
) -> None:
    question_id, version = discovery.question_refs[0]

    response = client.get(
        f"/v1/delivery/questions/{question_id}/revisions/{version}", {"locale": DEFAULT_LOCALE}
    )

    assert response.status_code == 200, describe(response)
    assert_immutable(response)


@pytest.mark.parametrize("locale", ["sv-SE", "en-GB"])
def test_batch_honours_locale(client: ContractClient, discovery: Discovery, locale: str) -> None:
    body = client.get_json(
        BATCH, {"refs": refs_param(discovery.question_refs[:1]), "locale": locale}
    )

    assert [q.get("locale") for q in body["items"]] == [locale]
