from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from typing import Sequence
from zoneinfo import ZoneInfo

import events.main as main_module
from events.domain import EventCategory, WeekWindow, week_window_for
from events.domain.models import (
    Event,
    IdentityKind,
    Location,
    Organizer,
    Venue,
)
from events.main import create_app

LOCAL_TZ = ZoneInfo("America/New_York")


def make_event(
    *,
    event_key: str,
    title: str,
    category: EventCategory,
    starts_at: datetime,
    organizer: bool = True,
    description: str | None = "desc",
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
        organizer_obj = Organizer(
            organizer_key="org:v1:crossroads%20presents",
            name="Crossroads Presents",
        )

    return Event(
        event_key=event_key,
        identity_kind=IdentityKind.OCCURRENCE_ID,
        identity_inputs={
            "source_name": "roadrunner",
            "occurrence_id": event_key.rsplit(":", 1)[-1],
        },
        title=title,
        category=category,
        venue=venue,
        organizer=organizer_obj,
        starts_at=starts_at,
        source_url=f"https://example.com/{event_key.rsplit(':', 1)[-1]}",
        source_name="roadrunner",
        source_event_id=event_key.rsplit(":", 1)[-1],
        description=description,
        performers=("Band",),
        tags=("rock",),
    )


class StubRepository:
    def __init__(self, events: Sequence[Event]) -> None:
        self._events = tuple(events)
        self.last_window: WeekWindow | None = None

    def get_events_for_window(self, window: WeekWindow) -> Sequence[Event]:
        self.last_window = window
        return self._events

    def upsert_events(self, events, refresh_timestamp) -> None:
        raise AssertionError("T5 route must not upsert events")

    def prune_stale_events(self, window, refresh_timestamp) -> None:
        raise AssertionError("T5 route must not prune events")


def get_response(app):
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))

    start = next(
        msg for msg in messages if msg["type"] == "http.response.start"
    )
    bodies = [
        msg.get("body", b"")
        for msg in messages
        if msg["type"] == "http.response.body"
    ]
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return int(start["status"]), headers, b"".join(bodies).decode("utf-8")


class WeeklyPageTests(unittest.TestCase):
    def test_create_app_delays_default_repository_until_first_request(
        self,
    ) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        default_repo_calls: list[int] = [0]
        repository = StubRepository(())

        def fake_default_repository():
            default_repo_calls[0] += 1
            return repository

        original_default_repository = main_module._default_repository
        main_module._default_repository = fake_default_repository
        try:
            app = create_app(now_provider=lambda: now)
            self.assertEqual(0, default_repo_calls[0])

            status_code, _, body = get_response(app)

            self.assertEqual(200, status_code)
            self.assertIn("No events stored for this week", body)
            self.assertEqual(1, default_repo_calls[0])
            self.assertEqual(week_window_for(now), repository.last_window)
        finally:
            main_module._default_repository = original_default_repository

    def test_weekly_page_returns_html_empty_state_and_uses_now_provider(
        self,
    ) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(())
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, headers, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("No events stored for this week", body)
        self.assertIn("Manual refresh will be added in T7", body)
        self.assertIn("Mar 30 - Apr 5, 2026", body)
        self.assertEqual(week_window_for(now), repository.last_window)

    def test_weekly_page_renders_grouped_events_and_markup_hooks(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(
            (
                make_event(
                    event_key="event:v1:roadrunner:occ:1",
                    title="Late Monday Show",
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 31, 0, 30, tzinfo=UTC),
                ),
                make_event(
                    event_key="event:v1:roadrunner:occ:2",
                    title="Early Tuesday Show",
                    category=EventCategory.THEATER,
                    starts_at=datetime(2026, 3, 31, 5, 30, tzinfo=UTC),
                    organizer=False,
                    description=None,
                ),
            )
        )
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, _, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("Monday, Mar 30, 2026", body)
        self.assertIn("Tuesday, Mar 31, 2026", body)
        self.assertLess(
            body.find("Late Monday Show"),
            body.find("Early Tuesday Show"),
        )
        self.assertIn('aria-labelledby="day-2026-03-30"', body)
        self.assertIn('id="day-2026-03-30"', body)
        self.assertIn(
            'data-event-key="event:v1:roadrunner:occ:1"',
            body,
        )
        self.assertIn("Concert", body)
        self.assertIn("Theater", body)
        self.assertIn("Crossroads Presents", body)
        self.assertIn('href="https://example.com/1"', body)
        self.assertIn('datetime="2026-03-30T20:30:00-04:00"', body)

    def test_weekly_page_suppresses_non_v0_categories(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(
            (
                make_event(
                    event_key="event:v1:roadrunner:occ:1",
                    title="Concert Event",
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 31, 0, 30, tzinfo=UTC),
                ),
                make_event(
                    event_key="event:v1:roadrunner:occ:2",
                    title="Film Event",
                    category=EventCategory.FILM,
                    starts_at=datetime(2026, 3, 31, 1, 30, tzinfo=UTC),
                ),
            )
        )
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, _, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("Concert Event", body)
        self.assertNotIn("Film Event", body)

    def test_weekly_page_suppresses_events_outside_requested_window(
        self,
    ) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(
            (
                make_event(
                    event_key="event:v1:roadrunner:occ:1",
                    title="In Window",
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 31, 0, 30, tzinfo=UTC),
                ),
                make_event(
                    event_key="event:v1:roadrunner:occ:2",
                    title="Out Of Window",
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 4, 6, 5, 30, tzinfo=UTC),
                ),
            )
        )
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, _, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("In Window", body)
        self.assertNotIn("Out Of Window", body)

    def test_weekly_page_omits_optional_fields_when_absent(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(
            (
                make_event(
                    event_key="event:v1:roadrunner:occ:1",
                    title="Minimal Event",
                    category=EventCategory.CONCERT,
                    starts_at=datetime(2026, 3, 31, 0, 30, tzinfo=UTC),
                    organizer=False,
                    description=None,
                ),
            )
        )
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, _, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("Minimal Event", body)
        self.assertIn("1 event this week", body)
        self.assertNotIn("Crossroads Presents", body)
        self.assertNotIn('<p class="event-description">desc</p>', body)

    def test_weekly_page_includes_both_years_for_new_year_week_label(
        self,
    ) -> None:
        now = datetime(2025, 12, 31, 12, 0, tzinfo=LOCAL_TZ)
        repository = StubRepository(())
        app = create_app(repository=repository, now_provider=lambda: now)
        status_code, _, body = get_response(app)

        self.assertEqual(200, status_code)
        self.assertIn("Dec 29, 2025 - Jan 4, 2026", body)


if __name__ == "__main__":
    unittest.main()
