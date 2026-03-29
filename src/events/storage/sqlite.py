from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Sequence

from sqlalchemy import JSON
from sqlalchemy import Column
from sqlalchemy import Index
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import create_engine
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.sql import and_
from sqlalchemy.sql import or_
from sqlalchemy.dialects.sqlite import insert

from events.domain import WeekWindow
from events.domain.models import Event
from events.domain.models import EventCategory
from events.domain.models import IdentityKind
from events.domain.models import Location
from events.domain.models import Organizer
from events.domain.models import Venue
from events.storage.repository import StorageRepository


metadata = MetaData()


current_week_events = Table(
    "current_week_events",
    metadata,
    Column("event_key", String, primary_key=True),
    Column("identity_kind", String, nullable=False),
    Column("identity_inputs", String, nullable=False),
    Column("title", String, nullable=False),
    Column("category", String, nullable=False),
    Column("venue_key", String, nullable=False),
    Column("venue_name", String, nullable=False),
    Column("location_key", String, nullable=False),
    Column("city", String, nullable=False),
    Column("region", String, nullable=False),
    Column("country_code", String, nullable=False),
    Column("organizer_key", String, nullable=True),
    Column("organizer_name", String, nullable=True),
    Column("starts_at", String, nullable=False),
    Column("source_url", String, nullable=False),
    Column("source_name", String, nullable=False),
    Column("source_event_id", String, nullable=True),
    Column("description", String, nullable=True),
    Column("performers", JSON, nullable=False, default=list),
    Column("tags", JSON, nullable=False, default=list),
    Column("last_seen_at", String, nullable=False),
)
Index("idx_current_week_events_starts_at", current_week_events.c.starts_at)
Index("idx_current_week_events_last_seen_at", current_week_events.c.last_seen_at)


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)


