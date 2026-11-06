"""§13.2 #7 and §13.4: a module's topic vocabulary."""

from collections.abc import Mapping
from typing import Any

from tests.contract.boost_content_v1.support import ContractClient, Discovery

TOPICS = "/v1/delivery/topics"


def _topics(client: ContractClient, module_id: str) -> list[Mapping[str, Any]]:
    body = client.get_json(TOPICS, {"moduleId": module_id})
    assert isinstance(body, Mapping), "topics response must be an object"
    assert isinstance(body.get("items"), list), "topics response needs an 'items' array"
    items: list[Mapping[str, Any]] = body["items"]
    return items


def test_topic_shape(client: ContractClient, discovery: Discovery) -> None:
    topics = _topics(client, discovery.module_id)

    assert topics, "precondition: the module has no topics"
    for topic in topics:
        assert isinstance(topic.get("key"), str), f"key must be a string: {topic!r}"
        assert topic["key"], f"key must be non-empty: {topic!r}"
        assert str(topic.get("moduleId")) == discovery.module_id, f"moduleId: {topic!r}"
        title = topic.get("title")
        assert isinstance(title, Mapping), f"title must be a locale map: {topic!r}"
        for locale in client.config.locales:
            assert title.get(locale), f"topic {topic['key']!r} has no {locale} title"


def test_topic_keys_are_unique(client: ContractClient, discovery: Discovery) -> None:
    keys = [t["key"] for t in _topics(client, discovery.module_id)]

    assert len(set(keys)) == len(keys), f"duplicate topic keys: {keys}"


def test_every_question_topic_is_in_the_vocabulary(
    client: ContractClient, discovery: Discovery
) -> None:
    vocabulary = {t["key"] for t in _topics(client, discovery.module_id)}
    used = {str(q["shared"].get("topicKey")) for q in discovery.questions}

    assert used <= vocabulary, (
        f"topicKeys not in the module vocabulary: {sorted(used - vocabulary)}"
    )
