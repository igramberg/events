from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine

from events.domain import WeekWindow
from events.domain import week_window_for
from events.domain.models import Event
from events.domain.models import EventCategory
from events.domain.models import IdentityKind
from events.domain.models import Location
from events.domain.models import Organizer
from events.domain.models import Venue
from events.storage.sqlite import SqliteStorageRepository
from events.storage.sqlite import create_tables
from events.storage.sqlite import utc_bounds_for_window


LOCAL_TZ = ZoneInfo("America/New_York")


def make_event(
    *,
    event_key: str,
    occurrence_id: str,
    title: str,
    starts_at: datetime,
    organizer: bool = True,
) -> Event:
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
    organizer_obj = None
    if organizer:
        organizer_obj = Organizer(organizer_key="org:v1:crossroads%20presents", name="Crossroads Presents")

    return Event(
        event_key=event_key,
        identity_kind=IdentityKind.OCCURRENCE_ID,
        identity_inputs={"source_name": "roadrunner", "occurrence_id": occurrence_id},
        title=title,
        category=EventCategory.CONCERT,
        venue=venue,
        organizer=organizer_obj,
        starts_at=starts_at,
        source_url="https://example.com/show",
        source_name="roadrunner",
        source_event_id=occurrence_id,
        description="desc",
        performers=("Band",),
        tags=("rock",),
    )


def make_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    create_tables(engine)
    return SqliteStorageRepository(engine=engine)


def test_upsert_updates_existing_row():
    repo = make_repo()
    refresh_ts = datetime(2026, 3, 29, 12, 0, 0, 123456, tzinfo=ZoneInfo("UTC"))
    event = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="First Title",
        starts_at=datetime(2026, 3, 30, 1, 0, tzinfo=ZoneInfo("UTC")),
    )

    repo.upsert_events([event], refresh_ts)

    updated = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="Updated Title",
        starts_at=datetime(2026, 3, 30, 1, 0, tzinfo=ZoneInfo("UTC")),
    )

    repo.upsert_events([updated], refresh_ts)

    events = repo.get_events_for_window(week_window_for(datetime(2026, 3, 30, tzinfo=ZoneInfo("UTC"))))
    assert len(events) == 1
    assert events[0].title == "Updated Title"
    assert events[0].performers == ("Band",)
    assert events[0].tags == ("rock",)


def test_prune_missing_removes_absent_rows():
    repo = make_repo()
    refresh_ts1 = datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo("UTC"))
    event1 = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="One",
        starts_at=datetime(2026, 3, 30, 1, 0, tzinfo=ZoneInfo("UTC")),
    )
    event2 = make_event(
        event_key="event:v1:roadrunner:occ:2",
        occurrence_id="2",
        title="Two",
        starts_at=datetime(2026, 3, 31, 1, 0, tzinfo=ZoneInfo("UTC")),
    )
    window = week_window_for(datetime(2026, 3, 30, tzinfo=ZoneInfo("UTC")))

    repo.upsert_events([event1, event2], refresh_ts1)

    refresh_ts2 = datetime(2026, 3, 29, 13, 0, tzinfo=ZoneInfo("UTC"))
    repo.upsert_events([event1], refresh_ts2)
    repo.prune_stale_events(window, refresh_ts2)

    events = repo.get_events_for_window(window)
    assert [e.event_key for e in events] == ["event:v1:roadrunner:occ:1"]


def test_prune_by_window_removes_out_of_range():
    repo = make_repo()
    window = week_window_for(datetime(2026, 3, 30, tzinfo=LOCAL_TZ))
    refresh_ts = datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo("UTC"))

    in_window = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="In",
        starts_at=window.start + timedelta(hours=2),
    )
    before_window = make_event(
        event_key="event:v1:roadrunner:occ:2",
        occurrence_id="2",
        title="Out",
        starts_at=window.start - timedelta(days=1),
    )

    repo.upsert_events([in_window, before_window], refresh_ts)
    repo.prune_stale_events(window, refresh_ts)

    events = repo.get_events_for_window(window)
    assert [e.event_key for e in events] == ["event:v1:roadrunner:occ:1"]


def test_rejects_naive_refresh_timestamp():
    repo = make_repo()
    event = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="One",
        starts_at=datetime(2026, 3, 30, 1, 0, tzinfo=ZoneInfo("UTC")),
    )
    with pytest.raises(ValueError):
        repo.upsert_events([event], datetime(2026, 3, 29, 12, 0))


def test_utc_bounds_helper_matches_expected_format():
    window = WeekWindow(
        start=datetime(2026, 3, 30, 0, 0, tzinfo=LOCAL_TZ),
        end=datetime(2026, 4, 6, 0, 0, tzinfo=LOCAL_TZ),
    )
    start_utc, end_utc = utc_bounds_for_window(window)
    assert start_utc.endswith("Z")
    assert end_utc.endswith("Z")
    assert len(start_utc) == len("2026-03-30T00:00:00Z")
    assert len(end_utc) == len("2026-04-06T00:00:00Z")


def test_identity_mismatch_raises_and_rolls_back_batch():
    repo = make_repo()
    refresh_ts = datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo("UTC"))
    good = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="1",
        title="One",
        starts_at=datetime(2026, 3, 30, 1, 0, tzinfo=ZoneInfo("UTC")),
    )
    mismatched = make_event(
        event_key="event:v1:roadrunner:occ:1",
        occurrence_id="DIFFERENT",
        title="Two",
        starts_at=datetime(2026, 3, 31, 1, 0, tzinfo=ZoneInfo("UTC")),
    )

    repo.upsert_events([good], refresh_ts)
    with pytest.raises(ValueError):
        repo.upsert_events([mismatched], refresh_ts)

    events = repo.get_events_for_window(week_window_for(datetime(2026, 3, 30, tzinfo=ZoneInfo("UTC"))))
    assert [e.title for e in events] == ["One"]


def test_window_end_is_exclusive():
    repo = make_repo()
    window = week_window_for(datetime(2026, 3, 30, tzinfo=LOCAL_TZ))
    refresh_ts = datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo("UTC"))

    at_end = make_event(
        event_key="event:v1:roadrunner:occ:3",
        occurrence_id="3",
        title="At End",
        starts_at=window.end,  # exactly at upper bound
    )
    inside = make_event(
        event_key="event:v1:roadrunner:occ:4",
        occurrence_id="4",
        title="Inside",
        starts_at=window.start + timedelta(hours=1),
    )

    repo.upsert_events([at_end, inside], refresh_ts)
    repo.prune_stale_events(window, refresh_ts)
    events = repo.get_events_for_window(window)
    assert [e.event_key for e in events] == ["event:v1:roadrunner:occ:4"]
