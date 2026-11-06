"""Shared API schemas. JSON is camelCase to match fordona-engine and Boost."""

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
