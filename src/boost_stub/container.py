"""Composition root and the background change-feed poll (plan §4.5)."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import httpx

from boost_stub.auth import TokenProbeCache
from boost_stub.changes import ChangeTracker
from boost_stub.config import StubSettings
from boost_stub.data import GeneratedData, load
from boost_stub.logging import get_logger
from boost_stub.upstream import UpstreamClient

log = get_logger(__name__)


class DataStore:
    """A reloadable holder for the generated files (plan §4.5's template generator
    output can change while the stub is running; the stub never writes them)."""

    def __init__(self, settings: StubSettings) -> None:
        self._settings = settings
        self.current: GeneratedData = load(settings.stub_data_dir)

    def reload(self) -> None:
        self.current = load(self._settings.stub_data_dir)


ServicesFactory = Callable[[StubSettings], AbstractAsyncContextManager["StubServices"]]


@dataclass(slots=True)
class StubServices:
    settings: StubSettings
    http: httpx.AsyncClient
    upstream: UpstreamClient
    tracker: ChangeTracker
    data: DataStore
    probe_cache: TokenProbeCache


def create_http_client(settings: StubSettings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=str(settings.stub_upstream_boost_url).rstrip("/"),
        timeout=httpx.Timeout(settings.stub_upstream_timeout_seconds),
        headers={"Accept": "application/json", "User-Agent": "fordona-boost-stub/0.1"},
        follow_redirects=False,
    )


async def poll_once(services: StubServices, *, token: str, now: float) -> int:
    """One change-feed poll cycle: list upstream Boost plus the generated files,
    diff against the last snapshot, write change rows. Returns rows written."""
    upstream = services.upstream
    written = 0
    modules = await upstream.list_all("/v1/delivery/modules", token, {})
    module_versions = {str(m["id"]): str(m.get("version", "")) for m in modules}
    written += services.tracker.record("MODULE", module_versions, now)

    lessons = await upstream.list_all("/v1/delivery/lessons", token, {})
    lesson_versions = {str(le["id"]): str(le.get("version", "")) for le in lessons}
    written += services.tracker.record("LESSON", lesson_versions, now)

    questions = await upstream.list_all("/v1/delivery/questions", token, {})
    question_versions = {str(q["id"]): str(q.get("version", "")) for q in questions}
    services.data.reload()
    for question_id, record in services.data.current.synthetic_questions.items():
        question_versions[question_id] = str(record["version"])
    written += services.tracker.record("QUESTION", question_versions, now)

    template_versions = {
        template_id: str(template["version"])
        for template_id, template in services.data.current.templates.items()
    }
    written += services.tracker.record("QUESTION_TEMPLATE", template_versions, now)

    services.tracker.purge(now, retention_seconds=services.settings.stub_retention_seconds)
    return written


async def _poll_loop(services: StubServices) -> None:
    token = services.settings.stub_poll_token.get_secret_value()
    if not token:
        log.warning("stub_poll_disabled", reason="STUB_POLL_TOKEN is not set")
        return
    while True:
        try:
            written = await poll_once(services, token=token, now=time.time())
            if written:
                log.info("stub_poll_recorded_changes", count=written)
        except Exception:
            log.exception("stub_poll_failed")
        await asyncio.sleep(services.settings.stub_poll_seconds)


@asynccontextmanager
async def build_services(settings: StubSettings) -> AsyncIterator[StubServices]:
    http = create_http_client(settings)
    tracker = ChangeTracker(str(settings.stub_sqlite_path))
    services = StubServices(
        settings=settings,
        http=http,
        upstream=UpstreamClient(http),
        tracker=tracker,
        data=DataStore(settings),
        probe_cache=TokenProbeCache(),
    )
    poll_task = asyncio.create_task(_poll_loop(services))
    try:
        yield services
    finally:
        poll_task.cancel()
        await http.aclose()
        tracker.close()
