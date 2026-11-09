"""Composing the retry phase (ported from the engine's RetryComposer).

Every wrongly answered lesson item comes back once (REPEAT). On top, the policy
asks for ``ceil(extras_per_wrong * wrong)`` similar questions (SIMILAR), clamped
to ``[extras_min, extras_max]``, drawn round-robin from each wrong item's
neighbours. A similar question must:

(a) still be active, in a visible lesson;
(b) be at the wrong item's level or one level easier;
(c) not already be in this attempt;
(d) be in a unit the learner is entitled to (never configurable);
(e) with ``similar_scope`` other than ALL, be from this lesson or one already completed;
(f) on the first pass, not have been seen by the learner before.

Image-based questions get no similar extras: no image is meaningfully "similar".
"""

import math
import random
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fordona_connect.learning.content.snapshot import ActiveQuestion, ContentSnapshot
from fordona_connect.learning.retry.policy import RetryPolicy

_LEVELS = ("EASY", "MEDIUM", "HARD")
_IMAGE = "image"


@dataclass(frozen=True, slots=True)
class LessonItem:
    """The parts of an answered lesson-phase item the composer needs."""

    seq: int
    question_id: str
    version: str
    is_correct: bool | None
    option_order: Sequence[str]
    domain_code: str
    topic_tag: str | None
    difficulty: int
    level: str


@dataclass(slots=True)
class RetryComposition:
    items: list[dict[str, Any]] = field(default_factory=list)
    extras_short: int = 0


def extras_for(policy: RetryPolicy, wrong: int) -> int:
    if wrong <= 0:
        return 0
    raw = math.ceil(policy.extras_per_wrong * Decimal(wrong))
    return max(policy.extras_min, min(policy.extras_max, raw))


def _one_level_down(level: str) -> str:
    index = _LEVELS.index(level)
    return _LEVELS[max(0, index - 1)]


def compose_retry(
    snapshot: ContentSnapshot,
    lesson_items: Sequence[LessonItem],
    *,
    lesson_id: str,
    completed_lesson_ids: Set[str],
    seen_question_ids: Set[str],
    unit_entitled: Callable[[str], bool],
    policy: RetryPolicy,
    seed: int,
) -> RetryComposition:
    wrong = sorted((item for item in lesson_items if not item.is_correct), key=lambda i: i.seq)
    target = extras_for(policy, len(wrong))
    excluded = {item.question_id for item in lesson_items}
    picks: list[tuple[LessonItem, ActiveQuestion, Any]] = []

    def passes(
        seed_item: LessonItem, candidate: ActiveQuestion | None, require_unseen: bool
    ) -> bool:
        if candidate is None or candidate.home_lesson_id is None:
            return False
        if snapshot.lesson(candidate.home_lesson_id) is None:
            return False
        if candidate.level not in (seed_item.level, _one_level_down(seed_item.level)):
            return False
        if candidate.unit_id is None or not unit_entitled(candidate.unit_id):
            return False
        if policy.similar_scope != "ALL" and not (
            candidate.home_lesson_id == lesson_id
            or candidate.home_lesson_id in completed_lesson_ids
        ):
            return False
        return not (require_unseen and candidate.question_id in seen_question_ids)

    def run_pass(require_unseen: bool) -> None:
        cursors = [0] * len(wrong)
        progressed = True
        while len(picks) < target and progressed:
            progressed = False
            for index, seed_item in enumerate(wrong):
                if len(picks) >= target:
                    break
                seed_question = snapshot.question(seed_item.question_id)
                if seed_question is not None and _IMAGE in seed_question.media_kinds:
                    continue
                neighbours = snapshot.neighbours_of(seed_item.question_id)
                cursor = cursors[index]
                while cursor < len(neighbours):
                    neighbour = neighbours[cursor]
                    cursor += 1
                    if neighbour.neighbour_id in excluded:
                        continue
                    candidate = snapshot.question(neighbour.neighbour_id)
                    if not passes(seed_item, candidate, require_unseen):
                        continue
                    assert candidate is not None
                    picks.append((seed_item, candidate, neighbour))
                    excluded.add(candidate.question_id)
                    progressed = True
                    break
                cursors[index] = cursor

    if target > 0 and wrong:
        run_pass(require_unseen=True)
        if len(picks) < target:
            run_pass(require_unseen=False)

    rng = random.Random(seed)  # noqa: S311 - deterministic per attempt, not a secret

    def shuffled(keys: Sequence[str]) -> list[str]:
        order = list(keys)
        rng.shuffle(order)
        return order

    items: list[dict[str, Any]] = [
        {
            "phase": "RETRY",
            "item_source": "REPEAT",
            "question_id": item.question_id,
            "version": item.version,
            "option_order": shuffled(item.option_order),
            "domain_code": item.domain_code,
            "topic_tag": item.topic_tag,
            "difficulty": item.difficulty,
            "level": item.level,
        }
        for item in wrong
    ]
    items.extend(
        {
            "phase": "RETRY",
            "item_source": "SIMILAR",
            "question_id": candidate.question_id,
            "version": candidate.version,
            "origin_question_id": seed_item.question_id,
            "option_order": shuffled(candidate.option_keys),
            "domain_code": candidate.domain_code,
            "topic_tag": candidate.topic_tag,
            "difficulty": candidate.difficulty,
            "level": candidate.level,
            "provider": neighbour.provider,
            "similarity_score": neighbour.score,
        }
        for seed_item, candidate, neighbour in picks
    )
    rng.shuffle(items)
    return RetryComposition(items=items, extras_short=target - len(picks))
