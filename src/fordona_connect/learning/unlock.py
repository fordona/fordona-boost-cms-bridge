"""Which lessons a learner may open (ported from the engine's UnlockService).

Walking units and lessons in order: completed lessons stay open for a retake;
the first not-completed lesson is CURRENT if its unit is entitled; everything
after it is LOCKED.
"""

from collections.abc import Callable, Set
from dataclasses import dataclass
from enum import StrEnum

from fordona_connect.learning.content.snapshot import ContentSnapshot


class UnlockStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CURRENT = "CURRENT"
    LOCKED = "LOCKED"


@dataclass(frozen=True, slots=True)
class LessonUnlock:
    lesson_id: str
    unit_id: str
    status: UnlockStatus


def resolve_unlocks(
    snapshot: ContentSnapshot,
    completed_lesson_ids: Set[str],
    unit_entitled: Callable[[str], bool],
) -> list[LessonUnlock]:
    results: list[LessonUnlock] = []
    decided = False
    for unit in snapshot.units:
        for lesson in snapshot.lessons_of(unit.unit_id):
            if lesson.lesson_id in completed_lesson_ids:
                status = UnlockStatus.COMPLETED
            elif not decided:
                decided = True
                status = (
                    UnlockStatus.CURRENT if unit_entitled(unit.unit_id) else UnlockStatus.LOCKED
                )
            else:
                status = UnlockStatus.LOCKED
            results.append(LessonUnlock(lesson.lesson_id, unit.unit_id, status))
    return results


def unlock_status(
    snapshot: ContentSnapshot,
    lesson_id: str,
    completed_lesson_ids: Set[str],
    unit_entitled: Callable[[str], bool],
) -> UnlockStatus | None:
    """The status of one lesson, or ``None`` if the lesson is not deliverable."""
    for unlock in resolve_unlocks(snapshot, completed_lesson_ids, unit_entitled):
        if unlock.lesson_id == lesson_id:
            return unlock.status
    return None
