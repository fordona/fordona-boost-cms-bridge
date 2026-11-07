"""Converts today's real Boost shapes (``contentHtml``, plain-text prompts/options/
explanations) into the §13 block format, for content the BFF reads directly from Boost
or forwards from the engine.

Ported from ``boost_stub.transforms`` (the stub's own reference implementation of this
exact conversion, written against the same plan sections) because real Boost — unlike
the stub — never sends block-format content: confirmed 2026-11-06 against a live
boost-api-dev.fordona.dev response, every lesson/question/explanation comes back with
only the legacy flat fields (``contentHtml``, ``questionText``, ``options[].text``, a
plain-string/HTML ``explanation``), never ``blocks``/``prompt``/``options[].blocks``.
Without this conversion, lesson theory, question prompts and "Check Answer" feedback
all render empty (or, for explanation, crash — see ``parse_explanation_blocks`` in
``theory_mappers.py``) against real content.

Unlike the stub (which produces raw dicts consumed only by its own JSON responses),
this module produces typed ``ContentBlock`` Pydantic instances, since every BFF
pipeline (``render_blocks``) expects those, not dicts.
"""

from html.parser import HTMLParser
from typing import Any

from pydantic import TypeAdapter

from boost_bridge.clients.boost.models import ContentBlock
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

# The "supported HTML subset" (plan §4.5): block-level containers, headings, inline
# emphasis, lists and links. Everything else — script, style, table, iframe, raw
# attributes — is dropped, including its content, and logged.
#
# Headings were missing from the original (stub-ported) subset entirely, which didn't
# just lose their styling — ``handle_starttag`` drops an unsupported tag's content
# outright, so every section heading in real Boost lesson content (confirmed
# 2026-11-06 live: "What does the rule say?", "Who does it apply to?", "Exceptions",
# "Tip") vanished from the response with no trace, not merely unstyled text.
_BLOCK_TAGS = frozenset({"p", "div", "br"})
_LIST_TAGS = frozenset({"ul", "ol"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_INLINE_MARKUP = {"strong": "**", "b": "**", "em": "*", "i": "*"}
_SUPPORTED_TAGS = _BLOCK_TAGS | _LIST_TAGS | _HEADING_TAGS | {"li", "a", *_INLINE_MARKUP}

_BLOCKS_ADAPTER: TypeAdapter[list[ContentBlock]] = TypeAdapter(list[ContentBlock])


class _BlockHtmlParser(HTMLParser):
    """Walks the supported subset; emits one markdown string per top-level block.

    Drops an unsupported tag **and its content** (anything inside it was never vetted
    for the subset the app renders), and logs each one once.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.dropped: list[str] = []
        self._current = ""
        self._list_depth = 0
        self._list_kinds: list[str] = []
        self._list_item_index: list[int] = []
        self._skip_depth = 0
        self._href_stack: list[str] = []

    def _flush(self) -> None:
        text = self._current.strip()
        if text:
            self.paragraphs.append(text)
        self._current = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            self._skip_depth += 1
            return
        if tag not in _SUPPORTED_TAGS:
            self.dropped.append(tag)
            self._skip_depth = 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()
        elif tag in _HEADING_TAGS:
            self._flush()
            self._current = "#" * int(tag[1]) + " "
        elif tag in _LIST_TAGS:
            self._flush()
            self._list_depth += 1
            self._list_kinds.append(tag)
            self._list_item_index.append(0)
        elif tag == "li":
            self._list_item_index[-1] += 1
            bullet = "-" if self._list_kinds[-1] == "ul" else f"{self._list_item_index[-1]}."
            if self._current.strip():
                self._current += "\n"
            self._current += f"{bullet} "
        elif tag in _INLINE_MARKUP:
            self._current += _INLINE_MARKUP[tag]
        elif tag == "a":
            href = next((v for k, v in attrs if k == "href" and v), "")
            self._href_stack.append(href)
            self._current += "["

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag not in _SUPPORTED_TAGS:
            return
        if tag in _BLOCK_TAGS or tag in _HEADING_TAGS:
            self._flush()
        elif tag in _LIST_TAGS:
            self._flush()
            self._list_depth -= 1
            self._list_kinds.pop()
            self._list_item_index.pop()
        elif tag == "li":
            pass  # the whole list is one block, flushed when the list itself ends
        elif tag in _INLINE_MARKUP:
            self._current += _INLINE_MARKUP[tag]
        elif tag == "a":
            href = self._href_stack.pop() if self._href_stack else ""
            self._current += f"]({href})"

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._current += data

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._skip_depth and tag == "br":
            self._current += "\n"


def _html_to_block_dicts(content_html: str | None, *, source: str = "") -> list[dict[str, Any]]:
    if not content_html or not content_html.strip():
        return []
    parser = _BlockHtmlParser()
    parser.feed(content_html)
    parser.close()
    parser._flush()
    if parser.dropped:
        log.warning("html_tags_dropped", source=source, tags=sorted(set(parser.dropped)))
    return [{"type": "text", "markdown": paragraph} for paragraph in parser.paragraphs]


def html_to_blocks(content_html: str | None, *, source: str = "") -> list[ContentBlock]:
    """Theory/explanation HTML → typed ``text`` blocks (plan §4.6's one-format rule)."""
    return _BLOCKS_ADAPTER.validate_python(_html_to_block_dicts(content_html, source=source))


def question_prompt_blocks(
    question_text: str | None, *, media_id: str | None
) -> list[ContentBlock]:
    """A legacy question's prompt: a text block plus an optional image, mirroring the
    stub's ``question_prompt_blocks``. ``shared.mediaId`` was never wired into any BFF
    pipeline before this fix — real sign-recognition questions ("what does this sign
    mean?") silently lost their image.
    """
    stripped = (question_text or "").strip()
    dicts: list[dict[str, Any]] = [{"type": "text", "markdown": stripped or "…"}]
    if media_id:
        dicts.append({"type": "image", "assetId": media_id, "alt": stripped or "Question media"})
    return _BLOCKS_ADAPTER.validate_python(dicts)
