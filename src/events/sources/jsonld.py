from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from events.sources.models import CandidateEventInput
from events.sources.models import ParseIssue
from events.sources.models import ParsePhase
from events.sources.models import ParseResult
from events.sources.models import ParseSeverity
from events.sources.models import SourceDocument


EVENT_TYPES = {"Event", "MusicEvent", "PerformingArtsEvent", "TheaterEvent"}
START_DATE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:T(?P<time>\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(?P<offset>Z|[+-]\d{2}:\d{2})?)?$"
)


@dataclass(frozen=True, slots=True)
class JsonLdExtractorOptions:
    include_non_event_node_skipped: bool = False


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._chunks: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): value for key, value in attrs}
        script_type = (attributes.get("type") or "").strip().lower()
        if script_type.startswith("application/ld+json"):
            self._capture = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture:
            self.scripts.append("".join(self._chunks))
            self._capture = False
            self._chunks = []


class JsonLdExtractor:
    def __init__(
        self,
        *,
        default_tz: ZoneInfo | None,
        options: JsonLdExtractorOptions | None = None,
    ) -> None:
        self.default_tz = default_tz
        self.options = options or JsonLdExtractorOptions()

    def parse(self, source_document: SourceDocument) -> ParseResult:
        parser = _JsonLdScriptParser()
        parser.feed(source_document.content)

        candidates: list[CandidateEventInput] = []
        issues: list[ParseIssue] = []
        for script_index, raw_script in enumerate(parser.scripts):
            source_ref = f"script[{script_index}]"
            try:
                payload = json.loads(raw_script)
            except json.JSONDecodeError as error:
                issues.append(
                    self._issue(
                        code="invalid_jsonld",
                        message=f"Invalid JSON-LD: {error.msg}",
                        source_ref=source_ref,
                    )
                )
                continue

            nodes = self._nodes_for_payload(payload)
            if nodes is None:
                issues.append(
                    self._issue(
                        code="unsupported_jsonld_shape",
                        message="JSON-LD top-level value must be an object, array, or object containing @graph",
                        source_ref=source_ref,
                    )
                )
                continue

            for node in nodes:
                if not isinstance(node, dict):
                    if self.options.include_non_event_node_skipped:
                        issues.append(
                            self._issue(
                                code="non_event_node_skipped",
                                message="Skipped non-object JSON-LD node",
                                source_ref=source_ref,
                            )
                        )
                    continue
                candidates_for_node, issues_for_node = self._extract_node(
                    node=node,
                    script_index=script_index,
                    source_document=source_document,
                )
                candidates.extend(candidates_for_node)
                issues.extend(issues_for_node)
        return ParseResult(candidates=tuple(candidates), issues=tuple(issues))

    def _extract_node(
        self,
        *,
        node: dict[str, object],
        script_index: int,
        source_document: SourceDocument,
    ) -> tuple[list[CandidateEventInput], list[ParseIssue]]:
        schema_types = _normalize_schema_types(node.get("@type"))
        source_ref = _source_ref(script_index=script_index, node=node)
        if not any(schema_type in EVENT_TYPES for schema_type in schema_types):
            if self.options.include_non_event_node_skipped:
                return [], [
                    self._issue(
                        code="non_event_node_skipped",
                        message="Skipped non-event JSON-LD node",
                        source_ref=source_ref,
                    )
                ]
            return [], []

        title = _first_usable_string(node.get("name"))
        description = _first_usable_string(node.get("description"))
        venue_name, city, region, country_code = _extract_location(node.get("location"))
        organizer_name = _extract_name_field(node.get("organizer"))
        performers = _extract_performers(node.get("performer"), node.get("performers"))
        tags = _extract_tags(node.get("keywords"))
        source_url, had_failed_url = _resolve_source_url(
            node=node,
            fetched_url=source_document.fetched_url,
        )

        meaningful = any(
            (
                title is not None,
                _has_non_blank_string(node.get("startDate")),
                _has_meaningful_url_candidate(node.get("url")),
                _has_meaningful_url_candidate(node.get("@id")),
                venue_name is not None,
                organizer_name is not None,
                description is not None,
                bool(performers),
                bool(tags),
            )
        )
        if not meaningful:
            return [], []

        issues: list[ParseIssue] = []
        starts_at = None
        if "startDate" not in node:
            issues.append(
                self._issue(
                    code="missing_start_date",
                    message="Missing startDate for event-like node",
                    source_ref=source_ref,
                )
            )
        else:
            starts_at, start_issue = _parse_start_date(
                node.get("startDate"),
                default_tz=self.default_tz,
            )
            if start_issue is not None:
                issues.append(
                    self._issue(
                        code=start_issue,
                        message=_issue_message_for_start_date(start_issue),
                        source_ref=source_ref,
                    )
                )

        if had_failed_url:
            issues.append(
                self._issue(
                    code="url_resolution_failed",
                    message="Node-specific URL candidates were present but unusable",
                    source_ref=source_ref,
                )
            )

        candidate = CandidateEventInput(
            title=title,
            category=None,
            schema_types=schema_types,
            starts_at=starts_at,
            source_url=source_url,
            source_name=source_document.source_name,
            venue_name=venue_name,
            city=city,
            region=region,
            country_code=country_code,
            organizer_name=organizer_name,
            description=description,
            performers=performers,
            tags=tags,
        )
        return [candidate], issues

    def _nodes_for_payload(self, payload: object) -> list[object] | None:
        if isinstance(payload, dict):
            graph = payload.get("@graph")
            if graph is not None:
                if isinstance(graph, list):
                    return list(graph)
                if isinstance(graph, dict):
                    return [graph]
                return None
            return [payload]
        if isinstance(payload, list):
            return list(payload)
        return None

    def _issue(self, *, code: str, message: str, source_ref: str) -> ParseIssue:
        return ParseIssue(
            code=code,
            phase=ParsePhase.PARSE,
            severity=ParseSeverity.WARNING if code not in {"invalid_jsonld", "unsupported_jsonld_shape"} else ParseSeverity.ERROR,
            message=message,
            source_ref=source_ref,
        )


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _first_usable_string(value: object) -> str | None:
    if isinstance(value, str):
        return _optional_string(value)
    if isinstance(value, list):
        for item in value:
            usable = _first_usable_string(item)
            if usable is not None:
                return usable
    return None


