from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from events.domain import WeekWindow
from events.domain import week_window_for
from events.domain.models import Event
from events.domain.models import EventCategory
from events.domain.models import IdentityKind
from events.domain.models import Location
from events.domain.models import Organizer
from events.domain.models import Venue


class DomainModelTests(unittest.TestCase):
    def test_domain_package_reexports_primary_symbols(self) -> None:
        self.assertEqual("events.domain.weeks", WeekWindow.__module__)
        self.assertEqual("events.domain.weeks", week_window_for.__module__)

    def test_event_category_exposes_v0_categories(self) -> None:
        self.assertEqual(
            {EventCategory.CONCERT, EventCategory.THEATER},
            EventCategory.v0_categories(),
        )

    def test_event_requires_timezone_aware_start(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:roadrunner:occ:123",
                title="Example Show",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={"source_name": "roadrunner", "occurrence_id": "123"},
                starts_at=datetime(2026, 3, 28, 20, 0, 0),
                source_url="https://example.com/show",
                source_event_id=None,
                source_name="roadrunner",
            )

    def test_event_accepts_tz_aware_start(self) -> None:
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
        organizer = Organizer(
            organizer_key="org:v1:crossroads%20presents",
            name="Crossroads Presents",
        )

        event = Event(
            event_key="event:v1:roadrunner:occ:123",
            title="Example Show",
            category=EventCategory.CONCERT,
            venue=venue,
            organizer=organizer,
            identity_kind=IdentityKind.OCCURRENCE_ID,
            identity_inputs={"source_name": "roadrunner", "occurrence_id": "123"},
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            source_url="https://example.com/show",
            source_event_id="123",
            source_name="roadrunner",
        )

        self.assertEqual("Roadrunner", event.venue.venue_name)
        self.assertEqual("Crossroads Presents", event.organizer.name)
        self.assertEqual(IdentityKind.OCCURRENCE_ID, event.identity_kind)
        self.assertEqual(
            {"source_name": "roadrunner", "occurrence_id": "123"},
            dict(event.identity_inputs),
        )

    def test_event_rejects_invalid_source_name(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:roadrunner:occ:123",
                title="Example Show",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={"source_name": "roadrunner:boston", "occurrence_id": "123"},
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="https://example.com/show",
                source_event_id="123",
                source_name="roadrunner:boston",
            )

    def test_event_rejects_empty_required_strings(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="",
                title="",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={},
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="",
                source_event_id=None,
                source_name="roadrunner",
            )

    def test_event_rejects_empty_identity_inputs(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:roadrunner:occ:123",
                title="Example Show",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={},
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="https://example.com/show",
                source_event_id=None,
                source_name="roadrunner",
            )

    def test_event_rejects_identity_inputs_with_mismatched_source_name(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:roadrunner:occ:123",
                title="Example Show",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={"source_name": "other_source", "occurrence_id": "123"},
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="https://example.com/show",
                source_event_id=None,
                source_name="roadrunner",
            )

    def test_event_rejects_inconsistent_source_event_identity(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:boch_center:src:HAMILTON%2FEvening:2026-03-28T20%3A00%3A00Z",
                title="Example Show",
                category=EventCategory.THEATER,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.SOURCE_EVENT_ID_STARTS_AT,
                identity_inputs={
                    "source_name": "boch_center",
                    "source_event_id": "HAMILTON/Evening",
                    "starts_at_utc": "2026-03-28T21:00:00Z",
                },
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="https://example.com/show",
                source_event_id="HAMILTON/Evening",
                source_name="boch_center",
            )

    def test_event_rejects_non_absolute_source_url(self) -> None:
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

        with self.assertRaises(ValueError):
            Event(
                event_key="event:v1:roadrunner:occ:123",
                title="Example Show",
                category=EventCategory.CONCERT,
                venue=venue,
                organizer=None,
                identity_kind=IdentityKind.OCCURRENCE_ID,
                identity_inputs={"source_name": "roadrunner", "occurrence_id": "123"},
                starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
                source_url="/relative/path",
                source_event_id=None,
                source_name="roadrunner",
            )

    def test_location_venue_and_organizer_reject_empty_required_strings(self) -> None:
        with self.assertRaises(ValueError):
            Location(
                location_key="",
                city="",
                region="MA",
                country_code="US",
            )

        location = Location(
            location_key="loc:v1:us:ma:boston",
            city="Boston",
            region="MA",
            country_code="US",
        )

        with self.assertRaises(ValueError):
            Venue(
                venue_key="",
                venue_name="",
                location=location,
            )

        with self.assertRaises(ValueError):
            Organizer(
                organizer_key="",
                name="",
            )

    def test_location_venue_and_organizer_reject_mismatched_canonical_keys(self) -> None:
        location = Location(
            location_key="loc:v1:us:ma:boston",
            city="Boston",
            region="MA",
            country_code="US",
        )

        with self.assertRaises(ValueError):
            Location(
                location_key="loc:v1:us:ma:cambridge",
                city="Boston",
                region="MA",
                country_code="US",
            )

        with self.assertRaises(ValueError):
            Venue(
                venue_key="venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:wrong",
                venue_name="Roadrunner",
                location=location,
            )

        with self.assertRaises(ValueError):
            Organizer(
                organizer_key="org:v1:wrong",
                name="Crossroads Presents",
            )


if __name__ == "__main__":
    unittest.main()
