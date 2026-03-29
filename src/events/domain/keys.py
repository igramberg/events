from __future__ import annotations

from datetime import datetime

from events.domain.identity import (
    derive_event_identity,
    encode_key_component,
    format_starts_at_utc,
)

__all__ = [
    "derive_event_identity",
    "format_starts_at_utc",
    "make_event_key",
    "make_location_key",
    "make_organizer_key",
    "make_venue_key",
]


def make_location_key(*, city: str, region: str, country_code: str) -> str:
    return (
        f"loc:v1:{encode_key_component(country_code)}:"
        f"{encode_key_component(region)}:"
        f"{encode_key_component(city)}"
    )


def make_venue_key(*, location_key: str, venue_name: str) -> str:
    return f"venue:v1:{encode_key_component(location_key)}:{encode_key_component(venue_name)}"


def make_organizer_key(*, name: str) -> str:
    return f"org:v1:{encode_key_component(name)}"


def make_event_key(
    *,
    source_name: str,
    starts_at: datetime,
    occurrence_id: str | None = None,
    source_event_id: str | None = None,
    title: str | None = None,
    venue_key: str | None = None,
) -> str:
    return derive_event_identity(
        source_name=source_name,
        starts_at=starts_at,
        occurrence_id=occurrence_id,
        source_event_id=source_event_id,
        title=title,
        venue_key=venue_key,
    ).event_key
