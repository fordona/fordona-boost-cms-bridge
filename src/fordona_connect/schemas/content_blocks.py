"""Public content-block shapes (Plan §7.3). ``srcset`` is a plain list of resolved
URLs (matching the plan's own example), not CSS srcset syntax with width
descriptors — the app already knows which width it asked for from the list
order/content, so there is nothing else to encode.
"""

from typing import Literal

from pydantic import Field

from fordona_connect.schemas.common import APIModel


class TextBlockOut(APIModel):
    type: Literal["text"] = "text"
    markdown: str


class ImageBlockOut(APIModel):
    type: Literal["image"] = "image"
    url: str
    srcset: list[str] = Field(default_factory=list)
    alt: str
    width: int | None = None
    height: int | None = None
    caption: str | None = None


class AnimationBlockOut(APIModel):
    type: Literal["animation"] = "animation"
    format: str
    url: str
    alt: str


class VideoCaptionOut(APIModel):
    locale: str | None = None
    url: str


class VideoBlockOut(APIModel):
    type: Literal["video"] = "video"
    hls_url: str
    poster_url: str | None = None
    duration_sec: int | None = None
    captions: list[VideoCaptionOut] = Field(default_factory=list)


class AudioBlockOut(APIModel):
    type: Literal["audio"] = "audio"
    hls_url: str
    duration_sec: int | None = None
    transcript: str | None = None


class RuleCardBlockOut(APIModel):
    type: Literal["rule_card"] = "rule_card"
    kind: str
    title: str
    points: list[str] = Field(default_factory=list)
    image: ImageBlockOut | None = None


ContentBlockOut = (
    TextBlockOut
    | ImageBlockOut
    | AnimationBlockOut
    | VideoBlockOut
    | AudioBlockOut
    | RuleCardBlockOut
)
