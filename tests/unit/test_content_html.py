"""The legacy-Boost-shape-to-block conversions used against real content (no block
format sent, confirmed 2026-11-06 against boost-api-dev.fordona.dev)."""

from boost_bridge.services.content_html import html_to_blocks, question_prompt_blocks


def test_plain_paragraph_becomes_one_text_block() -> None:
    blocks = html_to_blocks("<p>Give way to the right.</p>")
    assert len(blocks) == 1
    assert blocks[0].markdown == "Give way to the right."  # type: ignore[union-attr]


def test_heading_becomes_its_own_markdown_heading_block() -> None:
    """Confirmed 2026-11-06 via a live lesson (``/v1/lessons/1``): before this fix,
    every section heading ("What does the rule say?", "Who does it apply to?",
    "Exceptions", "Tip") vanished from the response with no trace — an unsupported
    tag's content, not just its styling, is dropped outright."""
    blocks = html_to_blocks("<h2>What does the rule say?</h2><p>Body text.</p>")
    assert [b.markdown for b in blocks] == ["## What does the rule say?", "Body text."]  # type: ignore[union-attr]


def test_unsupported_tag_and_its_content_are_dropped() -> None:
    blocks = html_to_blocks("<p>Keep this.</p><script>alert(1)</script><p>And this.</p>")
    assert [b.markdown for b in blocks] == ["Keep this.", "And this."]  # type: ignore[union-attr]


def test_empty_html_is_no_blocks() -> None:
    assert html_to_blocks(None) == []
    assert html_to_blocks("") == []
    assert html_to_blocks("   ") == []


def test_question_prompt_blocks_wraps_plain_text() -> None:
    blocks = question_prompt_blocks("Vad betyder skylten?", media_id=None)
    assert len(blocks) == 1
    assert blocks[0].markdown == "Vad betyder skylten?"  # type: ignore[union-attr]


def test_question_prompt_blocks_appends_image_when_media_id_present() -> None:
    blocks = question_prompt_blocks("Vad betyder skylten?", media_id="asset-1")
    assert len(blocks) == 2
    assert blocks[1].type == "image"  # type: ignore[union-attr]
    assert blocks[1].asset_id == "asset-1"  # type: ignore[union-attr]


def test_question_prompt_blocks_falls_back_to_placeholder_for_blank_text() -> None:
    blocks = question_prompt_blocks(None, media_id=None)
    assert blocks[0].markdown == "…"  # type: ignore[union-attr]
