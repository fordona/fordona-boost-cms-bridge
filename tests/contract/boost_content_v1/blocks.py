"""Content-block validation for the §13 contract (plan §4.6, §13.4).

Pure functions: given a block list and where it appears, return every problem
found as a human-readable string. An empty list means the blocks conform.

What the plan fixes, and therefore what is enforced:

* the six block types and nothing else (Boost emits "exactly the block types in
  §4.6"; only *consumers* skip unknown types);
* the required fields: ``alt`` on image and animation, ``captions`` on video,
  ``transcript`` on audio, and the fields each type is defined by;
* where each type may appear (the "Allowed in" column), and that a prompt
  starts with a ``text`` block.

What the plan leaves open, and is therefore only checked loosely:

* image ``width``/``height`` are optional (§13.4's option example omits them),
  but must be positive integers when present;
* a video caption entry's shape beyond its ``locale`` is not defined.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any


class Context(StrEnum):
    THEORY = "theory"
    PROMPT = "prompt"
    OPTION = "option"
    EXPLANATION = "explanation"


BLOCK_TYPES: frozenset[str] = frozenset(
    {"text", "image", "animation", "video", "audio", "rule_card"}
)

ALLOWED_IN: Mapping[str, frozenset[Context]] = {
    "text": frozenset(Context),
    "image": frozenset(Context),
    "animation": frozenset({Context.THEORY, Context.PROMPT, Context.EXPLANATION}),
    "video": frozenset({Context.THEORY, Context.PROMPT, Context.EXPLANATION}),
    "audio": frozenset({Context.THEORY, Context.PROMPT}),
    "rule_card": frozenset({Context.THEORY, Context.EXPLANATION}),
}

ANIMATION_FORMATS = frozenset({"lottie", "video_loop"})
RULE_CARD_KINDS = frozenset({"RULE", "SIGN"})


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _require_str(block: Mapping[str, Any], field: str, where: str) -> list[str]:
    return [] if _non_empty_str(block.get(field)) else [f"{where}: '{field}' is required"]


def _image_fields(block: Mapping[str, Any], where: str) -> list[str]:
    problems = _require_str(block, "assetId", where) + _require_str(block, "alt", where)
    for field in ("width", "height"):
        if field in block and not _positive_int(block[field]):
            problems.append(f"{where}: '{field}' must be a positive integer when present")
    if "caption" in block and not isinstance(block["caption"], str):
        problems.append(f"{where}: 'caption' must be a string when present")
    return problems


def _check_text(block: Mapping[str, Any], where: str) -> list[str]:
    return _require_str(block, "markdown", where)


def _check_image(block: Mapping[str, Any], where: str) -> list[str]:
    return _image_fields(block, where)


def _check_animation(block: Mapping[str, Any], where: str) -> list[str]:
    problems = _require_str(block, "assetId", where) + _require_str(block, "alt", where)
    if block.get("format") not in ANIMATION_FORMATS:
        problems.append(f"{where}: 'format' must be one of {sorted(ANIMATION_FORMATS)}")
    return problems


def _check_video(block: Mapping[str, Any], where: str) -> list[str]:
    problems = _require_str(block, "assetId", where) + _require_str(block, "posterAssetId", where)
    if not _positive_number(block.get("durationSec")):
        problems.append(f"{where}: 'durationSec' must be a positive number")
    captions = block.get("captions")
    if not isinstance(captions, list) or not captions:
        problems.append(f"{where}: 'captions' is required (a non-empty list, one per locale)")
    else:
        for n, caption in enumerate(captions):
            if not isinstance(caption, Mapping) or not _non_empty_str(caption.get("locale")):
                problems.append(f"{where}: captions[{n}] needs a 'locale'")
    return problems


def _check_audio(block: Mapping[str, Any], where: str) -> list[str]:
    problems = _require_str(block, "assetId", where) + _require_str(block, "transcript", where)
    if not _positive_number(block.get("durationSec")):
        problems.append(f"{where}: 'durationSec' must be a positive number")
    return problems


def _check_rule_card(block: Mapping[str, Any], where: str) -> list[str]:
    problems = _require_str(block, "title", where)
    if block.get("kind") not in RULE_CARD_KINDS:
        problems.append(f"{where}: 'kind' must be one of {sorted(RULE_CARD_KINDS)}")
    points = block.get("points")
    if not isinstance(points, list) or not points or not all(_non_empty_str(p) for p in points):
        problems.append(f"{where}: 'points' must be a non-empty list of strings")
    if "image" in block:
        image = block["image"]
        if not isinstance(image, Mapping):
            problems.append(f"{where}: 'image' must be an object when present")
        else:
            problems += _image_fields(image, f"{where}.image")
    return problems


_CHECKS = {
    "text": _check_text,
    "image": _check_image,
    "animation": _check_animation,
    "video": _check_video,
    "audio": _check_audio,
    "rule_card": _check_rule_card,
}


def validate_blocks(blocks: Any, context: Context, *, path: str = "blocks") -> list[str]:
    """Every way ``blocks`` breaks the §4.6 rules for ``context``."""
    if not isinstance(blocks, list):
        return [f"{path}: must be a list of blocks"]
    problems: list[str] = []
    if context is Context.PROMPT and (
        not blocks or not isinstance(blocks[0], Mapping) or blocks[0].get("type") != "text"
    ):
        problems.append(f"{path}: a prompt must start with a 'text' block")
    if context is Context.OPTION and not blocks:
        problems.append(f"{path}: an option needs at least one block")
    for n, block in enumerate(blocks):
        where = f"{path}[{n}]"
        if not isinstance(block, Mapping):
            problems.append(f"{where}: must be an object")
            continue
        block_type = block.get("type")
        if block_type not in BLOCK_TYPES:
            problems.append(f"{where}: unknown block type {block_type!r}")
            continue
        if context not in ALLOWED_IN[block_type]:
            problems.append(f"{where}: '{block_type}' is not allowed in {context.value}")
        problems += _CHECKS[block_type](block, where)
    return problems


def validate_locale_blocks(
    by_locale: Any, locales: Sequence[str], context: Context, *, path: str
) -> list[str]:
    """A ``{locale: blocks}`` map (grading explanations) with every required locale."""
    if not isinstance(by_locale, Mapping):
        return [f"{path}: must be an object keyed by locale"]
    problems = [f"{path}: locale {loc!r} is missing" for loc in locales if loc not in by_locale]
    for locale, blocks in by_locale.items():
        problems += validate_blocks(blocks, context, path=f"{path}.{locale}")
    return problems
