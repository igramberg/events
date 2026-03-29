from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from events.domain.models import Event
from events.domain.models import EventCategory


LOCAL_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class WeekWindow:
    start: datetime
    end: datetime


def week_window_for(reference: date | datetime, tz: ZoneInfo = LOCAL_TZ) -> WeekWindow:
    if isinstance(reference, datetime):
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("reference datetime must be timezone-aware")
        local_reference = reference.astimezone(tz)
        local_date = local_reference.date()
    else:
        local_date = reference
    week_start_date = local_date - timedelta(days=local_date.weekday())
    start = datetime(week_start_date.year, week_start_date.month, week_start_date.day, tzinfo=tz)
    return WeekWindow(start=start, end=start + timedelta(days=7))


def event_in_week_window(event: Event, window: WeekWindow, tz: ZoneInfo = LOCAL_TZ) -> bool:
    starts_at_local = event.starts_at.astimezone(tz)
    return window.start <= starts_at_local < window.end


def is_event_in_scope(
    event: Event,
    window: WeekWindow,
    allowed_categories: set[EventCategory] | None = None,
    tz: ZoneInfo = LOCAL_TZ,
) -> bool:
    categories = EventCategory.v0_categories() if allowed_categories is None else allowed_categories
    return event.category in categories and event_in_week_window(event, window, tz=tz)
