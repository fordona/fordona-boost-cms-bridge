"""Pure retry and progress rules: neighbours, the retry composer, streaks, weeks."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fordona_connect.learning.progress.calendar import (
    displayed_streak,
    local_date,
    next_streak,
    resolve_timezone,
    week_days,
    week_start,
)
from fordona_connect.learning.progress.screens import learning_path_etag, readiness_percent
from fordona_connect.learning.retry.composer import LessonItem, compose_retry, extras_for
from fordona_connect.learning.retry.neighbours import (
    MAX_NEIGHBOURS,
    build_neighbours,
    rank_neighbours,
)
from fordona_connect.learning.retry.policy import RetryPolicy
from tests.learning.snapshots import question, snapshot


def q(
    question_id: str,
    lesson_id: str,
    *,
    unit_id: str = "u1",
    difficulty: int = 2,
    level: str = "EASY",
    topic: str | None = None,
    media: tuple[str, ...] = (),
):  # type: ignore[no-untyped-def]
    return replace(
        question(question_id, lesson_id, unit_id=unit_id),
        difficulty=difficulty,
        level=level,
        topic_tag=topic,
        media_kinds=media,
    )


# --- neighbours ---------------------------------------------------------------


def test_closer_relations_rank_first() -> None:
    seed = q("s", "l1", topic="give-way")
    bank = [
        seed,
        q("same-lesson-topic", "l1", topic="give-way"),
        q("same-unit-topic", "l2", topic="give-way"),
        q("same-lesson-domain", "l1"),
        q("same-domain-unit", "l3"),
        q("unrelated", "l9", unit_id="u9"),
    ]
    bank[-1] = replace(bank[-1], domain_code="other")

    ranked = rank_neighbours(seed, bank)

    assert [n.neighbour_id for n in ranked] == [
        "same-lesson-topic",
        "same-unit-topic",
        "same-lesson-domain",
        "same-domain-unit",
    ]
    assert [n.score for n in ranked] == [
        Decimal("1.0"),
        Decimal("0.8"),
        Decimal("0.6"),
        Decimal("0.4"),
    ]
    assert [n.rank for n in ranked] == [1, 2, 3, 4]


def test_ties_prefer_closer_difficulty_and_at_most_twenty_are_kept() -> None:
    seed = q("s", "l1", difficulty=3)
    bank = [seed, *(q(f"c{i:02}", "l1", difficulty=1 + i % 5) for i in range(30))]

    ranked = rank_neighbours(seed, bank)

    assert len(ranked) == MAX_NEIGHBOURS
    assert ranked[0].neighbour_id == "c02"  # difficulty 3, then lowest id
    assert len(build_neighbours(bank)) == MAX_NEIGHBOURS * len(bank)


# --- retry composer -----------------------------------------------------------


def item(seq: int, question_id: str, correct: bool, level: str = "EASY") -> LessonItem:
    return LessonItem(seq, question_id, "1", correct, ("a", "b", "c"), "traffic", None, 2, level)


def test_extras_scale_with_mistakes_within_the_bounds() -> None:
    policy = RetryPolicy()
    assert [extras_for(policy, wrong) for wrong in range(5)] == [0, 2, 3, 5, 5]


def test_wrong_items_repeat_and_bring_similar_questions() -> None:
    bank = [q("w1", "l1"), q("ok", "l1"), q("n1", "l1"), q("n2", "l1"), q("n3", "l1")]
    content = snapshot({"u1": ["l1"]}, questions=bank)
    content = replace(content, neighbours_by_question={"w1": tuple(rank_neighbours(bank[0], bank))})

    composition = compose_retry(
        content,
        [item(1, "w1", False), item(2, "ok", True)],
        lesson_id="l1",
        completed_lesson_ids=set(),
        seen_question_ids=set(),
        unit_entitled=lambda unit: True,
        policy=RetryPolicy(),
        seed=7,
    )

    sources = sorted((i["item_source"], i["question_id"]) for i in composition.items)
    assert sources == [("REPEAT", "w1"), ("SIMILAR", "n1"), ("SIMILAR", "n2")]
    assert composition.extras_short == 0
    similar = [i for i in composition.items if i["item_source"] == "SIMILAR"]
    assert {i["origin_question_id"] for i in similar} == {"w1"}


def test_filters_keep_out_unreached_unseen_harder_and_unentitled_questions() -> None:
    bank = [
        q("w1", "l1", level="MEDIUM", difficulty=3),
        q("harder", "l1", level="HARD", difficulty=4),
        q("later-lesson", "l2", level="MEDIUM", difficulty=3),
        q("paid", "l1", unit_id="u2", level="EASY"),
        q("seen", "l1", level="EASY"),
    ]
    content = snapshot({"u1": ["l1", "l2"], "u2": []}, questions=bank)
    content = replace(content, neighbours_by_question={"w1": tuple(rank_neighbours(bank[0], bank))})

    composition = compose_retry(
        content,
        [item(1, "w1", False, level="MEDIUM")],
        lesson_id="l1",
        completed_lesson_ids=set(),
        seen_question_ids={"seen"},
        unit_entitled=lambda unit: unit == "u1",
        policy=RetryPolicy(),
        seed=1,
    )

    # "seen" is only allowed on the second pass, which runs because extras fell short.
    assert sorted(i["question_id"] for i in composition.items) == ["seen", "w1"]
    assert composition.extras_short == 1


def test_image_questions_only_repeat() -> None:
    bank = [q("img", "l1", media=("image",)), q("n1", "l1")]
    content = snapshot({"u1": ["l1"]}, questions=bank)
    content = replace(
        content, neighbours_by_question={"img": tuple(rank_neighbours(bank[0], bank))}
    )

    composition = compose_retry(
        content,
        [item(1, "img", False)],
        lesson_id="l1",
        completed_lesson_ids=set(),
        seen_question_ids=set(),
        unit_entitled=lambda unit: True,
        policy=RetryPolicy(),
        seed=1,
    )

    assert [i["item_source"] for i in composition.items] == ["REPEAT"]
    assert composition.extras_short == 2


# --- calendar -----------------------------------------------------------------


def test_unknown_timezones_fall_back_to_stockholm() -> None:
    assert resolve_timezone("Not/AZone").key == "Europe/Stockholm"
    assert resolve_timezone(None).key == "Europe/Stockholm"
    assert resolve_timezone(" Asia/Colombo ").key == "Asia/Colombo"


def test_the_local_day_follows_the_learners_zone() -> None:
    moment = datetime(2026, 11, 8, 23, 30, tzinfo=ZoneInfo("UTC"))
    assert local_date(moment, ZoneInfo("Europe/Stockholm")) == date(2026, 11, 9)


def test_streaks_grow_on_consecutive_days_and_reset_after_a_gap() -> None:
    day = date(2026, 11, 9)
    assert next_streak(3, day, day) == 3
    assert next_streak(3, date(2026, 11, 8), day) == 4
    assert next_streak(3, date(2026, 11, 6), day) == 1
    assert next_streak(0, None, day) == 1


def test_a_streak_is_shown_while_yesterday_was_active() -> None:
    today = date(2026, 11, 9)
    assert displayed_streak(4, 6, date(2026, 11, 8), today).current == 4
    assert displayed_streak(4, 6, date(2026, 11, 7), today).current == 0
    assert displayed_streak(4, 6, today, today).extended_today is True


def test_the_week_starts_on_the_configured_day() -> None:
    today = date(2026, 11, 11)  # a Wednesday
    assert week_start(today, "SUNDAY") == date(2026, 11, 8)
    assert week_start(today, "MONDAY") == date(2026, 11, 9)
    days = week_days(today, "MONDAY", {date(2026, 11, 9): 2})
    assert [d.status for d in days] == ["done", "missed", "today", *["upcoming"] * 4]


def test_readiness_and_etag() -> None:
    assert readiness_percent(Decimal("1.5"), 4) == 38
    assert readiness_percent(Decimal(0), 0) == 0
    assert learning_path_etag(7, 3, True, "sv-SE") == '"7.3.sub.sv-SE"'
