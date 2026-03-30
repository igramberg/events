from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from events.domain import EventCategory, WeekWindow, event_in_week_window
from events.domain.models import Event

LOCAL_TZ = ZoneInfo("America/New_York")
MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
MERIDIEM_LABELS = ("AM", "PM")
CATEGORY_LABELS = {
    EventCategory.CONCERT: "Concert",
    EventCategory.THEATER: "Theater",
}


@dataclass(frozen=True, slots=True)
class RefreshStatusView:
    message: str


@dataclass(frozen=True, slots=True)
class WeeklyEventItemView:
    event_key: str
    title: str
    category_label: str
    starts_at_label: str
    starts_at_iso: str
    venue_name: str
    location_label: str
    organizer_name: str | None
    source_url: str
    description: str | None


@dataclass(frozen=True, slots=True)
class WeeklyDaySectionView:
    day_key: str
    day_label: str
    items: tuple[WeeklyEventItemView, ...]


@dataclass(frozen=True, slots=True)
class WeeklyPageView:
    week_label: str
    week_start: str
    week_end_exclusive: str
    day_sections: tuple[WeeklyDaySectionView, ...]
    total_events: int
    refresh_status: RefreshStatusView
    has_events: bool


def build_weekly_page_view(
    *, events: Iterable[Event], window: WeekWindow
) -> WeeklyPageView:
    visible_categories = EventCategory.v0_categories()
    visible_events = [
        event
        for event in events
        if event.category in visible_categories
        and event_in_week_window(event, window, tz=LOCAL_TZ)
    ]
    grouped: dict[str, list[WeeklyEventItemView]] = {}
    day_labels: dict[str, str] = {}

    for event in visible_events:
        local_start = event.starts_at.astimezone(LOCAL_TZ)
        day_key = local_start.date().isoformat()
        day_labels.setdefault(day_key, _format_day_label(local_start))
        grouped.setdefault(day_key, []).append(
            WeeklyEventItemView(
                event_key=event.event_key,
                title=event.title,
                category_label=CATEGORY_LABELS.get(
                    event.category,
                    event.category.value.replace("_", " ").title(),
                ),
                starts_at_label=_format_time_label(local_start),
                starts_at_iso=local_start.isoformat(),
                venue_name=event.venue.venue_name,
                location_label=_format_location_label(event),
                organizer_name=event.organizer.name
                if event.organizer
                else None,
                source_url=event.source_url,
                description=event.description,
            )
        )

    day_sections = tuple(
        WeeklyDaySectionView(
            day_key=day_key,
            day_label=day_labels[day_key],
            items=tuple(grouped[day_key]),
        )
        for day_key in sorted(grouped)
    )

    local_start = window.start.astimezone(LOCAL_TZ)
    local_end_exclusive = window.end.astimezone(LOCAL_TZ)
    local_end_display = local_end_exclusive - timedelta(days=1)
    if local_start.year != local_end_display.year:
        week_label = (
            f"{MONTH_ABBR[local_start.month - 1]} "
            f"{local_start.day}, {local_start.year} - "
            f"{MONTH_ABBR[local_end_display.month - 1]} "
            f"{local_end_display.day}, {local_end_display.year}"
        )
    else:
        week_label = (
            f"{MONTH_ABBR[local_start.month - 1]} {local_start.day} - "
            f"{MONTH_ABBR[local_end_display.month - 1]} "
            f"{local_end_display.day}, {local_end_display.year}"
        )
    return WeeklyPageView(
        week_label=week_label,
        week_start=local_start.date().isoformat(),
        week_end_exclusive=local_end_exclusive.date().isoformat(),
        day_sections=day_sections,
        total_events=len(visible_events),
        refresh_status=RefreshStatusView(
            message="Manual refresh will be added in T7"
        ),
        has_events=bool(visible_events),
    )


def _format_day_label(local_start: datetime) -> str:
    return (
        f"{WEEKDAY_NAMES[local_start.weekday()]}, "
        f"{MONTH_ABBR[local_start.month - 1]} "
        f"{local_start.day}, {local_start.year}"
    )


def _format_time_label(local_start: datetime) -> str:
    hour_24 = local_start.hour
    minute = local_start.minute
    meridiem = MERIDIEM_LABELS[0 if hour_24 < 12 else 1]
    hour_12 = hour_24 % 12 or 12
    return f"{hour_12}:{minute:02d} {meridiem}"


def _format_location_label(event: Event) -> str:
    return f"{event.venue.location.city}, {event.venue.location.region}"
