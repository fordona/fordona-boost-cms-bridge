"""Typed models of Boost delivery payloads.

Boost's OpenAPI document types every delivery response as a bare ``object``.
These models are built from three sources:

* **Boost's API docs** (boost.fordona.io/api-docs, "Published content"): a list
  returns ``items, total, page, pageSize, asOf``, and each item has a string
  ``id``, an immutable ``version``, ``locale``, ``shared``, ``translation``,
  ``resources`` and ``assetBaseUrl``.
* **Field names inside ``shared``/``translation``**: Boost's ``*Mutation``
  schemas, cross-checked against the field names its CMS editor uses.
* **Still UNVERIFIED** until a real delivery payload is captured (design doc
  §12): the exact form of ``assetBaseUrl``, and whether delivery items carry
  ``availableLocales``/``updatedAt``. Both are optional here.

Two choices keep the models tolerant of drift:

* ``extra="ignore"`` everywhere, so new upstream fields never break parsing.
* ``BoostEntity`` also accepts a *flat* entity, with fields at the top level
  instead of under ``shared``/``translation``, in case delivery flattens what
  the editorial API nests.

Answer fields (``correctOptionId``, ``explanation``) are deliberately **not
modelled**. Code that does not exist cannot leak them.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class BoostModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", alias_generator=to_camel, populate_by_name=True, frozen=True
    )


# --- Content blocks (Plan §4.6, §13.4) --------------------------------------
#
# Theory, question prompts, options and explanations all use one block format.
# Explanation blocks are not modelled here at all (grading-only, never reaches
# the BFF — see the module docstring's answer-fields rule); this covers theory,
# prompt and option blocks, the only ones the delivery API ever returns.
#
# ``UnknownBlock`` is the forward-compatible fallback: §4.6 says "an unknown
# block type is skipped by the app," which only works if parsing a block list
# containing one never raises in the first place. Deciding what to *do* with
# an unknown block (drop it, log it) is P6.T4's job; this layer only needs to
# not crash on one.


class TextBlock(BoostModel):
    type: Literal["text"] = "text"
    markdown: str


class ImageBlock(BoostModel):
    type: Literal["image"] = "image"
    asset_id: str
    alt: str
    width: int | None = None
    height: int | None = None
    caption: str | None = None


class AnimationBlock(BoostModel):
    type: Literal["animation"] = "animation"
    asset_id: str
    format: str  # "lottie" or "video_loop"
    alt: str


class VideoCaption(BoostModel):
    locale: str | None = None
    # UNVERIFIED (no real payload captured yet): assumed to be a published file
    # id, matching how every other asset reference in this contract works.
    file_id: str | None = None


class VideoBlock(BoostModel):
    type: Literal["video"] = "video"
    asset_id: str
    poster_asset_id: str | None = None
    duration_sec: int | None = None
    captions: list[VideoCaption] = Field(default_factory=list)


class AudioBlock(BoostModel):
    type: Literal["audio"] = "audio"
    asset_id: str
    duration_sec: int | None = None
    transcript: str | None = None


class RuleCardBlock(BoostModel):
    type: Literal["rule_card"] = "rule_card"
    kind: str  # "RULE" or "SIGN"
    title: str
    points: list[str] = Field(default_factory=list)
    image: ImageBlock | None = None


class UnknownBlock(BoostModel):
    """Anything whose ``type`` isn't one of the above — kept, never dropped here."""

    type: str


ContentBlock = Annotated[
    TextBlock
    | ImageBlock
    | AnimationBlock
    | VideoBlock
    | AudioBlock
    | RuleCardBlock
    | UnknownBlock,
    Field(union_mode="left_to_right"),
]


class Resource(BoostModel):
    """An attached file. ``fileId`` is a public asset id once the content is published."""

    file_id: str
    type: str
    placement: str | None = None