def _has_non_blank_string(value: object) -> bool:
    return _first_usable_string(value) is not None


def _has_meaningful_url_candidate(value: object) -> bool:
    if isinstance(value, dict):
        return _has_meaningful_url_candidate(value.get("url")) or _has_meaningful_url_candidate(
            value.get("@id")
        )
    if isinstance(value, list):
        return any(_has_meaningful_url_candidate(item) for item in value)
    return _is_url_candidate_id(value)


def _has_url_candidate(value: object, *, field_name: str) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return any(_has_url_candidate(item, field_name=field_name) for item in value)
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    if not trimmed:
        return False
    if field_name == "@id":
        return _is_url_candidate_id(trimmed)
    return True


def _normalize_schema_types(value: object) -> tuple[str, ...]:
    raw_values: list[str] = []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = [item for item in value if isinstance(item, str)]
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in raw_values:
        trimmed = raw.strip()
        if not trimmed:
            continue
        if trimmed.startswith("schema:"):
            trimmed = trimmed.removeprefix("schema:")
        elif trimmed.startswith("http://schema.org/"):
            trimmed = trimmed.removeprefix("http://schema.org/")
            trimmed = trimmed.rstrip("/")
        elif trimmed.startswith("https://schema.org/"):
            trimmed = trimmed.removeprefix("https://schema.org/")
            trimmed = trimmed.rstrip("/")
        if "/" in trimmed:
            trimmed = trimmed.rsplit("/", 1)[-1]
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return tuple(normalized)


