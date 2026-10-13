"""Typed models of Boost delivery payloads.

UNVERIFIED: Boost's OpenAPI document types every delivery response as a bare
``object``. These models are inferred from its ``Entity`` and ``Page`` schemas
(``id, version, locale, shared, translation, availableLocales, resources``) and
from the field sets of ``QuestionMutation``, ``ModuleMutation`` and
``LessonMutation``. Check them against a real payload as soon as a delivery
token is available (design doc §12, risk 2).

Two choices make them tolerant of drift until then:

* ``extra="ignore"`` everywhere, so new upstream fields never break parsing.
* ``_EntityBase`` also accepts a *flat* entity, with fields at the top level
  instead of under ``shared``/``translation``, in case delivery flattens what
  the editorial API nests.

Answer fields (``correctOptionId``, ``explanation``) are deliberately **not
modelled**. Code that does not exist cannot leak them.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class BoostModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", alias_generator=to_camel, populate_by_name=True, frozen=True
    )


class Resource(BoostModel):
    """An attached file. ``fileId`` is a public asset id once the content is published."""

    file_id: str
    type: str
    placement: str | None = None


class _EntityBase(BoostModel):
    id: str
    version: str | None = None
    locale: str | None = None
    available_locales: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None
    resources: list[Resource] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_shape(cls, data: Any) -> Any:
        if isinstance(data, dict) and "shared" not in data and "translation" not in data:
            return {**data, "shared": data, "translation": data}
        return data


# --- Modules ---------------------------------------------------------------


class ModuleShared(BoostModel):
    icon_id: str | None = None
    cover_image_id: str | None = None


class ModuleTranslation(BoostModel):
    title: str | None = None
    slug: str | None = None
    description: str | None = None


class BoostModule(_EntityBase):
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


class BoostLesson(_EntityBase):
    shared: LessonShared = Field(default_factory=LessonShared)
    translation: LessonTranslation | None = None


# --- Questions -------------------------------------------------------------


class QuestionOption(BoostModel):
    id: str
    text: str


class QuestionShared(BoostModel):
    type: str | None = None
    lesson_id: str | None = None
    module_id: str | None = None
    subject_id: str | None = None
    difficulty: int | None = None
    points: int | None = None
    media_id: str | None = None
    media_type: str | None = None


class QuestionTranslation(BoostModel):
    question_text: str | None = None
    options: list[QuestionOption] = Field(default_factory=list)


class BoostQuestion(_EntityBase):
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
