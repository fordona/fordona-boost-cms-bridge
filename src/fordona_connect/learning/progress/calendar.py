"""Local days, streaks and the weekly view (ported from the engine)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Stockholm"
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def resolve_timezone(header: str | None) -> ZoneInfo:
    """The learner's IANA zone from ``X-Timezone``; an unknown or empty value means Stockholm."""
    if header and header.strip():
        try:
            return ZoneInfo(header.strip())
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZoneInfo(DEFAULT_TIMEZONE)


def local_date(moment: datetime, zone: ZoneInfo) -> date:
    return moment.astimezone(zone).date()


def next_midnight(moment: datetime, zone: ZoneInfo) -> datetime:
    tomorrow = local_date(moment, zone) + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=zone)


@dataclass(frozen=True, slots=True)
class DisplayedStreak:
    current: int
    longest: int
    extended_today: bool


def displayed_streak(
    current_streak: int, longest_streak: int, last_active: date | None, today: date
) -> DisplayedStreak:
    """A streak is alive while the last active day is today or yesterday."""
    alive = last_active is not None and last_active >= today - timedelta(days=1)
    return DisplayedStreak(
        current=current_streak if alive else 0,
        longest=longest_streak,
        extended_today=last_active == today,
    )


def next_streak(current_streak: int, last_active: date | None, today: date) -> int:
    """The streak after completing a lesson today."""
    if last_active == today:
        return current_streak
    if last_active is not None and today == last_active + timedelta(days=1):
        return current_streak + 1
    return 1


def week_start(today: date, starts_on: str) -> date:
    offset = (today.weekday() - WEEKDAYS.index(starts_on)) % 7
    return today - timedelta(days=offset)


@dataclass(frozen=True, slots=True)
class WeekDay:
    date: date
    status: str  # "done", "missed", "today" or "upcoming"
    done: bool | None


def week_days(today: date, starts_on: str, lessons_by_date: Mapping[date, int]) -> list[WeekDay]:
    start = week_start(today, starts_on)
    days: list[WeekDay] = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        active = lessons_by_date.get(day, 0) > 0
        if day == today:
            days.append(WeekDay(day, "today", active))
        elif day < today:
            days.append(WeekDay(day, "done" if active else "missed", None))
        else:
            days.append(WeekDay(day, "upcoming", None))
    return days
