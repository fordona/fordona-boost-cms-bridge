"""The §4.6 block validator used by the Boost contract suite."""

from typing import Any

import pytest

from tests.contract.boost_content_v1.blocks import (
    Context,
    validate_blocks,
    validate_locale_blocks,
)

TEXT = {"type": "text", "markdown": "Vehicles coming from your right."}
IMAGE = {"type": "image", "assetId": "a77", "alt": "Car park exit", "width": 1440, "height": 810}
LOTTIE = {"type": "animation", "assetId": "l12", "format": "lottie", "alt": "Indicator blinking"}
LOOP = {"type": "animation", "assetId": "g3", "format": "video_loop", "alt": "Roundabout"}
VIDEO = {
    "type": "video",
    "assetId": "v81",
    "posterAssetId": "p81",
    "durationSec": 94,
    "captions": [{"locale": "sv-SE", "assetId": "c1"}, {"locale": "en-GB", "assetId": "c2"}],
}
AUDIO = {"type": "audio", "assetId": "a90", "durationSec": 420, "transcript": "Welcome …"}
RULE_CARD = {
    "type": "rule_card",
    "kind": "RULE",
    "title": "Right-Hand Right of Way",
    "points": ["Vehicles (including bicycles) coming from the right have the right of way."],
}


def _without(block: dict[str, Any], field: str) -> dict[str, Any]:
    return {k: v for k, v in block.items() if k != field}


# --- valid content -------------------------------------------------------------


def test_every_block_type_is_valid_in_theory() -> None:
    blocks = [TEXT, IMAGE, LOTTIE, LOOP, VIDEO, AUDIO, RULE_CARD]

    assert validate_blocks(blocks, Context.THEORY) == []


def test_option_may_be_an_image_without_dimensions() -> None:
    sign = {"type": "image", "assetId": "a91", "alt": "Give-way sign"}  # §13.4 example

    assert validate_blocks([sign], Context.OPTION) == []


def test_prompt_with_text_first_then_media_is_valid() -> None:
    assert validate_blocks([TEXT, IMAGE, VIDEO, AUDIO], Context.PROMPT) == []


def test_explanation_may_hold_a_rule_card_with_an_image() -> None:
    card = {**RULE_CARD, "kind": "SIGN", "image": {"assetId": "s1", "alt": "Stop sign"}}

    assert validate_blocks([TEXT, card], Context.EXPLANATION) == []


# --- required fields -----------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "field"),
    [
        (TEXT, "markdown"),
        (IMAGE, "assetId"),
        (IMAGE, "alt"),
        (LOTTIE, "alt"),
        (LOTTIE, "assetId"),
        (VIDEO, "captions"),
        (VIDEO, "posterAssetId"),
        (VIDEO, "durationSec"),
        (AUDIO, "transcript"),
        (AUDIO, "durationSec"),
        (RULE_CARD, "title"),
        (RULE_CARD, "points"),
    ],
)
def test_missing_required_field_is_reported(block: dict[str, Any], field: str) -> None:
    problems = validate_blocks([_without(block, field)], Context.THEORY)

    assert problems
    assert all(f"'{field}'" in p for p in problems)


def test_blank_alt_is_missing() -> None:
    assert validate_blocks([{**IMAGE, "alt": "  "}], Context.THEORY)


def test_empty_captions_are_missing() -> None:
    assert validate_blocks([{**VIDEO, "captions": []}], Context.THEORY)


def test_caption_without_locale_is_reported() -> None:
    problems = validate_blocks([{**VIDEO, "captions": [{"assetId": "c1"}]}], Context.THEORY)

    assert problems == ["blocks[0]: captions[0] needs a 'locale'"]


def test_non_positive_image_dimension_is_reported() -> None:
    assert validate_blocks([{**IMAGE, "width": 0}], Context.THEORY)


def test_unknown_animation_format_is_reported() -> None:
    assert validate_blocks([{**LOTTIE, "format": "gif"}], Context.THEORY)


def test_unknown_rule_card_kind_is_reported() -> None:
    assert validate_blocks([{**RULE_CARD, "kind": "TIP"}], Context.THEORY)


# --- where blocks may appear ---------------------------------------------------


@pytest.mark.parametrize(
    ("block", "context"),
    [
        (LOTTIE, Context.OPTION),
        (VIDEO, Context.OPTION),
        (AUDIO, Context.OPTION),
        (AUDIO, Context.EXPLANATION),
        (RULE_CARD, Context.PROMPT),
        (RULE_CARD, Context.OPTION),
    ],
)
def test_block_outside_its_allowed_places_is_reported(
    block: dict[str, Any], context: Context
) -> None:
    blocks = [TEXT, block] if context is Context.PROMPT else [block]

    problems = validate_blocks(blocks, context)

    assert any("is not allowed in" in p for p in problems)


def test_prompt_must_start_with_text() -> None:
    problems = validate_blocks([IMAGE, TEXT], Context.PROMPT)

    assert problems == ["blocks: a prompt must start with a 'text' block"]


def test_empty_prompt_is_reported() -> None:
    assert validate_blocks([], Context.PROMPT)


def test_empty_option_is_reported() -> None:
    assert validate_blocks([], Context.OPTION)


def test_empty_theory_is_allowed_by_the_block_rules() -> None:
    # Empty theory hides the lesson at engine sync (plan §4.4); it is not a block error.
    assert validate_blocks([], Context.THEORY) == []


# --- malformed input -----------------------------------------------------------


def test_unknown_block_type_is_reported() -> None:
    problems = validate_blocks([{"type": "gif", "assetId": "x"}], Context.THEORY)

    assert problems == ["blocks[0]: unknown block type 'gif'"]


def test_non_list_is_reported() -> None:
    assert validate_blocks(None, Context.THEORY) == ["blocks: must be a list of blocks"]


def test_non_object_block_is_reported() -> None:
    assert validate_blocks(["text"], Context.THEORY) == ["blocks[0]: must be an object"]


def test_problems_name_their_path() -> None:
    problems = validate_blocks([TEXT, _without(IMAGE, "alt")], Context.THEORY, path="prompt")

    assert problems == ["prompt[1]: 'alt' is required"]


# --- per-locale maps (grading explanations) ------------------------------------


def test_locale_map_with_every_locale_is_valid() -> None:
    by_locale = {"sv-SE": [TEXT], "en-GB": [TEXT, RULE_CARD]}

    assert (
        validate_locale_blocks(by_locale, ["sv-SE", "en-GB"], Context.EXPLANATION, path="e") == []
    )


def test_locale_map_missing_a_locale_is_reported() -> None:
    problems = validate_locale_blocks(
        {"sv-SE": [TEXT]}, ["sv-SE", "en-GB"], Context.EXPLANATION, path="e"
    )

    assert problems == ["e: locale 'en-GB' is missing"]


def test_locale_map_validates_each_locale_in_context() -> None:
    problems = validate_locale_blocks({"sv-SE": [AUDIO]}, ["sv-SE"], Context.EXPLANATION, path="e")

    assert problems == ["e.sv-SE[0]: 'audio' is not allowed in explanation"]


def test_non_map_explanation_is_reported() -> None:
    assert validate_locale_blocks([TEXT], ["sv-SE"], Context.EXPLANATION, path="e") == [
        "e: must be an object keyed by locale"
    ]
