"""Injectable clock so TTL logic can be tested without sleeping."""

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Seconds since the epoch."""
        ...


class SystemClock:
    def now(self) -> float:
        return time.time()
