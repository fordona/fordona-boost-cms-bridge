from typing import Literal

from boost_bridge.schemas.common import APIModel


class Liveness(APIModel):
    status: Literal["ok"]


class ComponentStatus(APIModel):
    status: Literal["up", "down"]
    latency_ms: float
    error: str | None = None


class Readiness(APIModel):
    status: Literal["ready", "not_ready"]
    components: dict[str, ComponentStatus]
