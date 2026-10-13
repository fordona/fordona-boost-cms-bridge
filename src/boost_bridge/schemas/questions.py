"""Question schemas. **Answer-free by construction**: there is no field for the
correct option or the explanation, so neither can be serialised by accident."""

from pydantic import Field

from boost_bridge.schemas.common import APIModel, ContentId, Localized, Media


class QuestionOption(APIModel):
    id: str = Field(examples=["a"])
    text: str


class Question(Localized):
    id: ContentId
    version: str | None = Field(
        description="Published revision. Pin it to fetch this exact revision later."
    )
    type: str | None = Field(examples=["mcq", "truefalse"])
    module_id: str | None
    lesson_id: str | None
    subject_id: str | None
    difficulty: int | None = Field(description="1 (easiest) to 5.")
    points: int | None
    question_text: str | None
    options: list[QuestionOption]
    media: Media | None


class LessonQuestions(APIModel):
    """All published questions of a lesson, in delivery order.

    The list is not paginated: a sequencer (and later the recommendation
    engine) needs the full candidate set to order or select from.
    """

    lesson_id: ContentId
    items: list[Question]
    total: int = Field(ge=0)
