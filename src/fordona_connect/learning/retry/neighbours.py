"""Similar questions by metadata (ported from the engine's NeighbourRanker).

Two questions are related when they share a lesson, unit, topic or subject; the
closer the relation, the higher the score. Each question keeps its 20 best
neighbours, ties broken by closeness in difficulty, then by id.
"""

from collections.abc import Sequence
from decimal import Decimal

from fordona_connect.learning.content.snapshot import ActiveQuestion, Neighbour

MAX_NEIGHBOURS = 20
PROVIDER = "metadata"


def _same(a: str | None, b: str | None) -> bool:
    return a is not None and a == b


def relation_score(seed: ActiveQuestion, candidate: ActiveQuestion) -> float | None:
    same_lesson = _same(seed.home_lesson_id, candidate.home_lesson_id)
    same_unit = _same(seed.unit_id, candidate.unit_id)
    same_topic = _same(seed.topic_tag, candidate.topic_tag)
    same_domain = _same(seed.domain_code, candidate.domain_code)
    if same_lesson and same_topic:
        return 1.0
    if same_unit and same_topic:
        return 0.8
    if same_lesson and same_domain:
        return 0.6
    if same_topic:
        return 0.5
    if same_domain and same_unit:
        return 0.4
    return None


def rank_neighbours(seed: ActiveQuestion, bank: Sequence[ActiveQuestion]) -> list[Neighbour]:
    scored: list[tuple[float, ActiveQuestion]] = []
    for candidate in bank:
        if candidate.question_id == seed.question_id:
            continue
        score = relation_score(seed, candidate)
        if score is not None:
            scored.append((score, candidate))
    scored.sort(
        key=lambda pair: (
            -pair[0],
            abs(pair[1].difficulty - seed.difficulty),
            pair[1].question_id,
        )
    )
    return [
        Neighbour(seed.question_id, rank, candidate.question_id, Decimal(str(score)), PROVIDER)
        for rank, (score, candidate) in enumerate(scored[:MAX_NEIGHBOURS], start=1)
    ]


def build_neighbours(bank: Sequence[ActiveQuestion]) -> list[Neighbour]:
    return [neighbour for seed in bank for neighbour in rank_neighbours(seed, bank)]
