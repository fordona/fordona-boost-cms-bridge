"""The §4.6 conversions the stub applies to today's Boost shapes."""

from boost_stub.transforms import (
    explanation_blocks,
    html_to_blocks,
    option_blocks,
    question_prompt_blocks,
    topic_vocabulary,
    transform_lesson_item,
    transform_question_item,
)

# --- html_to_blocks -------------------------------------------------------------


def test_plain_paragraph_becomes_one_text_block() -> None:
    assert html_to_blocks("<p>Give way to the right.</p>") == [
        {"type": "text", "markdown": "Give way to the right."}
    ]


def test_each_paragraph_is_its_own_block() -> None:
    blocks = html_to_blocks("<p>First.</p><p>Second.</p>")
    assert [b["markdown"] for b in blocks] == ["First.", "Second."]


def test_inline_emphasis_becomes_markdown() -> None:
    blocks = html_to_blocks("<p>Always <strong>stop</strong> and <em>look</em>.</p>")
    assert blocks == [{"type": "text", "markdown": "Always **stop** and *look*."}]


def test_link_becomes_markdown() -> None:
    blocks = html_to_blocks('<p>See <a href="https://example.test">the rules</a>.</p>')
    assert blocks == [{"type": "text", "markdown": "See [the rules](https://example.test)."}]


def test_list_becomes_markdown_list() -> None:
    blocks = html_to_blocks("<ul><li>First point</li><li>Second point</li></ul>")
    assert blocks == [{"type": "text", "markdown": "- First point\n- Second point"}]


def test_ordered_list_is_numbered() -> None:
    blocks = html_to_blocks("<ol><li>One</li><li>Two</li></ol>")
    assert blocks == [{"type": "text", "markdown": "1. One\n2. Two"}]


def test_unsupported_tag_and_its_content_are_dropped() -> None:
    blocks = html_to_blocks("<p>Keep this.</p><script>alert(1)</script><p>And this.</p>")
    assert [b["markdown"] for b in blocks] == ["Keep this.", "And this."]


def test_empty_html_is_no_blocks() -> None:
    assert html_to_blocks(None) == []
    assert html_to_blocks("") == []
    assert html_to_blocks("   ") == []


def test_whitespace_only_paragraph_is_dropped() -> None:
    assert html_to_blocks("<p>Real.</p><p>   </p>") == [{"type": "text", "markdown": "Real."}]


def test_br_becomes_a_line_break_within_one_block() -> None:
    blocks = html_to_blocks("<p>Line one<br/>Line two</p>")
    assert blocks == [{"type": "text", "markdown": "Line one\nLine two"}]


# --- question_prompt_blocks / option_blocks --------------------------------------


def test_prompt_starts_with_text_even_when_question_text_is_empty() -> None:
    blocks = question_prompt_blocks(None, media_id=None)
    assert blocks[0]["type"] == "text"


def test_prompt_adds_an_image_block_for_media() -> None:
    blocks = question_prompt_blocks("What does this sign mean?", media_id="a77")
    assert blocks == [
        {"type": "text", "markdown": "What does this sign mean?"},
        {"type": "image", "assetId": "a77", "alt": "What does this sign mean?"},
    ]


def test_prompt_has_no_image_block_without_media() -> None:
    blocks = question_prompt_blocks("Text only.", media_id=None)
    assert len(blocks) == 1


def test_option_blocks_is_one_text_block() -> None:
    assert option_blocks("Vehicles from the right.") == [
        {"type": "text", "markdown": "Vehicles from the right."}
    ]


def test_explanation_blocks_falls_back_to_plain_text_when_html_has_no_blocks() -> None:
    # e.g. explanation text with no supported tags at all, just bare text.
    assert explanation_blocks("Bare explanation text.", source="t") == [
        {"type": "text", "markdown": "Bare explanation text."}
    ]


def test_explanation_blocks_uses_html_paragraphs_when_present() -> None:
    blocks = explanation_blocks("<p>First.</p><p>Second.</p>", source="t")
    assert [b["markdown"] for b in blocks] == ["First.", "Second."]


# --- transform_lesson_item / transform_question_item -----------------------------


def test_transform_lesson_item_adds_blocks_and_keeps_other_fields() -> None:
    item = {
        "id": "10",
        "version": "1",
        "locale": "sv-SE",
        "translation": {"title": "A lesson", "contentHtml": "<p>Theory.</p>"},
    }

    transformed = transform_lesson_item(item)

    assert transformed["id"] == "10"
    assert transformed["translation"]["title"] == "A lesson"
    assert transformed["translation"]["blocks"] == [{"type": "text", "markdown": "Theory."}]
    assert transformed is not item  # the original item is never mutated


def test_transform_question_item_injects_topic_key_from_lesson() -> None:
    item = {
        "id": "100",
        "shared": {"lessonId": "10"},
        "translation": {"questionText": "Q?", "options": [{"id": "a", "text": "A"}]},
    }

    transformed = transform_question_item(item)

    assert transformed["shared"]["topicKey"] == "lesson-10"


def test_transform_question_item_keeps_an_existing_topic_key() -> None:
    item = {
        "id": "100",
        "shared": {"lessonId": "10", "topicKey": "right-of-way.right-hand-rule"},
        "translation": {"questionText": "Q?", "options": []},
    }

    transformed = transform_question_item(item)

    assert transformed["shared"]["topicKey"] == "right-of-way.right-hand-rule"


def test_transform_question_item_adds_prompt_and_option_blocks() -> None:
    item = {
        "id": "100",
        "shared": {"lessonId": "10", "mediaId": "m1"},
        "translation": {
            "questionText": "What applies?",
            "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        },
    }

    transformed = transform_question_item(item)

    assert transformed["translation"]["prompt"][0] == {"type": "text", "markdown": "What applies?"}
    assert transformed["translation"]["prompt"][1]["assetId"] == "m1"
    options = transformed["translation"]["options"]
    assert [o["id"] for o in options] == ["a", "b"]
    assert all("blocks" in o and "text" in o for o in options)
    # legacy fields are kept, not replaced (§13.4: "stay for existing consumers")
    assert options[0]["text"] == "A"


def test_transform_question_item_does_not_mutate_the_original() -> None:
    item = {"id": "100", "shared": {"lessonId": "10"}, "translation": {"options": []}}
    transform_question_item(item)
    assert "topicKey" not in item["shared"]
    assert "prompt" not in item["translation"]


# --- topic_vocabulary -------------------------------------------------------------


def test_topic_vocabulary_one_per_lesson_sorted_numerically() -> None:
    topics = topic_vocabulary("1", ["21", "3", "10"])

    assert [t["key"] for t in topics] == ["lesson-3", "lesson-10", "lesson-21"]
    assert all(t["moduleId"] == "1" for t in topics)
    assert all({"sv-SE", "en-GB"} <= set(t["title"]) for t in topics)


def test_topic_vocabulary_deduplicates_lessons() -> None:
    topics = topic_vocabulary("1", ["10", "10", "10"])
    assert len(topics) == 1
