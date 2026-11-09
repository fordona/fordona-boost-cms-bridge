"""Retry policy: settings for the retry phase, overridable per unit and lesson.

Resolution merges GLOBAL, then the unit's row, then the lesson's row; a key set
at a narrower scope wins. Keys missing everywhere fall back to the defaults
below (the engine's seeded values).
"""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Scope(StrEnum):
    GLOBAL = "GLOBAL"
    UNIT = "UNIT"
    LESSON = "LESSON"


# Which scopes may set each key.
ALLOWED_SCOPES: Mapping[str, frozenset[Scope]] = {
    "retry_enabled": frozenset(Scope),
    "extras_per_wrong": frozenset(Scope),
    "extras_min": frozenset(Scope),
    "extras_max": frozenset(Scope),
    "level_drop_allowed": frozenset(Scope),
    "similar_scope": frozenset({Scope.GLOBAL, Scope.UNIT}),
    "difficulty_level_map": frozenset({Scope.GLOBAL}),
}

_DEFAULT_LEVEL_MAP = {1: "EASY", 2: "EASY", 3: "MEDIUM", 4: "HARD", 5: "HARD"}


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    retry_enabled: bool = True
    extras_per_wrong: Decimal = Decimal("1.5")
    extras_min: int = 2
    extras_max: int = 5
    level_drop_allowed: int = 1
    similar_scope: str = "REACHED"
    difficulty_level_map: Mapping[int, str] = field(
        default_factory=lambda: dict(_DEFAULT_LEVEL_MAP)
    )

    def to_json(self) -> dict[str, Any]:
        """The shape stored as an attempt's ``policy_snapshot``."""
        data = asdict(self)
        data["extras_per_wrong"] = str(self.extras_per_wrong)
        data["difficulty_level_map"] = {
            str(level): name for level, name in self.difficulty_level_map.items()
        }
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "RetryPolicy":
        return _from_values(data, cls())


@dataclass(frozen=True, slots=True)
class PolicyRow:
    scope: str
    scope_id: str
    key_values: Mapping[str, Any]


def resolve_policy(
    rows: Iterable[PolicyRow], unit_id: str | None, lesson_id: str | None
) -> RetryPolicy:
    by_scope = {(row.scope, row.scope_id): row.key_values for row in rows}
    merged: dict[str, Any] = {}
    for scope, scope_id in (
        (Scope.GLOBAL, "GLOBAL"),
        (Scope.UNIT, unit_id),
        (Scope.LESSON, lesson_id),
    ):
        if scope_id is None:
            continue
        values = by_scope.get((scope.value, scope_id), {})
        merged.update(
            {key: value for key, value in values.items() if scope in ALLOWED_SCOPES.get(key, ())}
        )
    return _from_values(merged, RetryPolicy())


def _from_values(values: Mapping[str, Any], base: RetryPolicy) -> RetryPolicy:
    level_map = values.get("difficulty_level_map")
    return RetryPolicy(
        retry_enabled=bool(values.get("retry_enabled", base.retry_enabled)),
        extras_per_wrong=Decimal(str(values.get("extras_per_wrong", base.extras_per_wrong))),
        extras_min=int(values.get("extras_min", base.extras_min)),
        extras_max=int(values.get("extras_max", base.extras_max)),
        level_drop_allowed=int(values.get("level_drop_allowed", base.level_drop_allowed)),
        similar_scope=str(values.get("similar_scope", base.similar_scope)),
        difficulty_level_map=(
            {int(level): str(name) for level, name in level_map.items()}
            if isinstance(level_map, Mapping)
            else dict(base.difficulty_level_map)
        ),
    )
