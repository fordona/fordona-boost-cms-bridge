"""Learning-journey content as the journey service reads it.

The journey's structure (milestones, challenges, quizzes) is authored in Boost and
synced into the content tables; question text and options come from Boost's
published question bodies. ``boost_content.BoostJourneyContent`` builds these
objects from both. They hold answer keys (``QuestionContent.correct_answer``):
internal only, frozen into an attempt and never serialised in a read response.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class JourneyContent:
    journey_id: str
    version: int
    title: str
    description: str | None
    # milestone_count, challenge_count, question_count
    stats: dict[str, int]


@dataclass(frozen=True, slots=True)
class MilestoneContent:
    milestone_id: str
    journey_id: str
    position: int
    title: str
    description: str | None
    challenge_count: int
    question_count: int
    difficulty_distribution: dict[str, int]


@dataclass(frozen=True, slots=True)
class ChallengeContent:
    challenge_id: str
    milestone_id: str
    journey_id: str
    version: int
    position: int
    display_code: str
    title: str
    description: str | None
    estimated_minutes: int | None
    question_count: int
    difficulty_distribution: dict[str, int]
    # {"status": "READY"} when every quiz question can be served.
    content_readiness: dict[str, Any]
    topics: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class QuestionContent:
    question_id: str
    question_version: int
    question_type: str
    question_text: str
    difficulty: int
    level: str
    image_urls: list[str]
    has_image_reference: bool
    # [{"option_id", "text", "image_urls", "position"}], in authored order.
    options: list[dict[str, Any]]
    # {"option_ids": [...]}: grading data, never serialised in a read response.
    correct_answer: dict[str, list[str]]
    explanation: Any
    connected_chapters: list[str]
    cms_row_numbers: list[int] = field(default_factory=list)


class JourneyContentSource(Protocol):
    """Where the journey service reads content from."""

    async def journey_id(self) -> str | None:
        """The journey learners are assigned, or ``None`` if none is published."""
        ...

    async def free_milestone_id(self) -> str | None:
        """The milestone open without a subscription: the journey's first."""
        ...

    async def get_journey_template(self, journey_id: str) -> JourneyContent | None: ...

    async def list_milestones(self, journey_id: str) -> Sequence[MilestoneContent]: ...

    async def get_milestone(self, milestone_id: str) -> MilestoneContent | None: ...

    async def list_challenges_for_milestone(
        self, milestone_id: str
    ) -> Sequence[ChallengeContent]: ...

    async def get_challenge(self, challenge_id: str) -> ChallengeContent | None: ...

    async def list_questions_for_challenge(
        self, challenge_id: str
    ) -> Sequence[tuple[QuestionContent, int]]: ...

    async def get_questions_by_ids(
        self, question_ids: Sequence[str]
    ) -> dict[str, QuestionContent]: ...
