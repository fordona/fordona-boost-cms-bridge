"""Pure mapping logic: engine DTO + Boost body -> the public theory schemas."""

import pytest

from boost_bridge.clients.boost.models import BoostQuestion
from boost_bridge.clients.engine.theory import (
    EngineAttemptItemRef,
    EngineHome,
    EngineHomeTabs,
    EngineHomeTabState,
    EngineHomeUser,
)
from boost_bridge.core.errors import ContentNotFoundError
from boost_bridge.services import theory_mappers as mappers
from boost_bridge.services.media import AssetUrlResolver, PlainUrlSigner
from tests.factories import question_payload

BASE = "https://media.test"


def _resolver() -> AssetUrlResolver:
    plain = PlainUrlSigner(BASE)
    return AssetUrlResolver(frozenset(), plain, plain)


def _question(question_id: str = "100") -> BoostQuestion:
    return BoostQuestion.model_validate(question_payload(question_id=question_id))


def test_map_home_with_partial_failure_leaves_continue_and_tabs_populated() -> None:
    engine_home = EngineHome(
        user=EngineHomeUser(initials="SI", first_name="Samira"),
        week=None,
        daily_challenge=None,
        streak=None,
        readiness=None,
        tabs=EngineHomeTabs(
            learning_path=EngineHomeTabState(locked=False, lock_reason=None),
            mock_exams=EngineHomeTabState(locked=True, lock_reason="NOT_AVAILABLE"),
        ),
        learning_path_etag='"42"',
    )

    out = mappers.map_home(engine_home)

    assert out.week is None
    assert out.streak is None
    assert out.readiness is None
    assert out.tabs.mock_exams.locked is True
    assert out.continue_ is None
    assert out.up_next == []


def test_hydrate_items_orders_options_with_display_labels() -> None:
    question = _question(question_id="100")
    ref = EngineAttemptItemRef(
        seq=1,
        phase="LESSON",
        question_id="100",
        version="5",
        option_order=["b", "a", "c"],
        answered=None,
    )

    [item] = mappers.hydrate_items([ref], {"100": question}, _resolver())

    assert [opt.key for opt in item.options] == ["b", "a", "c"]
    assert [opt.label for opt in item.options] == ["A", "B", "C"]
    assert item.answered is False


def test_hydrate_items_raises_when_question_missing_from_cache() -> None:
    ref = EngineAttemptItemRef(
        seq=1, phase="LESSON", question_id="100", version="5", option_order=["a"], answered=None
    )

    with pytest.raises(ContentNotFoundError):
        mappers.hydrate_items([ref], {}, _resolver())


def test_hydrate_items_raises_when_option_order_references_unknown_option() -> None:
    question = _question(question_id="100")
    ref = EngineAttemptItemRef(
        seq=1,
        phase="LESSON",
        question_id="100",
        version="5",
        option_order=["not-a-real-option"],
        answered=None,
    )

    with pytest.raises(ContentNotFoundError):
        mappers.hydrate_items([ref], {"100": question}, _resolver())


def test_hydrate_items_marks_answered_items() -> None:
    question = _question(question_id="100")
    ref = EngineAttemptItemRef(
        seq=1,
        phase="LESSON",
        question_id="100",
        version="5",
        option_order=["a", "b", "c"],
        answered=True,
    )

    [item] = mappers.hydrate_items([ref], {"100": question}, _resolver())

    assert item.answered is True


def test_correct_option_content_finds_the_matching_option() -> None:
    question = _question(question_id="100")

    content = mappers.correct_option_content(question, "b", _resolver())

    assert content[0].markdown == "Väjningsplikt"  # type: ignore[union-attr]


def test_correct_option_content_raises_for_unknown_key() -> None:
    question = _question(question_id="100")

    with pytest.raises(ContentNotFoundError):
        mappers.correct_option_content(question, "nope", _resolver())


def test_item_refs_by_seq_maps_question_and_version() -> None:
    ref = EngineAttemptItemRef(
        seq=3, phase="LESSON", question_id="100", version="5", option_order=["a"], answered=None
    )

    refs = mappers.item_refs_by_seq([ref])

    assert refs[3].question_id == "100"
    assert refs[3].version == "5"


def test_parse_explanation_blocks_tolerates_unknown_type() -> None:
    raw = [{"type": "text", "markdown": "ok"}, {"type": "something_new"}]

    blocks = mappers.parse_explanation_blocks(raw)

    assert len(blocks) == 2
