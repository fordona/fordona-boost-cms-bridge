"""Who may open which unit: subscribers everything, everyone the first unit.

Whether a learner is subscribed is the platform's (fordona-engine's) fact;
``SubscriptionSource`` is how this service asks. Phase L6 implements it against
the engine with a short cache; tests pass a fake.
"""

from typing import Protocol

from fordona_connect.learning.content.snapshot import ContentSnapshot


class SubscriptionSource(Protocol):
    async def is_subscribed(self, learner_id: str) -> bool: ...


class Entitlement:
    """One learner's entitlement, resolved once per request."""

    def __init__(self, snapshot: ContentSnapshot, *, subscribed: bool) -> None:
        self._free_unit_id = snapshot.units[0].unit_id if snapshot.units else None
        self.subscribed = subscribed

    def unit_entitled(self, unit_id: str) -> bool:
        return self.subscribed or unit_id == self._free_unit_id
