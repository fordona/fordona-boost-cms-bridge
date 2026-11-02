"""The stub's change feed tracker (plan §13.3)."""

import pytest

from boost_stub.changes import ChangeTracker, CursorExpiredError


@pytest.fixture
def tracker() -> ChangeTracker:
    return ChangeTracker(":memory:")


def test_first_sighting_of_an_entity_is_published(tracker: ChangeTracker) -> None:
    written = tracker.record("QUESTION", {"100": "1"}, now=1000.0)

    assert written == 1
    page = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)
    assert [(r.id, r.version, r.change) for r in page.items] == [("100", "1", "PUBLISHED")]


def test_unchanged_snapshot_writes_nothing(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"100": "1"}, now=1000.0)

    written = tracker.record("QUESTION", {"100": "1"}, now=1001.0)

    assert written == 0


def test_a_new_version_is_published_again(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"100": "1"}, now=1000.0)

    written = tracker.record("QUESTION", {"100": "2"}, now=1001.0)

    page = tracker.feed(0, 10, now=1001.0, visibility_lag_seconds=0)
    assert written == 1
    assert [(r.version, r.change) for r in page.items] == [("1", "PUBLISHED"), ("2", "PUBLISHED")]


def test_a_disappeared_entity_is_unpublished(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"100": "1", "101": "1"}, now=1000.0)

    written = tracker.record("QUESTION", {"100": "1"}, now=1001.0)

    page = tracker.feed(0, 10, now=1001.0, visibility_lag_seconds=0)
    assert written == 1
    assert page.items[-1].id == "101"
    assert page.items[-1].change == "UNPUBLISHED"


def test_entity_types_are_tracked_independently(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"100": "1"}, now=1000.0)
    tracker.record("LESSON", {"100": "1"}, now=1000.0)  # same id, different type

    written = tracker.record("QUESTION", {"100": "1"}, now=1001.0)  # unchanged for QUESTION

    assert written == 0


def test_seq_is_strictly_increasing_across_writes(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"100": "1", "101": "1"}, now=1000.0)
    tracker.record("LESSON", {"10": "1"}, now=1000.0)

    page = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)

    seqs = [int(r.seq) for r in page.items]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


# --- feed: limit, nextCursor, hasMore --------------------------------------------


def test_limit_truncates_and_sets_has_more(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {str(n): "1" for n in range(5)}, now=1000.0)

    page = tracker.feed(0, 3, now=1000.0, visibility_lag_seconds=0)

    assert len(page.items) == 3
    assert page.has_more is True
    assert page.next_cursor == page.items[-1].seq


def test_no_truncation_means_has_more_is_false(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"1": "1", "2": "1"}, now=1000.0)

    page = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)

    assert page.has_more is False
    assert len(page.items) == 2


def test_reading_past_the_head_is_an_empty_page(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)
    head = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)

    page = tracker.feed(int(head.items[-1].seq), 10, now=1000.0, visibility_lag_seconds=0)

    assert page.items == []
    assert page.has_more is False
    assert page.next_cursor == head.items[-1].seq


def test_empty_feed_from_scratch_echoes_the_requested_cursor() -> None:
    tracker = ChangeTracker(":memory:")
    page = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0)
    assert page.items == []
    assert page.next_cursor == "0"


# --- visibility lag (commit-order safety, §13.3) ---------------------------------


def test_a_row_is_invisible_until_the_lag_passes(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)

    too_soon = tracker.feed(0, 10, now=1002.0, visibility_lag_seconds=5)
    later = tracker.feed(0, 10, now=1006.0, visibility_lag_seconds=5)

    assert too_soon.items == []
    assert len(later.items) == 1


def test_a_slower_reader_never_sees_rows_vanish() -> None:
    """Two rows written moments apart must never let a poll at t2 see the second
    without the first already being visible (the point of the lag at all)."""
    tracker = ChangeTracker(":memory:")
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)
    tracker.record("QUESTION", {"1": "1", "2": "1"}, now=1000.2)

    page = tracker.feed(0, 10, now=1005.5, visibility_lag_seconds=5)

    assert {r.id for r in page.items} == {"1", "2"}


# --- retention and CURSOR_EXPIRED -------------------------------------------------


def test_purge_removes_old_rows_and_raises_cursor_expired(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)

    tracker.purge(now=2000.0, retention_seconds=500.0)

    with pytest.raises(CursorExpiredError):
        tracker.feed(0, 10, now=2000.0, visibility_lag_seconds=0)


def test_purge_within_retention_keeps_rows_readable(tracker: ChangeTracker) -> None:
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)

    tracker.purge(now=1100.0, retention_seconds=500.0)

    page = tracker.feed(0, 10, now=1100.0, visibility_lag_seconds=0)
    assert len(page.items) == 1


def test_a_cursor_at_the_watermark_still_works(tracker: ChangeTracker) -> None:
    """``after == watermark`` means "I already have the purged row" — only
    ``after < watermark`` (missed content) should raise."""
    tracker.record("QUESTION", {"1": "1"}, now=1000.0)
    purged_seq = tracker.feed(0, 10, now=1000.0, visibility_lag_seconds=0).items[0].seq
    tracker.record("QUESTION", {"1": "1", "2": "1"}, now=1590.0)

    tracker.purge(now=1600.0, retention_seconds=500.0)  # cutoff 1100: only the first row qualifies

    page = tracker.feed(int(purged_seq), 10, now=1600.0, visibility_lag_seconds=0)
    assert [r.id for r in page.items] == ["2"]
