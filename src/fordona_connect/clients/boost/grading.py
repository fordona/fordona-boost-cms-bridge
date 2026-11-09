"""Boost's **grading** API: the answer key and explanation of one question revision.

Kept apart from ``models.py`` on purpose. Only the content sync
(``learning.content.sync``) imports this module; nothing that builds a public
response may. A published revision never changes, so each one is fetched once
and stored.
"""

from typing import Any

from pydantic import Field, field_validator

from fordona_connect.clients.boost.models import BoostModel


class GradingShared(BoostModel):
    correct_option_id: str | None = None


class GradingTranslation(BoostModel):
    # A block list or plain/HTML text, depending on the question; stored as-is.
    explanation: Any = None


class BoostGradingRevision(BoostModel):
    id: str
    version: str | None = None
    shared: GradingShared = Field(default_factory=GradingShared)
    translations: dict[str, GradingTranslation | None] = Field(default_factory=dict)

    @field_validator("translations", mode="before")
    @classmethod
    def _null_is_empty(cls, value: Any) -> Any:
        return {} if value is None else value

    @property
    def correct_option_id(self) -> str | None:
        return self.shared.correct_option_id

    def explanations(self) -> dict[str, Any]:
        """Explanation per locale, leaving out locales that have none."""
        return {
            locale: translation.explanation
            for locale, translation in self.translations.items()
            if translation is not None and translation.explanation is not None
        }
