"""Building small content snapshots for tests."""

from fordona_connect.learning.content.snapshot import (
    ActiveQuestion,
    ContentSnapshot,
    SnapshotChallenge,
    SnapshotLesson,
    SnapshotUnit,
    build_snapshot,
)
from fordona_connect.learning.retry.policy import PolicyRow


def question(question_id: str, lesson_id: str, *, unit_id: str = "u1") -> ActiveQuestion:
    return ActiveQuestion(
        question_id=question_id,
        home_lesson_id=lesson_id,
        unit_id=unit_id,
        version="1",
        type="mcq",
        difficulty=2,
        level="EASY",
        domain_code="traffic",
        topic_tag=None,
        correct_option_key="a",
        option_keys=("a", "b", "c"),
        media_kinds=(),
        explanation={"sv-SE": "varför", "en-GB": "why"},
    )


def snapshot(
    layout: dict[str, list[str]],
    *,
    questions: list[ActiveQuestion] | None = None,
    challenges: list[SnapshotChallenge] | None = None,
    policy_rows: list[PolicyRow] | None = None,
) -> ContentSnapshot:
    """``layout`` maps unit ids (in order) to their lesson ids (in order)."""
    units = [
        SnapshotUnit(unit_id=unit_id, sort=sort, title={"sv-SE": unit_id})
        for sort, unit_id in enumerate(layout, start=1)
    ]
    lessons = [
        SnapshotLesson(
            lesson_id=lesson_id,
            unit_id=unit_id,
            sort=sort,
            title={"sv-SE": lesson_id},
            current_version="1",
            estimated_minutes=None,
        )
        for unit_id, lesson_ids in layout.items()
        for sort, lesson_id in enumerate(lesson_ids, start=1)
    ]
    return build_snapshot(
        1,
        units=units,
        lessons=lessons,
        questions=questions or [],
        challenges=challenges or [],
        policy_rows=policy_rows or [],
    )
