"""render_blocks: every block type, an unknown type dropped, an unresolvable asset dropped."""

from pydantic import TypeAdapter

from fordona_connect.clients.boost.models import ContentBlock
from fordona_connect.schemas.content_blocks import (
    AnimationBlockOut,
    AudioBlockOut,
    ImageBlockOut,
    RuleCardBlockOut,
    TextBlockOut,
    VideoBlockOut,
)
from fordona_connect.services.blocks import render_blocks
from fordona_connect.services.media import AssetUrlResolver, PlainUrlSigner

BASE = "https://media.test"


def _resolver() -> AssetUrlResolver:
    plain = PlainUrlSigner(BASE)
    return AssetUrlResolver(frozenset(), plain, plain)


_BLOCK_ADAPTER: TypeAdapter[ContentBlock] = TypeAdapter(ContentBlock)


def _block(data: dict[str, object]) -> ContentBlock:
    return _BLOCK_ADAPTER.validate_python(data)


def test_text_block_passes_through_markdown() -> None:
    out = render_blocks(
        [_block({"type": "text", "markdown": "Hello *world*"})], _resolver(), unit_id=None
    )

    assert out == [TextBlockOut(markdown="Hello *world*")]


def test_image_block_resolves_url_and_srcset() -> None:
    block = _block(
        {"type": "image", "assetId": "77", "alt": "Give-way sign", "width": 960, "height": 540}
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, ImageBlockOut)
    assert out.url == f"{BASE}/i/77/960.webp"
    assert len(out.srcset) == 3
    assert out.alt == "Give-way sign"
    assert out.width == 960
    assert out.height == 540


def test_animation_block_lottie_format_uses_lottie_url() -> None:
    block = _block(
        {"type": "animation", "assetId": "12", "format": "lottie", "alt": "Turning left"}
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, AnimationBlockOut)
    assert out.format == "lottie"
    assert "/a/12/animation.json" in out.url


def test_animation_block_video_loop_format_uses_loop_url() -> None:
    block = _block(
        {"type": "animation", "assetId": "12", "format": "video_loop", "alt": "Turning left"}
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, AnimationBlockOut)
    assert "/v/12/loop.mp4" in out.url


def test_video_block_resolves_hls_poster_and_captions() -> None:
    block = _block(
        {
            "type": "video",
            "assetId": "81",
            "posterAssetId": "82",
            "durationSec": 94,
            "captions": [{"locale": "sv-SE", "fileId": "90"}],
        }
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, VideoBlockOut)
    assert "/v/81/master.m3u8" in out.hls_url
    assert out.poster_url is not None
    assert "/i/82/poster.jpg" in out.poster_url
    assert out.duration_sec == 94
    assert len(out.captions) == 1
    assert out.captions[0].locale == "sv-SE"
    assert "/c/90.vtt" in out.captions[0].url


def test_video_block_without_poster_has_no_poster_url() -> None:
    block = _block({"type": "video", "assetId": "81", "durationSec": 94})

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, VideoBlockOut)
    assert out.poster_url is None


def test_audio_block_resolves_hls_and_keeps_transcript() -> None:
    block = _block({"type": "audio", "assetId": "90", "durationSec": 420, "transcript": "…"})

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, AudioBlockOut)
    assert "/v/90/master.m3u8" in out.hls_url
    assert out.duration_sec == 420
    assert out.transcript == "…"


def test_rule_card_block_without_image() -> None:
    block = _block(
        {
            "type": "rule_card",
            "kind": "RULE",
            "title": "Right-Hand Right of Way",
            "points": ["Vehicles coming from the right have the right of way."],
        }
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, RuleCardBlockOut)
    assert out.kind == "RULE"
    assert out.image is None


def test_rule_card_block_with_image() -> None:
    block = _block(
        {
            "type": "rule_card",
            "kind": "SIGN",
            "title": "Give way",
            "points": ["Yield to traffic on the main road."],
            "image": {"assetId": "5", "alt": "Give-way sign"},
        }
    )

    [out] = render_blocks([block], _resolver(), unit_id=None)

    assert isinstance(out, RuleCardBlockOut)
    assert out.image is not None
    assert "/i/5/960.webp" in out.image.url


def test_unknown_block_type_is_dropped_and_logged() -> None:
    block = _block({"type": "interactive_quiz", "foo": "bar"})

    out = render_blocks([block], _resolver(), unit_id=None)

    assert out == []


def test_image_block_with_no_asset_id_is_dropped() -> None:
    block = _block({"type": "image", "assetId": "", "alt": "broken"})

    out = render_blocks([block], _resolver(), unit_id=None)

    assert out == []


def test_one_bad_block_does_not_drop_the_rest() -> None:
    good = _block({"type": "text", "markdown": "ok"})
    bad = _block({"type": "unknown_future_type"})

    out = render_blocks([good, bad], _resolver(), unit_id=None)

    assert out == [TextBlockOut(markdown="ok")]


def test_free_unit_blocks_get_plain_urls() -> None:
    signed_resolver = AssetUrlResolver(
        frozenset({"1"}),
        PlainUrlSigner(BASE),
        PlainUrlSigner(BASE),  # stand-in; real signing is covered in test_media.py
    )
    block = _block({"type": "image", "assetId": "77", "alt": "x"})

    [out] = render_blocks([block], signed_resolver, unit_id="1")

    assert isinstance(out, ImageBlockOut)
    assert out.url == f"{BASE}/i/77/960.webp"
