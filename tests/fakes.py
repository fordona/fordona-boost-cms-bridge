"""In-memory doubles shared by unit and API tests."""

import asyncio
from datetime import datetime
from typing import Any

from boost_bridge.clients.boost.client import BoostRequest
from boost_bridge.db.snapshot_repository import Snapshot


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.current = start

    def now(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


class FakeFetcher:
    """Scripted stand-in for BoostClient.fetch_raw.

    ``responses`` maps a request path to a payload or an exception instance.
    Set ``gate`` to an ``asyncio.Event`` to hold every call until it is set.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses: dict[str, Any] = responses or {}
        self.calls: list[BoostRequest[Any]] = []
        self.gate: asyncio.Event | None = None

    async def fetch_raw(self, request: BoostRequest[Any]) -> Any:
        self.calls.append(request)
        if self.gate is not None:
            await self.gate.wait()
        result = self.responses[request.path]
        if isinstance(result, BaseException):
            raise result
        return result

    def calls_to(self, path: str) -> int:
        return sum(1 for call in self.calls if call.path == path)


class InMemorySnapshots:
    def __init__(self) -> None:
        self.rows: dict[str, Snapshot] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("database down")

    async def get(self, cache_key: str) -> Snapshot | None:
        self._check()
        return self.rows.get(cache_key)

    async def upsert(
        self, cache_key: str, *, resource: str, locale: str, payload: Any, fetched_at: datetime
    ) -> None:
        self._check()
        self.rows[cache_key] = Snapshot(payload=payload, fetched_at=fetched_at)

    async def delete(self, cache_key: str) -> None:
        self._check()
        self.rows.pop(cache_key, None)
