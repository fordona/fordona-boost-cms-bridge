"""Liveness and readiness probes (unauthenticated).

* ``/health/live``: the process is serving HTTP. It never touches a dependency,
  so a dependency outage cannot get healthy containers restarted.
* ``/health/ready``: Postgres and Redis respond. Each check runs concurrently
  with a 1s timeout. Any failure returns 503 with every component's status in
  the body.

Boost is deliberately not checked. The service keeps serving last-known-good
snapshots through a Boost outage, and pulling every replica out of rotation
would make that outage worse (design doc §9).
"""

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from boost_bridge.api.deps import get_services
from boost_bridge.container import ReadinessCheck, Services
from boost_bridge.core.logging import get_logger
from boost_bridge.schemas.health import ComponentStatus, Liveness, Readiness

router = APIRouter(prefix="/health", tags=["health"])
log = get_logger(__name__)

_CHECK_TIMEOUT_SECONDS = 1.0


@router.get("/live", response_model=Liveness, summary="Liveness probe")
async def live() -> Liveness:
    return Liveness(status="ok")


async def _run(name: str, check: ReadinessCheck) -> ComponentStatus:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        # Only the exception type is returned: messages can contain hosts or DSNs.
        error = "Timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
        log.warning("readiness_check_failed", component=name, error=repr(exc))
        return ComponentStatus(status="down", latency_ms=elapsed, error=error)
    return ComponentStatus(status="up", latency_ms=round((time.perf_counter() - started) * 1000, 2))


@router.get(
    "/ready",
    response_model=Readiness,
    summary="Readiness probe (Postgres + Redis)",
    responses={503: {"model": Readiness, "description": "A dependency is unavailable."}},
)
async def ready(
    response: Response, services: Annotated[Services, Depends(get_services)]
) -> Readiness:
    names = list(services.readiness_checks)
    results = await asyncio.gather(*(_run(name, services.readiness_checks[name]) for name in names))
    components = dict(zip(names, results, strict=True))
    healthy = all(c.status == "up" for c in components.values())
    response.headers["Cache-Control"] = "no-store"
    if not healthy:
        response.status_code = 503
    return Readiness(status="ready" if healthy else "not_ready", components=components)
