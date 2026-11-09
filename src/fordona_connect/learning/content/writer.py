"""Writing a ``ReadModel`` into the content tables, changing only what differs."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, cast

from sqlalchemy import Table, delete, func, insert, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fordona_connect.core.logging import get_logger
from fordona_connect.db.models import Base
from fordona_connect.learning.content.models import (
    ContentChallenge,
    ContentChallengeLesson,
    ContentChallengeQuestion,
    ContentJourney,
    ContentLesson,
    ContentMilestone,
    ContentMockExam,
    ContentMockExamQuestion,
    ContentQuestion,
    ContentQuestionRevision,
    ContentRelease,
    ContentUnit,
)
from fordona_connect.learning.content.read_model import ReadModel, Row
from fordona_connect.learning.content.snapshot import load_active_questions
from fordona_connect.learning.content.validation import ExclusionReason
from fordona_connect.learning.retry.models import QuestionNeighbour
from fordona_connect.learning.retry.neighbours import build_neighbours

log = get_logger(__name__)


class _OnRemoved(Enum):
    """What happens to a stored row Boost no longer publishes."""

    HIDE = "hide"  # units and lessons: kept for history, never shown
    EXCLUDE = "exclude"  # questions: kept (attempts refer to them), never delivered
    DELETE = "delete"  # catalogues and memberships: nothing refers to them


@dataclass(frozen=True, slots=True)
class WriteResult:
    changed: bool
    release_id: int
    new_revisions: int


async def stored_correct_keys(session: AsyncSession) -> dict[tuple[str, str], str]:
    """The answer key of every stored revision, by ``(question_id, version)``."""
    rows = await session.execute(
        select(
            ContentQuestionRevision.question_id,
            ContentQuestionRevision.version,
            ContentQuestionRevision.correct_option_key,
        )
    )
    return {(question_id, version): key for question_id, version, key in rows}


async def write_read_model(session: AsyncSession, model: ReadModel, now: datetime) -> WriteResult:
    """Apply ``model`` inside the caller's transaction."""
    tables: Sequence[tuple[type[Base], list[Row], _OnRemoved]] = (
        (ContentUnit, model.units, _OnRemoved.HIDE),
        (ContentLesson, model.lessons, _OnRemoved.HIDE),
        (ContentQuestion, model.questions, _OnRemoved.EXCLUDE),
        (ContentMockExam, model.mock_exams, _OnRemoved.DELETE),
        (ContentMockExamQuestion, model.mock_exam_questions, _OnRemoved.DELETE),
        (ContentJourney, model.journeys, _OnRemoved.DELETE),
        (ContentMilestone, model.milestones, _OnRemoved.DELETE),
        (ContentChallenge, model.challenges, _OnRemoved.DELETE),
        (ContentChallengeLesson, model.challenge_lessons, _OnRemoved.DELETE),
        (ContentChallengeQuestion, model.challenge_questions, _OnRemoved.DELETE),
    )

    changed = False
    removed: list[tuple[type[Base], list[Row], _OnRemoved]] = []
    # Parents before children for inserts and updates ...
    for table, rows, on_removed in tables:
        upserted, absent = await _upsert(session, table, rows)
        changed |= upserted
        removed.append((table, absent, on_removed))
    # ... and children before parents for removals.
    for table, absent, on_removed in reversed(removed):
        changed |= await _remove(session, table, absent, on_removed)

    latest = await session.scalar(select(func.max(ContentRelease.release_id)))
    if latest is not None and not changed and not model.new_revisions:
        return WriteResult(changed=False, release_id=latest, new_revisions=0)

    release_id = await session.scalar(
        insert(ContentRelease).values(activated_at=now).returning(ContentRelease.release_id)
    )
    assert release_id is not None
    if model.new_revisions:
        # Another instance may have stored the same immutable revision first.
        await session.execute(
            pg_insert(ContentQuestionRevision)
            .values([{**row, "release_id": release_id} for row in model.new_revisions])
            .on_conflict_do_nothing()
        )
    neighbours = build_neighbours(await load_active_questions(session))
    await session.execute(delete(QuestionNeighbour))
    if neighbours:
        await session.execute(
            insert(QuestionNeighbour),
            [
                {
                    "question_id": n.question_id,
                    "rank": n.rank,
                    "neighbour_id": n.neighbour_id,
                    "score": n.score,
                    "provider": n.provider,
                    "release_id": release_id,
                }
                for n in neighbours
            ],
        )
    log.info(
        "content_release_created",
        release_id=release_id,
        new_revisions=len(model.new_revisions),
    )
    return WriteResult(changed=True, release_id=release_id, new_revisions=len(model.new_revisions))


def _table(table: type[Base]) -> Table:
    return cast(Table, table.__table__)


def _primary_key(table: type[Base]) -> tuple[str, ...]:
    return tuple(column.name for column in _table(table).primary_key.columns)


def _key(row: Row, pk: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[name] for name in pk)


async def _upsert(
    session: AsyncSession, table: type[Base], rows: list[Row]
) -> tuple[bool, list[Row]]:
    """Insert new rows and update differing ones; return the stored rows not in ``rows``."""
    pk = _primary_key(table)
    columns = [column.name for column in _table(table).columns]
    stored = {
        _key(dict(row), pk): dict(row)
        for row in (await session.execute(select(*_table(table).columns))).mappings()
    }
    desired = {_key(row, pk): row for row in rows}

    to_insert = [row for key, row in desired.items() if key not in stored]
    to_update = [
        row
        for key, row in desired.items()
        if key in stored and any(stored[key][name] != row[name] for name in row)
    ]
    if to_insert:
        await session.execute(insert(table), to_insert)
    for row in to_update:
        values = {name: row[name] for name in columns if name in row and name not in pk}
        await session.execute(
            update(table)
            .where(*(_table(table).c[name] == row[name] for name in pk))
            .values(**values)
        )
    absent = [dict(row) for key, row in stored.items() if key not in desired]
    return bool(to_insert or to_update), absent


async def _remove(
    session: AsyncSession, table: type[Base], absent: list[Row], on_removed: _OnRemoved
) -> bool:
    if not absent:
        return False
    pk = _primary_key(table)
    keys = [_key(row, pk) for row in absent]
    key_columns = tuple_(*(_table(table).c[name] for name in pk))

    if on_removed is _OnRemoved.DELETE:
        await session.execute(delete(table).where(key_columns.in_(keys)))
        return True

    if on_removed is _OnRemoved.HIDE:
        pending = [key for key, row in zip(keys, absent, strict=True) if row["status"] != "HIDDEN"]
        values: dict[str, Any] = {"status": "HIDDEN"}
    else:
        reason = ExclusionReason.REMOVED.value
        pending = [
            key
            for key, row in zip(keys, absent, strict=True)
            if (row["status"], row["exclusion_reason"]) != ("EXCLUDED", reason)
        ]
        values = {"status": "EXCLUDED", "exclusion_reason": reason}
    if not pending:
        return False
    await session.execute(update(table).where(key_columns.in_(pending)).values(**values))
    log.info("content_removed_from_boost", table=table.__tablename__, count=len(pending))
    return True
