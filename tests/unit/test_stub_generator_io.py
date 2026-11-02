"""The generator's Boost reader and its file round trip (tracker P2.T2)."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from scripts.generate_stub_templates import SYNTHETIC_FILE, TEMPLATES_FILE, run
from scripts.stub_data import boost_source
from scripts.stub_data.boost_source import BoostSourceError
from scripts.stub_data.generator import Lesson, Question

BASE = "https://boost.test"


def _page(items: list[dict[str, Any]], *, total: int, page: int = 1) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": 250,
        "asOf": "2026-11-02T00:00:00Z",
    }


@pytest.fixture
def http() -> httpx.Client:
    return httpx.Client(base_url=BASE)


@respx.mock
def test_fetch_reads_nested_and_flat_items(http: httpx.Client) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([{"id": "1"}], total=1))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(
        json=_page(
            [
                {"id": "10", "shared": {"moduleId": "1"}},
                {"id": "11", "moduleId": 1},  # flat, numeric module id
                {"id": "12", "shared": {"moduleId": "2"}},  # module not published
            ],
            total=3,
        )
    )
    respx.get(f"{BASE}/v1/delivery/questions").respond(
        json=_page(
            [
                {"id": "100", "shared": {"lessonId": "10", "subjectId": "3", "difficulty": 2}},
                {"id": "101", "lessonId": 11, "subjectId": None, "difficulty": "4"},
            ],
            total=2,
        )
    )

    lessons, questions = boost_source.fetch(http)

    assert lessons == [Lesson("10", "1"), Lesson("11", "1")]
    assert questions == [
        Question("100", "10", "3", 2),
        Question("101", "11", None, None),  # a non-integer difficulty is not trusted
    ]


@respx.mock
def test_fetch_pages_through_large_lists(http: httpx.Client) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([{"id": "1"}], total=1))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(
        json=_page([{"id": "10", "shared": {"moduleId": "1"}}], total=1)
    )
    route = respx.get(f"{BASE}/v1/delivery/questions")
    route.side_effect = lambda request: httpx.Response(
        200,
        json=_page(
            [{"id": str(int(request.url.params["page"]) * 1000), "shared": {"lessonId": "10"}}],
            total=501,
            page=int(request.url.params["page"]),
        ),
    )

    _, questions = boost_source.fetch(http)

    assert [q.id for q in questions] == ["1000", "2000", "3000"]
    assert [c.request.url.params["pageSize"] for c in route.calls] == ["250"] * 3


@respx.mock
def test_fetch_asks_for_published_swedish_content(http: httpx.Client) -> None:
    modules = respx.get(f"{BASE}/v1/delivery/modules").respond(json=_page([], total=0))
    respx.get(f"{BASE}/v1/delivery/lessons").respond(json=_page([], total=0))
    respx.get(f"{BASE}/v1/delivery/questions").respond(json=_page([], total=0))

    boost_source.fetch(http)

    assert modules.calls.last.request.url.params["locale"] == "sv-SE"


@respx.mock
def test_fetch_fails_loudly_on_an_upstream_error(http: httpx.Client) -> None:
    respx.get(f"{BASE}/v1/delivery/modules").respond(401, json={"code": "authentication_required"})

    with pytest.raises(BoostSourceError, match="401"):
        boost_source.fetch(http)


def _source() -> tuple[list[Lesson], list[Question]]:
    lessons = [Lesson("10", "1"), Lesson("11", "1")]
    questions = [Question(str(100 + n), "10", "3", n % 5 + 1) for n in range(17)]
    return lessons, questions


def test_run_writes_both_files(tmp_path: Path) -> None:
    run(_source, tmp_path)

    assert (tmp_path / TEMPLATES_FILE).read_bytes().endswith(b"\n")
    assert (tmp_path / SYNTHETIC_FILE).exists()


def test_rerun_produces_no_diff(tmp_path: Path) -> None:
    run(_source, tmp_path)
    before = {name: (tmp_path / name).read_bytes() for name in (TEMPLATES_FILE, SYNTHETIC_FILE)}

    output = run(_source, tmp_path)

    after = {name: (tmp_path / name).read_bytes() for name in (TEMPLATES_FILE, SYNTHETIC_FILE)}
    assert after == before
    assert output.report.changed is False
