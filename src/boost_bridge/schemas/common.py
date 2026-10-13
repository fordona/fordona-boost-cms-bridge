"""Shared API schemas. JSON is camelCase to match fordona-engine and Boost."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ID_PATTERN = r"^[1-9][0-9]*$"

ContentId = Annotated[
    str,
    Field(
        pattern=ID_PATTERN,
        description="Decimal-string identifier. Kept as a string: 64-bit ids lose "
        "precision as JavaScript numbers.",
        examples=["42"],
    ),
]


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Media(APIModel):
    type: str = Field(description="image, video, audio or document", examples=["image"])
    url: str = Field(description="Absolute, public, immutable asset URL.")


class Localized(APIModel):
    locale: str | None = Field(description="Locale this representation is in.", examples=["sv-SE"])
    available_locales: list[str] = Field(description="Locales this content is published in.")


class Page[ItemT: BaseModel](APIModel):
    items: list[ItemT]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    as_of: datetime | None = Field(default=None, description="Upstream snapshot time.")


class FieldError(APIModel):
    field: str
    location: str
    message: str


class Problem(APIModel):
    """RFC 7807 problem details, the same shape fordona-engine returns."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    error_code: str
    correlation_id: str | None
    field_errors: list[FieldError] | None = None
