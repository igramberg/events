from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from events.domain.identity import (
    SOURCE_NAME_RE,
    IdentityKind,
    derive_event_identity,
)
from events.domain.keys import (
    make_location_key,
    make_organizer_key,
    make_venue_key,
)
from events.domain.urls import require_absolute_url


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


class EventCategory(StrEnum):
    CONCERT = "concert"
    THEATER = "theater"
    EXHIBITION = "exhibition"
    MUSEUM_SPECIAL = "museum_special"
    FILM = "film"

    @classmethod
    def v0_categories(cls) -> set["EventCategory"]:
        return {cls.CONCERT, cls.THEATER}


IDENTITY_KEYS_BY_KIND = {
    IdentityKind.OCCURRENCE_ID: frozenset({"source_name", "occurrence_id"}),
    IdentityKind.SOURCE_EVENT_ID_STARTS_AT: frozenset(
        {"source_name", "source_event_id", "starts_at_utc"},
    ),
    IdentityKind.FALLBACK_HASH: frozenset(
        {
            "source_name",
            "normalized_title",
            "starts_at_utc",
            "venue_key",
            "normalization_version",
        },
    ),
}


@dataclass(frozen=True, slots=True)
class Location:
    location_key: str
    city: str
    region: str
    country_code: str

    def __post_init__(self) -> None:
        _require_non_empty("location_key", self.location_key)
        _require_non_empty("city", self.city)
        _require_non_empty("region", self.region)
        _require_non_empty("country_code", self.country_code)
        if self.location_key != make_location_key(
            city=self.city,
            region=self.region,
            country_code=self.country_code,
        ):
            raise ValueError(
                "location_key must match canonical location fields"
            )


@dataclass(frozen=True, slots=True)
class Venue:
    venue_key: str
    venue_name: str
    location: Location

    def __post_init__(self) -> None:
        _require_non_empty("venue_key", self.venue_key)
        _require_non_empty("venue_name", self.venue_name)
        if self.venue_key != make_venue_key(
            location_key=self.location.location_key,
            venue_name=self.venue_name,
        ):
            raise ValueError("venue_key must match canonical venue fields")


@dataclass(frozen=True, slots=True)
class Organizer:
    organizer_key: str
    name: str

    def __post_init__(self) -> None:
        _require_non_empty("organizer_key", self.organizer_key)
        _require_non_empty("name", self.name)
        if self.organizer_key != make_organizer_key(name=self.name):
            raise ValueError(
                "organizer_key must match canonical organizer fields"
            )


@dataclass(frozen=True, slots=True)
class Event:
    event_key: str
    identity_kind: IdentityKind
    identity_inputs: Mapping[str, str]
    title: str
    category: EventCategory
    venue: Venue
    organizer: Organizer | None
    starts_at: datetime
    source_url: str
    source_event_id: str | None
    source_name: str
    description: str | None = None
    performers: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("event_key", self.event_key)
        _require_non_empty("title", self.title)
        _require_non_empty("source_url", self.source_url)
        _require_non_empty("source_name", self.source_name)
        if not self.identity_inputs:
            raise ValueError("identity_inputs must be non-empty")
        frozen_identity_inputs = MappingProxyType(dict(self.identity_inputs))
        object.__setattr__(self, "identity_inputs", frozen_identity_inputs)
        require_absolute_url(self.source_url)
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must be timezone-aware")
        if not SOURCE_NAME_RE.fullmatch(self.source_name):
            raise ValueError("source_name must be a stable internal identifier")
        if frozen_identity_inputs.get("source_name") != self.source_name:
            raise ValueError(
                "identity_inputs source_name must match source_name"
            )
        required_keys = IDENTITY_KEYS_BY_KIND[self.identity_kind]
        if set(frozen_identity_inputs) != required_keys:
            raise ValueError(
                "identity_inputs must match identity_kind requirements"
            )
        expected_identity = self._derive_expected_identity()
        if expected_identity.event_key != self.event_key:
            raise ValueError(
                "event_key must match identity_kind and identity_inputs"
            )
        if dict(expected_identity.identity_inputs) != dict(
            frozen_identity_inputs
        ):
            raise ValueError(
                "identity_inputs must match derived identity inputs"
            )
        if (
            self.identity_kind is IdentityKind.SOURCE_EVENT_ID_STARTS_AT
            and self.source_event_id
            != frozen_identity_inputs["source_event_id"]
        ):
            raise ValueError("source_event_id must match identity_inputs")

    def _derive_expected_identity(self):
        match self.identity_kind:
            case IdentityKind.OCCURRENCE_ID:
                return derive_event_identity(
                    source_name=self.source_name,
                    starts_at=self.starts_at,
                    occurrence_id=self.identity_inputs["occurrence_id"],
                )
            case IdentityKind.SOURCE_EVENT_ID_STARTS_AT:
                return derive_event_identity(
                    source_name=self.source_name,
                    starts_at=self.starts_at,
                    source_event_id=self.identity_inputs["source_event_id"],
                )
            case IdentityKind.FALLBACK_HASH:
                return derive_event_identity(
                    source_name=self.source_name,
                    starts_at=self.starts_at,
                    title=self.title,
                    venue_key=self.venue.venue_key,
                )
