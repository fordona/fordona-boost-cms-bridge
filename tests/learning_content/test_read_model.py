"""Fetching a catalogue from (fake) Boost and building the desired content rows."""

import httpx
import pytest
import respx

from fordona_connect.clients.boost.client import BoostClient
from fordona_connect.learning.content.catalogue import Catalogue, fetch_catalogue, fetch_grading
from fordona_connect.learning.content.read_model import (
    ReadModel,
    build_read_model,
    refs_needing_grading,
)
from tests.learning_content.boost_world import (
    BASE,
    LOCALES,
    BoostWorld,
    FakeLesson,
    FakeQuestion,
)


@pytest.fixture
async def client() -> BoostClient:
    async with httpx.AsyncClient(base_url=BASE) as http:
        yield BoostClient(  # type: ignore[misc]
            http, token="svc-token", grading_token="grading-token", max_retries=0
        )


def world() -> BoostWorld:
    return BoostWorld(
        modules=["m1", "m2"],
        lessons=[
            FakeLesson("l1", "m1"),
            FakeLesson("l2", "m1", theory=False),
            FakeLesson("l3", "m2"),
            FakeLesson("orphan", "gone"),
        ],
        questions=[
            FakeQuestion("q1", "l1"),
            FakeQuestion("q2", "l2"),
            FakeQuestion("q3", "l3", correct="z"),
            FakeQuestion("q4", "l3", locales=("sv-SE",)),
        ],
        mock_exams=[
            {
                "id": "e1",
                "version": "3",
                "questionCount": 60,
                "questionIds": ["q1", "q2", "q1"],
                "complete": False,
            }
        ],
        journeys=[
            {
                "id": "j1",
                "title": "B Licence",
                "milestones": [
                    {
                        "id": "ms1",
                        "title": "Learn to drive",
                        "challenges": [
                            {"id": "c1", "title": "Gear", "chapterIds": ["l1"], "questionIds": []},
                            {
                                "id": "c2",
                                "title": "Safety",
                                "goal": "Stay safe",
                                "chapterIds": ["l3"],
                                "questionIds": ["q3", "q1"],
                            },
                        ],
                    }
                ],
            }
        ],
    )


async def build(client: BoostClient, boost: BoostWorld) -> tuple[Catalogue, ReadModel]:
    with respx.mock(assert_all_called=False) as router:
        boost.mount(router)
        catalogue = await fetch_catalogue(client, LOCALES, default_locale="sv-SE", page_size=2)
        grading = await fetch_grading(client, refs_needing_grading(catalogue, {}))
    return catalogue, build_read_model(catalogue, stored_correct_keys={}, grading=grading)


async def test_paging_collects_every_item(client: BoostClient) -> None:
    catalogue, _ = await build(client, world())

    assert [q.id for q in catalogue.default.questions] == ["q1", "q2", "q3", "q4"]
    assert set(catalogue.by_locale) == set(LOCALES)


async def test_units_and_lessons_keep_boost_order_and_titles(client: BoostClient) -> None:
    _, model = await build(client, world())

    assert [(u["unit_id"], u["sort"]) for u in model.units] == [("m1", 1), ("m2", 2)]
    assert model.units[0]["title"] == {"sv-SE": "m1 sv-SE", "en-GB": "m1 en-GB"}
    # Sort restarts per unit; a lesson whose unit Boost does not publish is skipped.
    assert [(row["lesson_id"], row["unit_id"], row["sort"]) for row in model.lessons] == [
        ("l1", "m1", 1),
        ("l2", "m1", 2),
        ("l3", "m2", 1),
    ]


async def test_questions_are_validated_against_the_answer_key(client: BoostClient) -> None:
    _, model = await build(client, world())

    status = {q["question_id"]: (q["status"], q["exclusion_reason"]) for q in model.questions}
    assert status == {
        "q1": ("ACTIVE", None),
        "q2": ("ACTIVE", None),
        "q3": ("EXCLUDED", "CORRECT_KEY_NOT_AMONG_OPTIONS"),
        "q4": ("EXCLUDED", "LOCALE_MISSING"),
    }


async def test_only_valid_new_revisions_are_recorded_with_their_key(client: BoostClient) -> None:
    _, model = await build(client, world())

    revisions = {r["question_id"]: r for r in model.new_revisions}
    assert set(revisions) == {"q1", "q2"}
    assert revisions["q1"]["correct_option_key"] == "a"
    assert revisions["q1"]["option_keys"] == ["a", "b", "c"]
    assert revisions["q1"]["level"] == "EASY"
    assert revisions["q1"]["explanation"] == {"sv-SE": "why (sv-SE)", "en-GB": "why (en-GB)"}


async def test_a_lesson_is_visible_with_theory_and_an_active_question(
    client: BoostClient,
) -> None:
    _, model = await build(client, world())

    # l2 has no theory; l3's questions are all excluded.
    assert {row["lesson_id"]: row["status"] for row in model.lessons} == {
        "l1": "VISIBLE",
        "l2": "HIDDEN",
        "l3": "HIDDEN",
    }


async def test_mock_exams_and_journeys_keep_order_without_duplicates(
    client: BoostClient,
) -> None:
    _, model = await build(client, world())

    assert model.mock_exams[0]["name"] == {"sv-SE": "e1 sv-SE", "en-GB": "e1 en-GB"}
    assert model.mock_exams[0]["question_count"] == 60
    assert [(m["question_id"], m["sort"]) for m in model.mock_exam_questions] == [
        ("q1", 1),
        ("q2", 2),
    ]
    assert [(c["challenge_id"], c["milestone_id"], c["sort"]) for c in model.challenges] == [
        ("c1", "ms1", 1),
        ("c2", "ms1", 2),
    ]
    assert model.challenges[1]["goal"] == {"sv-SE": "Stay safe", "en-GB": "Stay safe"}
    assert [(q["question_id"], q["sort"]) for q in model.challenge_questions] == [
        ("q3", 1),
        ("q1", 2),
    ]


async def test_stored_revisions_are_never_fetched_again(client: BoostClient) -> None:
    catalogue, _ = await build(client, world())

    stored = {("q1", "1"): "a", ("q2", "1"): "a"}
    assert refs_needing_grading(catalogue, stored) == {("q3", "1"), ("q4", "1")}

    model = build_read_model(catalogue, stored_correct_keys=stored, grading={})
    # The stored key still validates the question, and no revision is re-recorded.
    assert {q["question_id"] for q in model.questions if q["status"] == "ACTIVE"} == {"q1", "q2"}
    assert model.new_revisions == []


async def test_missing_mock_exam_and_journey_routes_mean_none(client: BoostClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        world().mount(router)
        router.get(f"{BASE}/v1/delivery/mock-exams").respond(404, json={"status": 404})
        router.get(f"{BASE}/v1/delivery/learning-journeys").respond(404, json={"status": 404})
        catalogue = await fetch_catalogue(client, LOCALES, default_locale="sv-SE", page_size=10)

    assert catalogue.default.mock_exams == []
    assert catalogue.default.journeys == []
