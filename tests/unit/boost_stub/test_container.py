"""The composition root's one real piece of logic: a poll cycle (plan §4.5)."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from boost_stub.auth import TokenProbeCache
from boost_stub.changes import ChangeTracker
from boost_stub.config import StubSettings
from boost_stub.container import DataStore, StubServices, poll_once
from boost_stub.upstream import UpstreamClient

BASE = "https://boost.test"


def _page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "total": len(items), "page": 1, "pageSize": 250, "asOf": "x"}


@pytest.fixture
def services(tmp_path: Path) -> StubServices:
    http = httpx.AsyncClient(base_url=BASE)
    settings = StubSettings(
        stub_upstream_boost_url=BASE,
        stub_data_dir=tmp_path,
        stub_sqlite_path=":memory:",
    )
    return StubServices(
        settings=settings,
        http=http,
        upstream=UpstreamClient(http),
        tracker=ChangeTracker(":memory:"),
        data=DataStore(settings),
        probe_cache=TokenProbeCache(),
    )


@respx.mock
async def test_poll_once_records_every_entity_kind(services: StubServices) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([{"id": "1", "version": "1"}]))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(json=_page([{"id": "10", "version": "1"}]))
    respx.get(f"{BASE}/v1/delivery/questions").respond(json=_page([{"id": "100", "version": "1"}]))

    written = await poll_once(services, token="t", now=1000.0)

    assert written == 3  # one MODULE, one LESSON, one QUESTION row
    page = services.tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)
    assert {r.entity_type for r in page.items} == {"MODULE", "LESSON", "QUESTION"}


@respx.mock
async def test_poll_once_reloads_generated_data_and_tracks_templates(
    services: StubServices, tmp_path: Path
) -> None:
    from scripts.stub_data.generator import Lesson, Question, generate, render

    output = generate([Lesson("10", "1")], [Question("100", "10", "3", 2)])
    (tmp_path / "templates.json").write_bytes(render(output.templates))
    (tmp_path / "synthetic.json").write_bytes(render(output.synthetic))

    respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([]))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(json=_page([]))
    respx.get(f"{BASE}/v1/delivery/questions").respond(json=_page([]))

    await poll_once(services, token="t", now=1000.0)

    page = services.tracker.feed(0, 100, now=1000.0, visibility_lag_seconds=0)
    types = {r.entity_type for r in page.items}
    assert "QUESTION_TEMPLATE" in types
    # the synthetic questions used to top up the thin lesson are tracked as QUESTION too
    assert any(r.entity_type == "QUESTION" and r.id != "100" for r in page.items)
    assert services.data.current.generation == output.templates["generation"]


@respx.mock
async def test_second_poll_with_no_change_writes_nothing(services: StubServices) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([{"id": "1", "version": "1"}]))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(json=_page([]))
    respx.get(f"{BASE}/v1/delivery/questions").respond(json=_page([]))

    await poll_once(services, token="t", now=1000.0)
    written = await poll_once(services, token="t", now=1001.0)

    assert written == 0
