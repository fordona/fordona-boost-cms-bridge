"""Maps Boost content blocks to the public block shapes (Plan §4.6, §7.3, P6.T4).

An unknown block type, or a known block type missing its required asset id,
is dropped from the list and logged — the whole response never fails for one
bad block (§4.6: "an asset that can't be resolved is dropped from the
response... never shown as a broken screen"; "an unknown block type is
skipped by the app" — this is the server-side half of that same rule, so a
client that *does* understand a type the BFF itself doesn't yet map still
never sees it either, which is the conservative direction to be wrong in).
"""

from boost_bridge.clients.boost.models import (
    AnimationBlock,
    AudioBlock,
    ContentBlock,
    ImageBlock,
    RuleCardBlock,
    TextBlock,
    VideoBlock,
)
from boost_bridge.core.logging import get_logger
from boost_bridge.schemas.content_blocks import (
    AnimationBlockOut,
    AudioBlockOut,
    ContentBlockOut,
    ImageBlockOut,
    RuleCardBlockOut,
    TextBlockOut,
    VideoBlockOut,
    VideoCaptionOut,
)
from boost_bridge.services.media import AssetUrlResolver

log = get_logger(__name__)


def render_blocks(
    blocks: list[ContentBlock], resolver: AssetUrlResolver, *, unit_id: str | None
) -> list[ContentBlockOut]:
    rendered: list[ContentBlockOut] = []
    for block in blocks:
        out = _render_one(block, resolver, unit_id=unit_id)
        if out is not None:
            rendered.append(out)
    return rendered


def _render_one(
    block: ContentBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> ContentBlockOut | None:
    if isinstance(block, TextBlock):
        return TextBlockOut(markdown=block.markdown)
    if isinstance(block, ImageBlock):
        return _render_image(block, resolver, unit_id=unit_id)
    if isinstance(block, AnimationBlock):
        return _render_animation(block, resolver, unit_id=unit_id)
    if isinstance(block, VideoBlock):
        return _render_video(block, resolver, unit_id=unit_id)
    if isinstance(block, AudioBlock):
        return _render_audio(block, resolver, unit_id=unit_id)
    if isinstance(block, RuleCardBlock):
        return _render_rule_card(block, resolver, unit_id=unit_id)
    # UnknownBlock, or anything else a future union variant falls through to.
    log.warning("block_type_unknown", type=getattr(block, "type", "?"))
    return None


def _render_image(
    block: ImageBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> ImageBlockOut | None:
    if not block.asset_id:
        log.warning("block_asset_unresolvable", block_type="image")
        return None
    return ImageBlockOut(
        url=resolver.image_url(block.asset_id, unit_id=unit_id),
        srcset=resolver.image_srcset(block.asset_id, unit_id=unit_id),
        alt=block.alt,
        width=block.width,
        height=block.height,
        caption=block.caption,
    )


def _render_animation(
    block: AnimationBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> AnimationBlockOut | None:
    if not block.asset_id:
        log.warning("block_asset_unresolvable", block_type="animation")
        return None
    url = (
        resolver.lottie_url(block.asset_id, unit_id=unit_id)
        if block.format == "lottie"
        else resolver.video_loop_url(block.asset_id, unit_id=unit_id)
    )
    return AnimationBlockOut(format=block.format, url=url, alt=block.alt)


def _render_video(
    block: VideoBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> VideoBlockOut | None:
    if not block.asset_id:
        log.warning("block_asset_unresolvable", block_type="video")
        return None
    poster_url = (
        resolver.poster_url(block.poster_asset_id, unit_id=unit_id)
        if block.poster_asset_id
        else None
    )
    captions = [
        VideoCaptionOut(
            locale=caption.locale, url=resolver.caption_url(caption.file_id, unit_id=unit_id)
        )
        for caption in block.captions
        if caption.file_id
    ]
    return VideoBlockOut(
        hls_url=resolver.hls_url(block.asset_id, unit_id=unit_id),
        poster_url=poster_url,
        duration_sec=block.duration_sec,
        captions=captions,
    )


def _render_audio(
    block: AudioBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> AudioBlockOut | None:
    if not block.asset_id:
        log.warning("block_asset_unresolvable", block_type="audio")
        return None
    return AudioBlockOut(
        hls_url=resolver.hls_url(block.asset_id, unit_id=unit_id),
        duration_sec=block.duration_sec,
        transcript=block.transcript,
    )


def _render_rule_card(
    block: RuleCardBlock, resolver: AssetUrlResolver, *, unit_id: str | None
) -> RuleCardBlockOut:
    image_out = None
    if block.image is not None and block.image.asset_id:
        image_out = ImageBlockOut(
            url=resolver.image_url(block.image.asset_id, unit_id=unit_id),
            srcset=resolver.image_srcset(block.image.asset_id, unit_id=unit_id),
            alt=block.image.alt,
            width=block.image.width,
            height=block.image.height,
            caption=block.image.caption,
        )
    elif block.image is not None:
        log.warning("block_asset_unresolvable", block_type="rule_card_image")
    return RuleCardBlockOut(
        kind=block.kind, title=block.title, points=block.points, image=image_out
    )
