from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from events.domain.identity import SOURCE_NAME_RE
from events.domain.models import EventCategory
from events.domain.urls import require_absolute_url


if TYPE_CHECKING:
    from zoneinfo import ZoneInfo


def _require_non_blank(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} must be non-blank")
    return trimmed


def _require_source_name(source_name: str) -> str:
    normalized = _require_non_blank("source_name", source_name)
    if not SOURCE_NAME_RE.fullmatch(normalized):
        raise ValueError("source_name must be a stable internal identifier")
    return normalized


def _require_absolute_http_url(name: str, url: str) -> str:
    normalized = _require_non_blank(name, url)
    parts = require_absolute_url(normalized)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    return normalized


def _freeze_unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    if (
        isinstance(values, str)
        or isinstance(values, Mapping)
        or not isinstance(values, Sequence)
    ):
        raise ValueError("string collections must be provided as a sequence of strings")
    frozen: list[str] = []
    seen: set[str] = set()
    for value in values:
        trimmed = _require_non_blank("collection item", value)
        if trimmed in seen:
            continue
        seen.add(trimmed)
        frozen.append(trimmed)
    return tuple(frozen)


def _freeze_typed_sequence(name: str, values: Sequence[object], expected_type: type[object]) -> tuple[object, ...]:
    if isinstance(values, str) or isinstance(values, Mapping) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence")
    frozen = tuple(values)
    for value in frozen:
        if not isinstance(value, expected_type):
            raise ValueError(f"{name} must contain only {expected_type.__name__} values")
    return frozen


class ParsePhase(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"


class ParseSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SourceRequest:
    source_name: str
    requested_url: str
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_name", _require_source_name(self.source_name))
        object.__setattr__(
            self,
            "requested_url",
            _require_absolute_http_url("requested_url", self.requested_url),
        )
        if self.headers is None:
            return
        if not isinstance(self.headers, Mapping):
            raise ValueError("headers must be a mapping of string pairs")
        normalized_headers = {
            _require_non_blank("header name", key): _require_non_blank("header value", value)
            for key, value in dict(self.headers).items()
        }
        object.__setattr__(self, "headers", MappingProxyType(normalized_headers))


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_name: str
    requested_url: str
    fetched_url: str
    content: str
    content_type: str | None
    status_code: int
    headers: Mapping[str, str] | None
    fetched_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_name", _require_source_name(self.source_name))
        if not isinstance(self.status_code, int):
            raise ValueError("status_code must be an int")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
        if self.content_type is not None and not isinstance(self.content_type, str):
            raise ValueError("content_type must be a string when present")
        if not isinstance(self.fetched_at, datetime):
            raise ValueError("fetched_at must be a datetime")
        object.__setattr__(
            self,
            "requested_url",
            _require_absolute_http_url("requested_url", self.requested_url),
        )
        object.__setattr__(
            self,
            "fetched_url",
            _require_absolute_http_url("fetched_url", self.fetched_url),
        )
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        if self.fetched_at.utcoffset() != UTC.utcoffset(self.fetched_at):
            raise ValueError("fetched_at must be UTC")
        if self.headers is not None:
            if not isinstance(self.headers, Mapping):
                raise ValueError("headers must be a mapping of string pairs")
            normalized_headers = {
                _require_non_blank("header name", key): _require_non_blank("header value", value)
                for key, value in dict(self.headers).items()
            }
            object.__setattr__(self, "headers", MappingProxyType(normalized_headers))


@dataclass(frozen=True, slots=True)
class CandidateEventInput:
    title: str | None
    category: EventCategory | None
    schema_types: Sequence[str]
    starts_at: datetime | None
    source_url: str
    source_name: str
    occurrence_id: str | None = None
    source_event_id: str | None = None
    venue_name: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    organizer_name: str | None = None
    description: str | None = None
    performers: Sequence[str] = ()
    tags: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_name", _require_source_name(self.source_name))
        object.__setattr__(self, "source_url", _require_absolute_http_url("source_url", self.source_url))
        if self.starts_at is not None and not isinstance(self.starts_at, datetime):
            raise ValueError("starts_at must be a datetime when present")
        if self.category is not None and not isinstance(self.category, EventCategory):
            raise ValueError("category must be EventCategory or None")
        if self.starts_at is not None and (
            self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None
        ):
            raise ValueError("starts_at must be timezone-aware when present")

        if self.title is not None:
            object.__setattr__(self, "title", _require_non_blank("title", self.title))
        if self.occurrence_id is not None:
            object.__setattr__(
                self,
                "occurrence_id",
                _require_non_blank("occurrence_id", self.occurrence_id),
            )
        if self.source_event_id is not None:
            object.__setattr__(
                self,
                "source_event_id",
                _require_non_blank("source_event_id", self.source_event_id),
            )
        for field_name in (
            "venue_name",
            "city",
            "region",
            "country_code",
            "organizer_name",
            "description",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_non_blank(field_name, value))

        object.__setattr__(self, "schema_types", _freeze_unique_strings(self.schema_types))
        object.__setattr__(self, "performers", _freeze_unique_strings(self.performers))
        object.__setattr__(self, "tags", _freeze_unique_strings(self.tags))


@dataclass(frozen=True, slots=True)
class ParseIssue:
    code: str
    phase: ParsePhase
    severity: ParseSeverity
    message: str
    source_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_non_blank("code", self.code))
        object.__setattr__(self, "message", _require_non_blank("message", self.message))
        if not isinstance(self.phase, ParsePhase):
            raise ValueError("phase must be ParsePhase")
        if not isinstance(self.severity, ParseSeverity):
            raise ValueError("severity must be ParseSeverity")
        if self.source_ref is not None:
            object.__setattr__(self, "source_ref", _require_non_blank("source_ref", self.source_ref))


@dataclass(frozen=True, slots=True)
class ParseResult:
    candidates: Sequence[CandidateEventInput]
    issues: Sequence[ParseIssue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidates",
            _freeze_typed_sequence("candidates", self.candidates, CandidateEventInput),
        )
        object.__setattr__(
            self,
            "issues",
            _freeze_typed_sequence("issues", self.issues, ParseIssue),
        )


if TYPE_CHECKING:
    from typing import Protocol

    class SourceAdapter(Protocol):
        source_name: str
        default_tz: ZoneInfo | None

        def build_request(self) -> SourceRequest: ...

        def parse(self, source_document: SourceDocument) -> ParseResult: ...
