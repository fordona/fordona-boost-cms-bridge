"""Production wiring builds and tears down cleanly.

Nothing connects at build time: Redis, the engine and httpx all connect
lazily, so this runs without any infrastructure.
"""

from boost_bridge.container import build_services
from boost_bridge.services.content_service import ContentService
from tests.conftest import make_settings


async def test_build_services_with_auth() -> None:
    async with build_services(make_settings()) as services:
        assert isinstance(services.content, ContentService)
        assert services.verifier is not None
        assert set(services.readiness_checks) == {"database", "redis"}


async def test_build_services_without_auth_locally() -> None:
    async with build_services(make_settings(auth_enabled=False)) as services:
        assert services.verifier is None