def _require_aware(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return dt


def _require_utc(dt: datetime, name: str) -> datetime:
    _require_aware(dt, name)
    if dt.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be provided in UTC")
    return dt.astimezone(UTC)


def _to_utc(dt: datetime, name: str) -> datetime:
    return _require_aware(dt, name).astimezone(UTC)


def serialize_starts_at(dt: datetime) -> str:
    utc_dt = _to_utc(dt, "starts_at")
    return utc_dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def serialize_refresh_timestamp(dt: datetime) -> str:
    utc_dt = _require_utc(dt, "refresh_timestamp")
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def deserialize_starts_at(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def deserialize_last_seen_at(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def utc_bounds_for_window(window: WeekWindow) -> tuple[str, str]:
    start_utc = _to_utc(window.start, "week_window.start")
    end_utc = _to_utc(window.end, "week_window.end")
    return (
        start_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _serialize_identity_inputs(identity_inputs: dict[str, str]) -> str:
    return json.dumps(identity_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _serialize_sequence(values: Sequence[str]) -> list[str]:
    return list(values)


def _row_to_event(row) -> Event:
    location = Location(
        location_key=row.location_key,
        city=row.city,
        region=row.region,
        country_code=row.country_code,
    )
    venue = Venue(
        venue_key=row.venue_key,
        venue_name=row.venue_name,
        location=location,
    )
    organizer = None
    if row.organizer_key and row.organizer_name:
        organizer = Organizer(organizer_key=row.organizer_key, name=row.organizer_name)

    return Event(
        event_key=row.event_key,
        identity_kind=IdentityKind(row.identity_kind),
        identity_inputs=json.loads(row.identity_inputs),
        title=row.title,
        category=EventCategory(row.category),
        venue=venue,
        organizer=organizer,
        starts_at=deserialize_starts_at(row.starts_at),
        source_url=row.source_url,
        source_name=row.source_name,
        source_event_id=row.source_event_id,
        description=row.description,
        performers=tuple(row.performers or ()),
        tags=tuple(row.tags or ()),
    )


@dataclass
class SqliteStorageRepository(StorageRepository):
    engine: Engine

    def upsert_events(self, events: Sequence[Event], refresh_timestamp: datetime) -> None:
        refresh_ts_str = serialize_refresh_timestamp(refresh_timestamp)
        with self.engine.begin() as conn:
            for event in events:
                starts_at_str = serialize_starts_at(event.starts_at)
                identity_inputs_serialized = _serialize_identity_inputs(dict(event.identity_inputs))

                existing = conn.execute(
                    select(
                        current_week_events.c.identity_kind,
                        current_week_events.c.identity_inputs,
                    ).where(current_week_events.c.event_key == event.event_key),
                ).fetchone()
                if existing:
                    if (
                        existing.identity_kind != event.identity_kind
                        or existing.identity_inputs != identity_inputs_serialized
                    ):
                        raise ValueError("identity material mismatch for event_key")

                stmt = insert(current_week_events).values(
                    event_key=event.event_key,
                    identity_kind=event.identity_kind.value,
                    identity_inputs=identity_inputs_serialized,
                    title=event.title,
                    category=event.category.value,
                    venue_key=event.venue.venue_key,
                    venue_name=event.venue.venue_name,
                    location_key=event.venue.location.location_key,
                    city=event.venue.location.city,
                    region=event.venue.location.region,
                    country_code=event.venue.location.country_code,
                    organizer_key=event.organizer.organizer_key if event.organizer else None,
                    organizer_name=event.organizer.name if event.organizer else None,
                    starts_at=starts_at_str,
                    source_url=event.source_url,
                    source_name=event.source_name,
                    source_event_id=event.source_event_id,
                    description=event.description,
                    performers=_serialize_sequence(event.performers),
                    tags=_serialize_sequence(event.tags),
                    last_seen_at=refresh_ts_str,
                )

                update_fields = dict(
                    title=event.title,
                    category=event.category.value,
                    venue_key=event.venue.venue_key,
                    venue_name=event.venue.venue_name,
                    location_key=event.venue.location.location_key,
                    city=event.venue.location.city,
                    region=event.venue.location.region,
                    country_code=event.venue.location.country_code,
                    organizer_key=event.organizer.organizer_key if event.organizer else None,
                    organizer_name=event.organizer.name if event.organizer else None,
                    starts_at=starts_at_str,
                    source_url=event.source_url,
                    source_name=event.source_name,
                    source_event_id=event.source_event_id,
                    description=event.description,
                    performers=_serialize_sequence(event.performers),
                    tags=_serialize_sequence(event.tags),
                    last_seen_at=refresh_ts_str,
                )

                stmt = stmt.on_conflict_do_update(
                    index_elements=[current_week_events.c.event_key],
                    set_=update_fields,
                )
                conn.execute(stmt)

    def get_events_for_window(self, window: WeekWindow) -> Sequence[Event]:
        start_utc, end_utc = utc_bounds_for_window(window)
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(current_week_events)
                .where(
                    and_(
                        current_week_events.c.starts_at >= start_utc,
                        current_week_events.c.starts_at < end_utc,
                    ),
                )
                .order_by(
                    current_week_events.c.starts_at,
                    current_week_events.c.venue_name,
                    current_week_events.c.event_key,
                )
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def prune_stale_events(self, window: WeekWindow, refresh_timestamp: datetime) -> None:
        start_utc, end_utc = utc_bounds_for_window(window)
        refresh_ts_str = serialize_refresh_timestamp(refresh_timestamp)
        with self.engine.begin() as conn:
            conn.execute(
                delete(current_week_events).where(
                    or_(
                        current_week_events.c.last_seen_at < refresh_ts_str,
                        current_week_events.c.starts_at < start_utc,
                        current_week_events.c.starts_at >= end_utc,
                    ),
                ),
            )


def build_sqlite_repository(database_url: str = "sqlite+pysqlite:///:memory:") -> SqliteStorageRepository:
    engine = create_engine(database_url, future=True)
    create_tables(engine)
    return SqliteStorageRepository(engine=engine)
