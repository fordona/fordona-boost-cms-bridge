"""Extension point for the AI recommendation engine.

A ``ContentSequencer`` decides which questions a learner sees, and in what
order, given the full published candidate set. Phase 1 ships only
``CmsOrderSequencer``, which keeps Boost's delivery order.

To plug in the recommendation engine:

1. Implement ``ContentSequencer``, for example an HTTP client for Damith's
   service. It may reorder, filter or select a subset of ``questions``. It
   must not invent questions that are not in the list.
2. Return it from ``build_services`` in ``main.py``, optionally behind a setting.

Routes, response schemas and the frontend contract stay the same. The engine
receives the learner's Kinde ``sub`` as a stable key for its own state. If it
fails, the implementation should fall back to the input order rather than
fail the request.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from boost_bridge.core.security import Learner
from boost_bridge.schemas.questions import Question


@dataclass(frozen=True, slots=True)
class SequencingContext:
    surface: Literal["lesson"]
    locale: str
    lesson_id: str | None = None
    module_id: str | None = None


class ContentSequencer(Protocol):
    async def sequence(
        self, learner: Learner, questions: list[Question], context: SequencingContext
    ) -> list[Question]: ...


class CmsOrderSequencer:
    """Default: keep the order Boost delivers."""

    async def sequence(
        self, learner: Learner, questions: list[Question], context: SequencingContext
    ) -> list[Question]:
        return list(questions)
