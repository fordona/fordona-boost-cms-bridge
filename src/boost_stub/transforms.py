"""Converts today's Boost shapes into the §13 block format (plan §4.6, §13.4).

Two sources feed these functions: today's Boost (``contentHtml``, ``questionText``,
plain-text option/explanation strings) and the stub's own generated data
(``stub-data/synthetic.json``, already in block form — see ``synthetic.py`` in
``scripts/stub_data``). Only the first kind needs converting; the second is
passed through.
"""

from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any

from boost_stub.logging import get_logger

log = get_logger(__name__)

# The "supported HTML subset" (plan §4.5): block-level containers, headings, inline
# emphasis, lists and links. Everything else — script, style, table, iframe,
# raw attributes — is dropped, including its content, and logged.
#
# Headings were missing here entirely until 2026-11-06, which didn't just lose their
# styling — ``handle_starttag`` drops an unsupported tag's content outright, so every
# section heading in real Boost lesson content vanished with no trace. Found via
# ``boost_bridge.services.content_html`` (this module's BFF-side port, which carries
# the same fix) and ported back here to keep the two in sync.
_BLOCK_TAGS = frozenset({"p", "div", "br"})
_LIST_TAGS = frozenset({"ul", "ol"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_INLINE_MARKUP = {"strong": "**", "b": "**", "em": "*", "i": "*"}
_SUPPORTED_TAGS = _BLOCK_TAGS | _LIST_TAGS | _HEADING_TAGS | {"li", "a", *_INLINE_MARKUP}


class _BlockHtmlParser(HTMLParser):
    """Walks the supported subset; emits one markdown string per top-level block.

    Drops an unsupported tag **and its content** (anything inside it was never
    vetted for the subset the app renders), and logs each one once.
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


def html_to_blocks(content_html: str | None, *, source: str = "") -> list[dict[str, Any]]:
    """Theory/explanation HTML → ``text`` blocks (plan §4.6's one-format rule).

    Plain paragraphs separate into their own blocks; everything unsupported is
    dropped (tag and content) and logged with ``source`` for traceability.
    """
    if not content_html or not content_html.strip():
        return []
    parser = _BlockHtmlParser()
    parser.feed(content_html)
    parser.close()
    parser._flush()
    if parser.dropped:
        log.warning("stub_html_tags_dropped", source=source, tags=sorted(set(parser.dropped)))
    return [{"type": "text", "markdown": paragraph} for paragraph in parser.paragraphs]


def transform_lesson_item(item: dict[str, Any]) -> dict[str, Any]:
    """A lesson delivery item + ``translation.blocks`` from its ``contentHtml``
    (plan §4.5, §13.4)."""
    translation = dict(item.get("translation") or {})
    translation["blocks"] = html_to_blocks(
        translation.get("contentHtml"), source=f"lesson:{item.get('id')}"
    )
    return {**item, "translation": translation}


def question_prompt_blocks(
    question_text: str | None, *, media_id: str | None
) -> list[dict[str, Any]]:
    """A prompt: a ``text`` block (required first, plan §4.6) plus an optional image.

    ``shared.mediaId`` is already an asset id (``BoostQuestion.shared.media_id``,
    one of the field names ``boost_bridge``'s README calls confirmed), so no URL
    recovery is needed — only blocks carry asset ids at all (plan §4.6).
    """
    text = (question_text or "").strip()
    blocks: list[dict[str, Any]] = [{"type": "text", "markdown": text or "…"}]
    if media_id:
        blocks.append({"type": "image", "assetId": media_id, "alt": text or "Question media"})
    return blocks


def option_blocks(option_text: str | None) -> list[dict[str, Any]]:
    return [{"type": "text", "markdown": (option_text or "").strip() or "…"}]


def explanation_blocks(explanation_text: str | None, *, source: str) -> list[dict[str, Any]]:
    blocks = html_to_blocks(explanation_text, source=source)
    return blocks or [{"type": "text", "markdown": (explanation_text or "").strip() or "…"}]


def transform_question_item(item: dict[str, Any]) -> dict[str, Any]:
    """A question delivery item + ``topicKey`` and ``prompt``/``options[].blocks``
    (plan §4.5, §13.4).

    ``questionText`` and ``options[].text`` are kept (§13.4: "stay for existing
    consumers"); the blocks are additive.
    """
    shared = dict(item.get("shared") or {})
    translation = dict(item.get("translation") or {})
    lesson_id = shared.get("lessonId")
    if not shared.get("topicKey"):
        shared["topicKey"] = f"lesson-{lesson_id}" if lesson_id is not None else None
    translation["prompt"] = question_prompt_blocks(
        translation.get("questionText"), media_id=shared.get("mediaId")
    )
    translation["options"] = [
        {**option, "blocks": option_blocks(option.get("text"))}
        for option in translation.get("options", [])
    ]
    return {**item, "shared": shared, "translation": translation}


def topic_vocabulary(module_id: str, lesson_ids: Iterable[str]) -> list[dict[str, Any]]:
    """One placeholder topic per lesson of the module, matching the injected key (§4.5)."""
    return [
        {
            "key": f"lesson-{lesson_id}",
            "moduleId": module_id,
            "title": {"sv-SE": f"Lektion {lesson_id}", "en-GB": f"Lesson {lesson_id}"},
        }
        for lesson_id in sorted(set(lesson_ids), key=lambda i: int(i) if i.isdecimal() else 0)
    ]