def _extract_name_field(value: object) -> str | None:
    if isinstance(value, str):
        return _optional_string(value)
    if isinstance(value, dict):
        return _first_usable_string(value.get("name"))
    if isinstance(value, list):
        for item in value:
            name = _extract_name_field(item)
            if name is not None:
                return name
    return None


def _extract_location(value: object) -> tuple[str | None, str | None, str | None, str | None]:
    if isinstance(value, str):
        return _optional_string(value), None, None, None
    if isinstance(value, list):
        venue_name = None
        city = None
        region = None
        country_code = None
        for item in value:
            extracted_venue, extracted_city, extracted_region, extracted_country = _extract_location(item)
            if venue_name is None:
                venue_name = extracted_venue
            if city is None:
                city = extracted_city
            if region is None:
                region = extracted_region
            if country_code is None:
                country_code = extracted_country
            if all(part is not None for part in (venue_name, city, region, country_code)):
                break
        return venue_name, city, region, country_code
    if not isinstance(value, dict):
        return None, None, None, None
    venue_name = _first_usable_string(value.get("name"))
    address = value.get("address")
    city, region, country_code = _extract_address_fields(address)
    return venue_name, city, region, country_code


def _extract_address_fields(value: object) -> tuple[str | None, str | None, str | None]:
    if isinstance(value, list):
        city = None
        region = None
        country_code = None
        for item in value:
            extracted_city, extracted_region, extracted_country = _extract_address_fields(item)
            if city is None:
                city = extracted_city
            if region is None:
                region = extracted_region
            if country_code is None:
                country_code = extracted_country
            if all(part is not None for part in (city, region, country_code)):
                break
        return city, region, country_code
    if not isinstance(value, dict):
        return None, None, None
    city = _first_usable_string(value.get("addressLocality"))
    region = _first_normalized_value(value.get("addressRegion"), _normalize_region)
    country_code = _first_normalized_value(
        value.get("addressCountry"),
        _normalize_country_code,
    )
    return city, region, country_code


def _first_normalized_value(
    value: object,
    normalizer: Callable[[object], str | None],
) -> str | None:
    if isinstance(value, list):
        for item in value:
            normalized = _first_normalized_value(item, normalizer)
            if normalized is not None:
                return normalized
        return None
    return normalizer(value)


