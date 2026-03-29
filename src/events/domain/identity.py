from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from string import ascii_letters, digits
from types import MappingProxyType
from unicodedata import normalize
from urllib.parse import quote

SOURCE_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
UNRESERVED = ascii_letters + digits + "-._~"
FALLBACK_NORMALIZATION_VERSION = "v1"


class IdentityKind(StrEnum):
    OCCURRENCE_ID = "occurrence_id"
    SOURCE_EVENT_ID_STARTS_AT = "source_event_id_starts_at"
    FALLBACK_HASH = "fallback_hash"


@dataclass(frozen=True, slots=True)
class EventIdentity:
    event_key: str
    identity_kind: IdentityKind
    identity_inputs: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identity_inputs",
            MappingProxyType(dict(self.identity_inputs)),
        )


def normalize_component_text(value: str) -> str:
    normalized = normalize("NFKC", value)
    collapsed = " ".join(normalized.strip().split())
    return collapsed.casefold()


def encode_key_component(value: str) -> str:
    return quote(normalize_component_text(value), safe=UNRESERVED)


def normalize_fallback_title(value: str) -> str:
    return normalize_component_text(value)


def encode_source_native_id(value: str) -> str:
    return quote(value, safe=UNRESERVED)


def encode_starts_at_component(starts_at_utc: str) -> str:
    return quote(starts_at_utc, safe=UNRESERVED)


def format_starts_at_utc(starts_at: datetime) -> str:
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("starts_at must be timezone-aware")
    return (
        starts_at.astimezone(UTC)
        .replace(microsecond=0)
        .strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        )
    )


def _require_source_name(source_name: str) -> None:
    if not SOURCE_NAME_RE.fullmatch(source_name):
        raise ValueError("source_name must be a stable internal identifier")


def _require_non_blank_identifier(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{name} must be non-blank")
    return value


def _require_non_blank_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{name} must be non-blank")
    return value


def _fallback_payload(
    *,
    source_name: str,
    normalized_title: str,
    starts_at_utc: str,
    venue_key: str,
) -> dict[str, str]:
    return {
        "normalization_version": FALLBACK_NORMALIZATION_VERSION,
        "normalized_title": normalized_title,
        "source_name": source_name,
        "starts_at_utc": starts_at_utc,
        "venue_key": venue_key,
    }


def derive_event_identity(
    *,
    source_name: str,
    starts_at: datetime,
    occurrence_id: str | None = None,
    source_event_id: str | None = None,
    title: str | None = None,
    venue_key: str | None = None,
) -> EventIdentity:
    _require_source_name(source_name)
    prefix = f"event:v1:{source_name}"
    starts_at_utc = format_starts_at_utc(starts_at)
    occurrence_id = _require_non_blank_identifier(
        "occurrence_id", occurrence_id
    )
    source_event_id = _require_non_blank_identifier(
        "source_event_id", source_event_id
    )
    title = _require_non_blank_text("title", title)
    venue_key = _require_non_blank_text("venue_key", venue_key)

    if occurrence_id:
        return EventIdentity(
            event_key=f"{prefix}:occ:{encode_source_native_id(occurrence_id)}",
            identity_kind=IdentityKind.OCCURRENCE_ID,
            identity_inputs={
                "source_name": source_name,
                "occurrence_id": occurrence_id,
            },
        )

    if source_event_id:
        return EventIdentity(
            event_key=(
                f"{prefix}:src:{encode_source_native_id(source_event_id)}:"
                f"{encode_starts_at_component(starts_at_utc)}"
            ),
            identity_kind=IdentityKind.SOURCE_EVENT_ID_STARTS_AT,
            identity_inputs={
                "source_name": source_name,
                "source_event_id": source_event_id,
                "starts_at_utc": starts_at_utc,
            },
        )

    if not title or not venue_key:
        raise ValueError(
            "title and venue_key are required for fallback event keys"
        )

    normalized_title = normalize_fallback_title(title)
    payload = _fallback_payload(
        source_name=source_name,
        normalized_title=normalized_title,
        starts_at_utc=starts_at_utc,
        venue_key=venue_key,
    )
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = sha256(serialized).hexdigest()
    return EventIdentity(
        event_key=f"{prefix}:hash:{digest}",
        identity_kind=IdentityKind.FALLBACK_HASH,
        identity_inputs=payload,
    )