class BoostEntity(BoostModel):
    id: str
    version: str | None = None
    locale: str | None = None
    # Not listed among delivery item fields in Boost's docs; None when absent.
    available_locales: list[str] | None = None
    updated_at: datetime | None = None
    resources: list[Resource] = Field(default_factory=list)
    # Per Boost's docs: "Build media URLs from assetBaseUrl and the returned asset ID".
    asset_base_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_shape(cls, data: Any) -> Any:
        if isinstance(data, dict) and "shared" not in data and "translation" not in data:
            return {**data, "shared": data, "translation": data}
        return data

    @field_validator("resources", mode="before")
    @classmethod
    def _null_resources_is_empty(cls, value: Any) -> Any:
        """2026-11-07, confirmed against a live boost-api-dev response: Boost's list
        endpoints (``GET /v1/delivery/questions``) send ``resources: []``, but its
        single-item endpoint (``GET /v1/delivery/questions/{id}/revisions/{version}``)
        sends ``resources: null`` for the exact same entity — an inconsistency between
        Boost's own endpoints, not a missing field. Every single-ref fetch failed
        pydantic validation on this (``list_type``, "Input should be a valid list"),
        surfacing as an unhandled ``BoostUnavailable``/503 for every attempt start.
        """
        return [] if value is None else value


# --- Modules ---------------------------------------------------------------


class ModuleShared(BoostModel):
    icon_id: str | None = None
    cover_image_id: str | None = None


class ModuleTranslation(BoostModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None


class BoostModule(BoostEntity):
    shared: ModuleShared = Field(default_factory=ModuleShared)
    translation: ModuleTranslation | None = None


# --- Lessons ---------------------------------------------------------------


class LessonShared(BoostModel):
    module_id: str | None = None
    estimated_read_minutes: int | None = None
    # Intended for the AI layer, never sent to the frontend (see mappers).
    ai_context_summary: str | None = None


class LessonTranslation(BoostModel):
    title: str | None = None
    slug: str | None = None
    content_html: str | None = None
    # §13.4 (new): the theory itself, as a block list. ``content_html`` stays
    # for existing consumers; a lesson revision carries both.
    blocks: list[ContentBlock] = Field(default_factory=list)


class BoostLesson(BoostEntity):
    shared: LessonShared = Field(default_factory=LessonShared)
    translation: LessonTranslation | None = None


# --- Questions -------------------------------------------------------------


class QuestionOption(BoostModel):
    id: str
    # §13.4's new shape: an option carries ``blocks`` instead of plain ``text``.
    # Neither field is required on its own, so an option with only one of them
    # (old-shape ``text``-only, or new-shape ``blocks``-only) still parses.
    text: str | None = None
    blocks: list[ContentBlock] = Field(default_factory=list)


class QuestionShared(BoostModel):
    type: str | None = None
    lesson_id: str | None = None
    module_id: str | None = None
    subject_id: str | None = None
    difficulty: int | None = None
    points: int | None = None
    media_id: str | None = None
    media_type: str | None = None
    # §13.4 (new).
    topic_key: str | None = None


class QuestionTranslation(BoostModel):
    question_text: str | None = None
    options: list[QuestionOption] = Field(default_factory=list)
    # §13.4 (new): the prompt as a block list, required and text-first per §4.6 —
    # not enforced here (Boost's own publish-time validation owns that rule).
    prompt: list[ContentBlock] = Field(default_factory=list)


class BoostQuestion(BoostEntity):
    shared: QuestionShared = Field(default_factory=QuestionShared)
    translation: QuestionTranslation | None = None


# --- Pages -----------------------------------------------------------------


class BoostPage[ItemT: BoostModel](BoostModel):
    items: list[ItemT]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    as_of: datetime | None = None


class BoostProblem(BoostModel):
    """Boost's error body: ``{status, code, detail, requestId, errors}``."""

    status: int | None = None
    code: str | None = None
    detail: str | None = None
    request_id: str | None = None
