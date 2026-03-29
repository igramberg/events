from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from events.domain.keys import derive_event_identity
from events.domain.models import Event
from events.domain.models import EventCategory
from events.domain.models import Location
from events.domain.models import Venue
from events.domain.weeks import WeekWindow
from events.domain.weeks import event_in_week_window
from events.domain.weeks import is_event_in_scope
from events.domain.weeks import week_window_for


def build_event(*, category: EventCategory, starts_at: datetime) -> Event:
    location = Location(
        location_key="loc:v1:us:ma:boston",
        city="Boston",
        region="MA",
        country_code="US",
    )
    venue = Venue(
        venue_key="venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner",
        venue_name="Roadrunner",
        location=location,
    )
    identity = derive_event_identity(
        source_name="test_source",
        starts_at=starts_at,
        occurrence_id=starts_at.isoformat(),
    )
    return Event(
        event_key=identity.event_key,
        identity_kind=identity.identity_kind,
        identity_inputs=identity.identity_inputs,
        title="Example",
        category=category,
        venue=venue,
        organizer=None,
        starts_at=starts_at,
        source_url="https://example.com/show",
        source_event_id=None,
        source_name="test_source",
    )


class WeekWindowTests(unittest.TestCase):
    def test_week_window_for_uses_monday_to_monday_in_new_york(self) -> None:
        window = week_window_for(date(2026, 3, 28))

        self.assertEqual(
            datetime(2026, 3, 23, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            window.start,
        )
        self.assertEqual(
            datetime(2026, 3, 30, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            window.end,
        )

    def test_week_window_for_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValueError):
            week_window_for(datetime(2026, 3, 28, 12, 0, 0))

    def test_week_window_can_cross_dst_boundary(self) -> None:
        # This intentionally locks behavior to current America/New_York tzdata:
        # the local Monday-to-Monday window stays the same even when the UTC
        # duration of that week is not exactly 7 * 24 hours.
        window = week_window_for(date(2026, 3, 8))

        self.assertEqual(
            datetime(2026, 3, 2, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            window.start,
        )
        self.assertEqual(
            datetime(2026, 3, 9, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            window.end,
        )
        self.assertEqual(
            167 * 60 * 60,
            int((window.end.astimezone(ZoneInfo("UTC")) - window.start.astimezone(ZoneInfo("UTC"))).total_seconds()),
        )

    def test_monday_midnight_is_included_and_next_monday_midnight_is_excluded(self) -> None:
        window = WeekWindow(
            start=datetime(2026, 3, 23, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            end=datetime(2026, 3, 30, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertTrue(
            event_in_week_window(
                build_event(
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 23, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
                ),
                window,
            ),
        )
        self.assertFalse(
            event_in_week_window(
                build_event(
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 30, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
                ),
                window,
            ),
        )

    def test_tz_aware_start_can_cross_local_day_boundary(self) -> None:
        window = WeekWindow(
            start=datetime(2026, 3, 23, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
            end=datetime(2026, 3, 30, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )
        event = build_event(
            category=EventCategory.CONCERT,
            starts_at=datetime(2026, 3, 23, 2, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

        self.assertFalse(event_in_week_window(event, window))

    def test_events_earlier_than_now_but_same_week_remain_in_scope(self) -> None:
        window = week_window_for(date(2026, 3, 28))
        event = build_event(
            category=EventCategory.THEATER,
            starts_at=datetime(2026, 3, 24, 20, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertTrue(is_event_in_scope(event, window))

    def test_out_of_scope_category_is_excluded(self) -> None:
        window = week_window_for(date(2026, 3, 28))
        event = build_event(
            category=EventCategory.EXHIBITION,
            starts_at=datetime(2026, 3, 24, 20, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertFalse(is_event_in_scope(event, window))

    def test_empty_allowed_categories_excludes_everything(self) -> None:
        window = week_window_for(date(2026, 3, 28))
        event = build_event(
            category=EventCategory.CONCERT,
            starts_at=datetime(2026, 3, 24, 20, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertFalse(is_event_in_scope(event, window, allowed_categories=set()))


if __name__ == "__main__":
    unittest.main()