def _normalize_region(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    upper = text.upper()
    return upper if re.fullmatch(r"[A-Z]{2,3}", upper) else None


def _normalize_country_code(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    upper = text.upper()
    return upper if re.fullmatch(r"[A-Z]{2}", upper) else None


def _extract_performers(*values: object) -> tuple[str, ...]:
    seen: set[str] = set()
    performers: list[str] = []

    def add(candidate: str | None) -> None:
        if candidate is None or candidate in seen:
            return
        seen.add(candidate)
        performers.append(candidate)

    def walk(value: object) -> None:
        if isinstance(value, str):
            add(_optional_string(value))
            return
        if isinstance(value, dict):
            add(_first_usable_string(value.get("name")))
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return tuple(performers)


def _extract_tags(value: object) -> tuple[str, ...]:
    seen: set[str] = set()
    tags: list[str] = []

    def add(candidate: str | None) -> None:
        if candidate is None or candidate in seen:
            return
        seen.add(candidate)
        tags.append(candidate)

    if isinstance(value, str):
        for item in value.split(","):
            add(_optional_string(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                add(_optional_string(item))
    return tuple(tags)


def _is_url_candidate_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    if not trimmed or trimmed.startswith("_:") or trimmed.startswith("#"):
        return False
    parts = urlsplit(trimmed)
    return not parts.scheme or parts.scheme in {"http", "https"}


def _resolve_source_url(
    *,
    node: dict[str, object],
    fetched_url: str,
) -> tuple[str, bool]:
    had_candidate = False
    for field_name in ("url", "@id"):
        candidates = _url_candidates(node.get(field_name), field_name=field_name)
        if not candidates and _has_url_candidate(node.get(field_name), field_name=field_name):
            had_candidate = True
        for candidate in candidates:
            had_candidate = True
            resolved = urljoin(fetched_url, candidate)
            parts = urlsplit(resolved)
            if parts.scheme in {"http", "https"} and parts.netloc:
                return resolved, False
    return fetched_url, had_candidate


def _url_candidates(value: object, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return ()
        if field_name == "@id" and not _is_url_candidate_id(trimmed):
            return ()
        return (trimmed,)
    if isinstance(value, list):
        candidates: list[str] = []
        for item in value:
            candidates.extend(_url_candidates(item, field_name=field_name))
        return tuple(candidates)
    if isinstance(value, dict):
        candidates: list[str] = []
        for nested_field_name in ("url", "@id"):
            candidates.extend(_url_candidates(value.get(nested_field_name), field_name=field_name))
        return tuple(candidates)
    return ()


def _parse_start_date(
    value: object,
    *,
    default_tz: ZoneInfo | None,
) -> tuple[datetime | None, str | None]:
    candidates = _start_date_string_candidates(value)
    if not candidates:
        return None, "invalid_start_date"

    first_issue: str | None = None
    for trimmed in candidates:
        parsed, issue = _parse_start_date_string(trimmed, default_tz=default_tz)
        if issue is None:
            return parsed, None
        if first_issue is None:
            first_issue = issue
    return None, first_issue or "invalid_start_date"


def _start_date_string_candidates(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        trimmed = value.strip()
        return (trimmed,) if trimmed else ()
    if isinstance(value, list):
        candidates: list[str] = []
        for item in value:
            candidates.extend(_start_date_string_candidates(item))
        return tuple(candidates)
    return ()


def _parse_start_date_string(
    trimmed: str,
    *,
    default_tz: ZoneInfo | None,
) -> tuple[datetime | None, str | None]:
    match = START_DATE_RE.fullmatch(trimmed)
    if match is None:
        return None, "invalid_start_date"
    if match.group("time") is None:
        return None, "date_only_start_date"
    if match.group("offset"):
        try:
            normalized = trimmed.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None, "invalid_start_date"
        return parsed, None
    try:
        naive = datetime.fromisoformat(trimmed)
    except ValueError:
        return None, "invalid_start_date"
    if default_tz is None:
        return None, "naive_start_date_no_tz"
    return _localize_naive_datetime(naive, default_tz)


def _localize_naive_datetime(
    naive: datetime,
    timezone: ZoneInfo,
) -> tuple[datetime | None, str | None]:
    fold0 = naive.replace(tzinfo=timezone, fold=0)
    fold1 = naive.replace(tzinfo=timezone, fold=1)
    roundtrip0 = fold0.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
    roundtrip1 = fold1.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
    valid0 = roundtrip0 == naive
    valid1 = roundtrip1 == naive
    if not valid0 and not valid1:
        return None, "nonexistent_local_start_date"
    if valid0 and valid1 and fold0.utcoffset() != fold1.utcoffset():
        return None, "ambiguous_local_start_date"
    return (fold0 if valid0 else fold1), None


def _issue_message_for_start_date(code: str) -> str:
    return {
        "naive_start_date_no_tz": "Naive startDate could not be localized without adapter timezone information",
        "date_only_start_date": "Date-only startDate is unschedulable in T3",
        "invalid_start_date": "startDate value is invalid for the locked T3 grammar",
        "ambiguous_local_start_date": "Naive startDate is ambiguous in the adapter timezone",
        "nonexistent_local_start_date": "Naive startDate does not exist in the adapter timezone",
    }[code]


def _source_ref(*, script_index: int, node: dict[str, object]) -> str:
    reference_ids = _url_candidates(node.get("@id"), field_name="@id")
    if reference_ids:
        return f"script[{script_index}] @id={reference_ids[0]}"
    name = _first_usable_string(node.get("name"))
    if name is not None:
        return f"script[{script_index}] name={name}"
    return f"script[{script_index}]"
