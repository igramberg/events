"""Public domain API for normalized events."""

from events.domain.keys import derive_event_identity, make_event_key
from events.domain.models import (
    Event,
    EventCategory,
    IdentityKind,
    Location,
    Organizer,
    Venue,
)
from events.domain.weeks import (
    WeekWindow,
    event_in_week_window,
    is_event_in_scope,
    week_window_for,
)

__all__ = [
    "Event",
    "EventCategory",
    "IdentityKind",
    "Location",
    "Organizer",
    "Venue",
    "derive_event_identity",
    "make_event_key",
    "WeekWindow",
    "event_in_week_window",
    "is_event_in_scope",
    "week_window_for",
]
