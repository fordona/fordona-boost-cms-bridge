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

# The "supported HTML subset" (plan §4.5): block-level containers, inline emphasis,
# lists and links. Everything else — script, style, table, iframe, raw attributes — is
# dropped, including its content, and logged.
_BLOCK_TAGS = frozenset({"p", "div", "br"})
_LIST_TAGS = frozenset({"ul", "ol"})
_INLINE_MARKUP = {"strong": "**", "b": "**", "em": "*", "i": "*"}
_SUPPORTED_TAGS = _BLOCK_TAGS | _LIST_TAGS | {"li", "a", *_INLINE_MARKUP}

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
        if tag in _BLOCK_TAGS:
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


def text_block(text: str | None) -> list[ContentBlock]:
    """A single plain-text block, for fields that are never HTML (question prompts,
    option text) — mirrors the stub's ``question_prompt_blocks``/``option_blocks``.
    """
    markdown = (text or "").strip() or "…"
    return _BLOCKS_ADAPTER.validate_python([{"type": "text", "markdown": markdown}])
