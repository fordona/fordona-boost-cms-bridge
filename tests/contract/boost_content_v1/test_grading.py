"""§13.2 #6 and §13.4: grading revisions (batch, all locales) and token scopes."""

from typing import Any

from tests.contract.boost_content_v1.assertions import assert_problem
from tests.contract.boost_content_v1.blocks import Context, validate_locale_blocks
from tests.contract.boost_content_v1.support import (
    MAX_BATCH_REFS,
    ContractClient,
    Discovery,
    describe,
    refs_param,
)

GRADING = "/v1/grading/questions/revisions"
UNKNOWN_REF = ("999999999", "1")


def _grading(client: ContractClient, refs: list[tuple[str, str]]) -> Any:
    response = client.grading(GRADING, {"refs": refs_param(refs)})
    assert response.status_code == 200, describe(response)
    return response.json()


def test_grading_batch_returns_the_requested_revisions(
    client: ContractClient, discovery: Discovery
) -> None:
    refs = discovery.question_refs

    body = _grading(client, refs)

    assert {(str(g["id"]), str(g["version"])) for g in body["items"]} == set(refs)
    assert body["missing"] == []


def test_correct_option_is_one_of_the_delivered_options(
    client: ContractClient, discovery: Discovery
) -> None:
    options_by_ref = {
        (str(q["id"]), str(q["version"])): {o["id"] for o in q["translation"]["options"]}
        for q in discovery.questions
    }

    for item in _grading(client, discovery.question_refs)["items"]:
        ref = (str(item["id"]), str(item["version"]))
        correct_option_id = item.get("shared", {}).get("correctOptionId")
        assert correct_option_id in options_by_ref[ref], (
            f"question {ref}: correctOptionId {correct_option_id!r} "
            f"is not among {sorted(options_by_ref[ref])}"
        )


def test_explanations_are_valid_blocks_in_every_locale(
    client: ContractClient, discovery: Discovery
) -> None:
    problems = [
        problem
        for item in _grading(client, discovery.question_refs)["items"]
        for problem in validate_locale_blocks(
            {locale: t.get("explanation") for locale, t in item.get("translations", {}).items()},
            client.config.locales,
            Context.EXPLANATION,
            path=f"question {item.get('id')} explanation",
        )
    ]

    assert not problems, "\n".join(problems)


def test_grading_batch_reports_unknown_refs_as_missing(
    client: ContractClient, discovery: Discovery
) -> None:
    known = discovery.question_refs[0]

    body = _grading(client, [known, UNKNOWN_REF])

    assert [(str(g["id"]), str(g["version"])) for g in body["items"]] == [known]
    assert body["missing"] == [f"{UNKNOWN_REF[0]}:{UNKNOWN_REF[1]}"]


def test_grading_batch_over_the_limit_is_422(client: ContractClient) -> None:
    refs = [(str(1_000_000 + n), "1") for n in range(MAX_BATCH_REFS + 1)]

    response = client.grading(GRADING, {"refs": refs_param(refs)})

    assert_problem(response, 422)


def test_delivery_token_cannot_read_grading(client: ContractClient) -> None:
    # Independent of discovery: the scope check must hold whatever the ref.
    response = client.get(GRADING, {"refs": refs_param([UNKNOWN_REF])})

    assert response.status_code in (401, 403), describe(response)
