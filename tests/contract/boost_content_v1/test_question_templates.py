"""§13.2 #2, #3 and §13.4: question templates (list and immutable revision)."""

from tests.contract.boost_content_v1.assertions import (
    assert_immutable,
    assert_item,
    assert_page,
    is_decimal_id,
)
from tests.contract.boost_content_v1.support import (
    DEFAULT_LOCALE,
    ContractClient,
    Discovery,
    describe,
)

TEMPLATES = "/v1/delivery/question-templates"
MIN_QUESTIONS = 3


def test_template_list_is_a_page_of_items(client: ContractClient) -> None:
    body = client.get_json(TEMPLATES, {"page": 1, "pageSize": 20, "locale": DEFAULT_LOCALE})

    items = assert_page(body)

    assert items, "precondition: no published template"
    for item in items:
        assert_item(item, locale=DEFAULT_LOCALE)


def test_template_list_filters_by_lesson(client: ContractClient, discovery: Discovery) -> None:
    body = client.get_json(TEMPLATES, {"lessonId": discovery.lesson_id, "locale": DEFAULT_LOCALE})

    items = assert_page(body)

    assert items, "the discovered template's own lesson returned no templates"
    assert {str(i["shared"]["lessonId"]) for i in items} == {discovery.lesson_id}


def test_template_list_filters_by_module(client: ContractClient, discovery: Discovery) -> None:
    body = client.get_json(TEMPLATES, {"moduleId": discovery.module_id, "locale": DEFAULT_LOCALE})

    items = assert_page(body)

    assert items, "the discovered template's own module returned no templates"
    assert {str(i["shared"]["moduleId"]) for i in items} == {discovery.module_id}


def test_template_list_filters_by_id(client: ContractClient, discovery: Discovery) -> None:
    template_id = str(discovery.template["id"])

    items = assert_page(client.get_json(TEMPLATES, {"id": template_id, "locale": DEFAULT_LOCALE}))

    assert [str(i["id"]) for i in items] == [template_id]


def test_template_revision_shape(discovery: Discovery) -> None:
    revision = discovery.template_revision
    shared = revision["shared"]

    assert_item(revision, locale=DEFAULT_LOCALE)
    assert str(revision["id"]) == str(discovery.template["id"])
    assert str(revision["version"]) == str(discovery.template["version"])
    assert is_decimal_id(shared.get("lessonId")), f"lessonId: {shared.get('lessonId')!r}"
    assert is_decimal_id(shared.get("moduleId")), f"moduleId: {shared.get('moduleId')!r}"
    assert isinstance(shared.get("sort"), int), "sort must be an integer"
    assert isinstance(revision.get("translation", {}).get("title"), str), "title is required"


def test_template_questions_are_sorted_and_distinct(discovery: Discovery) -> None:
    questions = discovery.template_revision["shared"]["questions"]
    sorts = [q["sort"] for q in questions]
    ids = [str(q["questionId"]) for q in questions]

    assert sorts == sorted(sorts), f"shared.questions must be in sort order: {sorts}"
    assert len(set(sorts)) == len(sorts), f"sort values must be distinct: {sorts}"
    assert len(set(ids)) == len(ids), f"a template lists a question once: {ids}"
    assert all(is_decimal_id(i) for i in ids), f"questionIds: {ids}"


def test_template_has_at_least_three_questions(discovery: Discovery) -> None:
    questions = discovery.template_revision["shared"]["questions"]

    assert len(questions) >= MIN_QUESTIONS, f"a template needs >= 3 questions, has {len(questions)}"


def test_template_questions_are_all_published(discovery: Discovery) -> None:
    referenced = {str(q["questionId"]) for q in discovery.template_revision["shared"]["questions"]}
    delivered = {str(q["id"]) for q in discovery.questions}

    assert referenced <= delivered, f"unpublished questions referenced: {referenced - delivered}"


def test_template_questions_share_its_module(discovery: Discovery) -> None:
    modules = {str(q["shared"]["moduleId"]) for q in discovery.questions}

    assert modules == {discovery.module_id}, f"questions span modules {modules}"


def test_template_revision_is_immutably_cacheable(
    client: ContractClient, discovery: Discovery
) -> None:
    template = discovery.template
    response = client.get(
        f"{TEMPLATES}/{template['id']}/revisions/{template['version']}",
        {"locale": DEFAULT_LOCALE},
    )

    assert response.status_code == 200, describe(response)
    assert_immutable(response)


def test_unknown_template_revision_is_404(client: ContractClient, discovery: Discovery) -> None:
    response = client.get(
        f"{TEMPLATES}/{discovery.template['id']}/revisions/999999999", {"locale": DEFAULT_LOCALE}
    )

    assert response.status_code == 404, describe(response)
