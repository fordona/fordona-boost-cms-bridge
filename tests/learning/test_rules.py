"""Pure learning rules: unlocks, entitlement, question selection, retry policy."""

from decimal import Decimal

from fordona_connect.learning.content.snapshot import SnapshotChallenge
from fordona_connect.learning.entitlement import Entitlement
from fordona_connect.learning.retry.policy import PolicyRow, RetryPolicy, resolve_policy
from fordona_connect.learning.selection import Strategy, select_questions
from fordona_connect.learning.unlock import UnlockStatus, resolve_unlocks
from tests.learning.snapshots import question, snapshot

LAYOUT = {"u1": ["l1", "l2"], "u2": ["l3"]}


def statuses(completed: set[str], entitled: set[str]) -> dict[str, UnlockStatus]:
    unlocks = resolve_unlocks(snapshot(LAYOUT), completed, lambda unit: unit in entitled)
    return {unlock.lesson_id: unlock.status for unlock in unlocks}


def test_the_first_unfinished_lesson_is_current_and_the_rest_locked() -> None:
    assert statuses(set(), {"u1", "u2"}) == {
        "l1": UnlockStatus.CURRENT,
        "l2": UnlockStatus.LOCKED,
        "l3": UnlockStatus.LOCKED,
    }


def test_completed_lessons_stay_open_and_the_next_one_unlocks() -> None:
    assert statuses({"l1", "l2"}, {"u1", "u2"}) == {
        "l1": UnlockStatus.COMPLETED,
        "l2": UnlockStatus.COMPLETED,
        "l3": UnlockStatus.CURRENT,
    }


def test_an_unentitled_unit_locks_even_its_first_lesson() -> None:
    assert statuses({"l1", "l2"}, {"u1"})["l3"] is UnlockStatus.LOCKED


def test_the_first_unit_is_free_and_subscribers_get_everything() -> None:
    content = snapshot(LAYOUT)
    free = Entitlement(content, subscribed=False)
    paid = Entitlement(content, subscribed=True)

    assert free.unit_entitled("u1")
    assert not free.unit_entitled("u2")
    assert paid.unit_entitled("u2")


def test_an_empty_catalogue_entitles_nothing_for_free() -> None:
    assert not Entitlement(snapshot({}), subscribed=False).unit_entitled("u1")


def test_the_lesson_bank_serves_every_active_question_in_id_order() -> None:
    content = snapshot(LAYOUT, questions=[question("q2", "l1"), question("q1", "l1")])

    selection = select_questions(content, "l1", Strategy.LESSON_BANK)

    assert [ref.question_id for ref in selection.refs] == ["q1", "q2"]
    assert all(ref.challenge_id is None for ref in selection.refs)


def test_the_challenge_strategy_uses_the_quiz_order_and_skips_inactive_questions() -> None:
    content = snapshot(
        LAYOUT,
        questions=[question("q1", "l1"), question("q2", "l1")],
        challenges=[SnapshotChallenge("c1", "m1", 1, ("l1",), ("q2", "gone", "q1"))],
    )

    selection = select_questions(content, "l1", Strategy.CHALLENGE)

    assert [ref.question_id for ref in selection.refs] == ["q2", "q1"]
    assert {ref.challenge_id for ref in selection.refs} == {"c1"}
    assert selection.reason == "challenge:curated-quiz"


def test_a_lesson_in_two_challenges_falls_back_to_its_bank() -> None:
    content = snapshot(
        LAYOUT,
        questions=[question("q1", "l1")],
        challenges=[
            SnapshotChallenge("c1", "m1", 1, ("l1",), ("q1",)),
            SnapshotChallenge("c2", "m1", 2, ("l1",), ("q1",)),
        ],
    )

    selection = select_questions(content, "l1", Strategy.CHALLENGE)

    assert content.challenge_for("l1") is None
    assert selection.reason == "no-challenge:lesson-bank-fallback"
    assert [ref.challenge_id for ref in selection.refs] == [None]


def test_a_lesson_without_questions_selects_nothing() -> None:
    assert select_questions(snapshot(LAYOUT), "l1", Strategy.LESSON_BANK).refs == ()


def test_policy_scopes_merge_narrowest_last() -> None:
    rows = [
        PolicyRow("GLOBAL", "GLOBAL", {"extras_min": 3, "similar_scope": "BANK"}),
        PolicyRow("UNIT", "u1", {"extras_min": 4, "similar_scope": "UNIT"}),
        PolicyRow("LESSON", "l1", {"extras_min": 5, "retry_enabled": False}),
    ]

    policy = resolve_policy(rows, "u1", "l1")

    assert policy.extras_min == 5
    assert policy.retry_enabled is False
    assert policy.similar_scope == "UNIT"
    assert policy.extras_max == 5  # default


def test_a_key_set_at_a_scope_that_may_not_set_it_is_ignored() -> None:
    rows = [PolicyRow("LESSON", "l1", {"similar_scope": "ANYWHERE"})]

    assert resolve_policy(rows, "u1", "l1").similar_scope == "REACHED"


def test_policy_round_trips_through_its_stored_json() -> None:
    policy = RetryPolicy(extras_per_wrong=Decimal("2.5"), difficulty_level_map={1: "EASY"})

    assert RetryPolicy.from_json(policy.to_json()) == policy
