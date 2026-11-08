"""Typed models of fordona-engine's internal API envelope.

Two shapes only: the ``Payload<T>`` success envelope and the RFC 7807 problem
body every error renders as (``GlobalExceptionHandler``, mirrored by this
service's own ``core/errors.py``). ``response``/the problem's business fields
stay untyped ``Any``/``str`` here — a specific route's service layer (P6.T5)
validates ``response`` into its own schema; this client only unwraps the
envelope.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class EngineModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", alias_generator=to_camel, populate_by_name=True, frozen=True
    )


class EnginePayload(EngineModel):
    """fordona-engine's ``Payload<T>`` success envelope."""

    code: int
    status: str
    message: str | None = None
    response: Any = None


class EngineProblem(EngineModel):
    """fordona-engine's RFC 7807 problem body (``GlobalExceptionHandler``)."""

    type: str | None = None
    title: str | None = None
    status: int | None = None
    detail: str | None = None
    instance: str | None = None
    error_code: str | None = None
    correlation_id: str | None = None
