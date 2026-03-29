from __future__ import annotations

import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _source_document(*, content: str) -> object:
    from events.sources import SourceDocument

    return SourceDocument(
        source_name="example_source",
        requested_url="https://example.com/events",
        fetched_url="https://example.com/final/events",
        content=content,
        content_type="text/html",
        status_code=200,
        headers=None,
        fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
    )


class JsonLdExtractorTests(unittest.TestCase):
    def test_extracts_event_candidate_from_single_object_script(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <html>
              <head>
                <script type="application/ld+json">
                {
                  "@context": "https://schema.org",
                  "@type": ["schema:MusicEvent", "https://schema.org/Event"],
                  "name": "Example Show",
                  "startDate": "2026-03-29T20:00:00Z",
                  "url": "/shows/example",
                  "location": {
                    "name": "Roadrunner",
                    "address": {
                      "addressLocality": "Boston",
                      "addressRegion": "ma",
                      "addressCountry": "us"
                    }
                  },
                  "organizer": {"name": "Massive Co"},
                  "performer": [{"name": "Artist A"}, "Artist B"],
                  "keywords": "rock, indie"
                }
                </script>
              </head>
            </html>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("Example Show", candidate.title)
        self.assertIsNone(candidate.category)
        self.assertEqual(("MusicEvent", "Event"), candidate.schema_types)
        self.assertEqual(
            datetime(2026, 3, 29, 20, 0, 0, tzinfo=UTC),
            candidate.starts_at,
        )
        self.assertEqual(
            "https://example.com/shows/example", candidate.source_url
        )
        self.assertEqual("Roadrunner", candidate.venue_name)
        self.assertEqual("Boston", candidate.city)
        self.assertEqual("MA", candidate.region)
        self.assertEqual("US", candidate.country_code)
        self.assertEqual("Massive Co", candidate.organizer_name)
        self.assertEqual(("Artist A", "Artist B"), candidate.performers)
        self.assertEqual(("rock", "indie"), candidate.tags)

    def test_ignores_blank_schema_type_tails_after_normalization(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": ["https://schema.org/", "schema:", "https://schema.org/Event"],
                "name": "Schema Tail Event",
                "startDate": "2026-03-29T20:00:00Z"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(("Event",), result.candidates[0].schema_types)
        self.assertEqual("Schema Tail Event", result.candidates[0].title)

    def test_normalizes_trailing_slash_schema_type_url(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "https://schema.org/Event/",
                "name": "Trailing Slash Event",
                "startDate": "2026-03-29T20:00:00Z"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(("Event",), result.candidates[0].schema_types)
        self.assertEqual("Trailing Slash Event", result.candidates[0].title)

    def test_discovers_jsonld_script_with_charset_suffix(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json; charset=utf-8">
              {
                "@type": "Event",
                "name": "Charset Event",
                "startDate": "2026-03-29T20:00:00Z"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Charset Event", result.candidates[0].title)

    def test_extracts_event_candidate_from_top_level_array_script(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              [
                {"@type": "Place", "name": "Ignored Place"},
                {
                  "@type": "Event",
                  "name": "Array Event",
                  "startDate": "2026-03-29T20:00:00Z"
                }
              ]
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Array Event", result.candidates[0].title)
        self.assertEqual((), result.issues)

    def test_emits_invalid_jsonld_and_continues_to_later_scripts(self) -> None:
        from events.sources import ParsePhase, ParseSeverity
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">{ invalid }</script>
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Fallback Event",
                "startDate": "2026-03-29T21:00:00Z"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.issues))
        self.assertEqual("invalid_jsonld", result.issues[0].code)
        self.assertEqual("script[0]", result.issues[0].source_ref)
        self.assertEqual(ParsePhase.PARSE, result.issues[0].phase)
        self.assertEqual(ParseSeverity.ERROR, result.issues[0].severity)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Fallback Event", result.candidates[0].title)
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )

    def test_emits_unsupported_jsonld_shape_for_scalar_payload(self) -> None:
        from events.sources import ParsePhase, ParseSeverity
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              123
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        self.assertEqual("unsupported_jsonld_shape", result.issues[0].code)
        self.assertEqual("script[0]", result.issues[0].source_ref)
        self.assertEqual(ParsePhase.PARSE, result.issues[0].phase)
        self.assertEqual(ParseSeverity.ERROR, result.issues[0].severity)

    def test_emits_missing_start_date_for_event_like_node_above_threshold(
        self,
    ) -> None:
        from events.sources import ParsePhase, ParseSeverity
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {"@type": "Event", "name": "No Start Yet"}
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual("No Start Yet", result.candidates[0].title)
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual(1, len(result.issues))
        self.assertEqual("missing_start_date", result.issues[0].code)
        self.assertEqual(
            "script[0] name=No Start Yet", result.issues[0].source_ref
        )
        self.assertEqual(ParsePhase.PARSE, result.issues[0].phase)
        self.assertEqual(ParseSeverity.WARNING, result.issues[0].severity)

    def test_skips_event_like_node_below_threshold_without_issues(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {"@type": "Event"}
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual((), result.issues)

    def test_emits_naive_start_date_no_tz_when_default_timezone_is_missing(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Naive Event",
                "startDate": "2026-03-29T20:00:00"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual("naive_start_date_no_tz", result.issues[0].code)

    def test_emits_date_only_start_date_issue(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Date Only Event",
                "startDate": "2026-03-29"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual("date_only_start_date", result.issues[0].code)

    def test_emits_invalid_start_date_for_disallowed_format(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Bad Format Event",
                "startDate": "2026-03-29 20:00:00"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual("invalid_start_date", result.issues[0].code)

    def test_uses_first_parseable_start_date_from_list(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "List Start Event",
                "startDate": ["bad", "2026-03-29T20:00:00Z"]
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            datetime(2026, 3, 29, 20, 0, 0, tzinfo=UTC),
            result.candidates[0].starts_at,
        )

    def test_localizes_naive_start_date_with_default_timezone(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Localized Event",
                "startDate": "2026-03-29T20:00:00"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(
            default_tz=ZoneInfo("America/New_York"),
        ).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(
            ZoneInfo("America/New_York"),
            result.candidates[0].starts_at.tzinfo,
        )

    def test_emits_ambiguous_local_start_date_issue(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Ambiguous Event",
                "startDate": "2026-11-01T01:30:00"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(
            default_tz=ZoneInfo("America/New_York"),
        ).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual("ambiguous_local_start_date", result.issues[0].code)

    def test_emits_nonexistent_local_start_date_issue(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "MusicEvent",
                "name": "Missing Hour Event",
                "startDate": "2026-03-08T02:30:00"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(
            default_tz=ZoneInfo("America/New_York"),
        ).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertIsNone(result.candidates[0].starts_at)
        self.assertEqual("nonexistent_local_start_date", result.issues[0].code)

    def test_prefers_usable_at_id_over_bad_url_without_resolution_warning(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Identifier Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": "mailto:boxoffice@example.com",
                "@id": "/events/id-event"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(
            "https://example.com/events/id-event",
            result.candidates[0].source_url,
        )

    def test_uses_object_form_url_candidate(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Object Url Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": {"@id": "/events/object-url"}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/events/object-url",
            result.candidates[0].source_url,
        )

    def test_emits_url_resolution_failed_for_unusable_object_form_url(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Bad Object Url Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": {"@id": "mailto:boxoffice@example.com"}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)

    def test_emits_url_resolution_failed_for_malformed_object_form_url(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Malformed Object Url Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": {"bad": true}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)

    def test_emits_url_resolution_failed_for_empty_object_form_url(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Empty Object Url Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": {}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)

    def test_emits_url_resolution_failed_when_node_specific_urls_are_unusable(
        self,
    ) -> None:
        from events.sources import ParsePhase, ParseSeverity
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Fallback Url Event",
                "startDate": "2026-03-29T20:00:00Z",
                "url": "mailto:boxoffice@example.com",
                "@id": "#fragment"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)
        self.assertEqual(ParsePhase.PARSE, result.issues[0].phase)
        self.assertEqual(ParseSeverity.WARNING, result.issues[0].severity)

    def test_supports_graph_shape_without_dereferencing_related_nodes(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@graph": [
                  {
                    "@id": "/events/graph",
                    "@type": "PerformingArtsEvent",
                    "name": "Graph Event",
                    "startDate": "2026-03-29T20:00:00Z",
                    "location": {"@id": "#venue-1"}
                  },
                  {
                    "@id": "#venue-1",
                    "@type": "Place",
                    "name": "Graph Venue"
                  }
                ]
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Graph Event", result.candidates[0].title)
        self.assertIsNone(result.candidates[0].venue_name)

    def test_supports_object_valued_graph_shape(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@graph": {
                  "@type": "Event",
                  "name": "Object Graph Event",
                  "startDate": "2026-03-29T20:00:00Z"
                }
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Object Graph Event", result.candidates[0].title)

    def test_uses_first_usable_values_from_list_shaped_single_fields(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": [null, " ", "List Event"],
                "description": [{}, "Listed description"],
                "startDate": [42, "", "2026-03-29T20:00:00Z"],
                "url": [null, "mailto:boxoffice@example.com", "/events/list-event"],
                "location": {
                  "name": [null, "Roadrunner"],
                  "address": {
                    "addressLocality": [{}, "Boston"],
                    "addressRegion": ["Massachusetts", "ma"],
                    "addressCountry": ["usa", "us"]
                  }
                }
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("List Event", candidate.title)
        self.assertEqual("Listed description", candidate.description)
        self.assertEqual(
            datetime(2026, 3, 29, 20, 0, 0, tzinfo=UTC),
            candidate.starts_at,
        )
        self.assertEqual(
            "https://example.com/events/list-event", candidate.source_url
        )
        self.assertEqual("Roadrunner", candidate.venue_name)
        self.assertEqual("Boston", candidate.city)
        self.assertEqual("MA", candidate.region)
        self.assertEqual("US", candidate.country_code)

    def test_merges_location_list_per_field(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Merged Location Event",
                "startDate": "2026-03-29T20:00:00Z",
                "location": [
                  {"name": "Roadrunner"},
                  {
                    "address": {
                      "addressLocality": "Boston",
                      "addressRegion": "ma",
                      "addressCountry": "us"
                    }
                  }
                ]
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("Roadrunner", candidate.venue_name)
        self.assertEqual("Boston", candidate.city)
        self.assertEqual("MA", candidate.region)
        self.assertEqual("US", candidate.country_code)

    def test_accepts_list_shaped_organizer_name_in_object_form(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Organizer List Event",
                "startDate": "2026-03-29T20:00:00Z",
                "organizer": {"name": ["", "Live Nation"]}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual("Live Nation", result.candidates[0].organizer_name)

    def test_accepts_list_shaped_performer_name_in_object_form(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Performer List Event",
                "startDate": "2026-03-29T20:00:00Z",
                "performer": {"name": ["", "Artist A"]}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(("Artist A",), result.candidates[0].performers)

    def test_accepts_list_shaped_location_address(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "List Address Event",
                "startDate": "2026-03-29T20:00:00Z",
                "location": {
                  "name": "Roadrunner",
                  "address": [
                    {"addressLocality": "Boston"},
                    {"addressRegion": "ma", "addressCountry": "us"}
                  ]
                }
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("Roadrunner", candidate.venue_name)
        self.assertEqual("Boston", candidate.city)
        self.assertEqual("MA", candidate.region)
        self.assertEqual("US", candidate.country_code)

    def test_source_ref_uses_first_usable_list_shaped_name(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": ["", "Named From List"]
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.issues))
        self.assertEqual("missing_start_date", result.issues[0].code)
        self.assertEqual(
            "script[0] name=Named From List", result.issues[0].source_ref
        )

    def test_source_ref_uses_object_form_at_id(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "@id": {"@id": "/events/object-id"}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.issues))
        self.assertEqual("missing_start_date", result.issues[0].code)
        self.assertEqual(
            "script[0] @id=/events/object-id", result.issues[0].source_ref
        )

    def test_uses_first_usable_at_id_from_list_when_url_is_missing(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": ["Identifier Event"],
                "startDate": ["2026-03-29T20:00:00Z"],
                "@id": [null, "#fragment", "/events/list-id"]
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.issues)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/events/list-id",
            result.candidates[0].source_url,
        )

    def test_emits_url_resolution_failed_for_malformed_object_at_id(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Bad Identifier Event",
                "startDate": "2026-03-29T20:00:00Z",
                "@id": {"value": "/events/bad"}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)

    def test_emits_url_resolution_failed_for_empty_object_at_id(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Empty Object Identifier Event",
                "startDate": "2026-03-29T20:00:00Z",
                "@id": {}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events",
            result.candidates[0].source_url,
        )
        self.assertEqual(1, len(result.issues))
        self.assertEqual("url_resolution_failed", result.issues[0].code)

    def test_ignores_fragment_only_at_id_for_url_resolution_failure(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Fragment Event",
                "startDate": "2026-03-29T20:00:00Z",
                "@id": "#fragment-only"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events", result.candidates[0].source_url
        )
        self.assertEqual((), result.issues)

    def test_ignores_blank_node_at_id_for_url_resolution_failure(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "name": "Blank Node Event",
                "startDate": "2026-03-29T20:00:00Z",
                "@id": "_:b0"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            "https://example.com/final/events", result.candidates[0].source_url
        )
        self.assertEqual((), result.issues)

    def test_skips_event_like_node_with_only_unusable_url_string(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "url": "mailto:boxoffice@example.com"
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual((), result.issues)

    def test_skips_event_like_node_with_only_malformed_object_url(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "url": {}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual((), result.issues)

    def test_skips_event_like_node_with_only_malformed_object_at_id(
        self,
    ) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "@id": {}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual((), result.issues)

    def test_source_ref_prefers_at_id_over_name(self) -> None:
        from events.sources.jsonld import JsonLdExtractor

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {
                "@type": "Event",
                "@id": "/events/source-ref",
                "name": "Source Ref Event",
                "url": {"bad": true}
              }
            </script>
            """,
        )

        result = JsonLdExtractor(default_tz=None).parse(document)

        self.assertEqual(1, len(result.issues))
        self.assertEqual("missing_start_date", result.issues[0].code)
        self.assertEqual(
            "script[0] @id=/events/source-ref", result.issues[0].source_ref
        )

    def test_can_emit_non_event_node_skipped_in_debug_mode(self) -> None:
        from events.sources.jsonld import (
            JsonLdExtractor,
            JsonLdExtractorOptions,
        )

        document = _source_document(
            content="""
            <script type="application/ld+json">
              {"@type": "Place", "name": "Just A Place"}
            </script>
            """,
        )

        result = JsonLdExtractor(
            default_tz=None,
            options=JsonLdExtractorOptions(include_non_event_node_skipped=True),
        ).parse(document)

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        self.assertEqual("non_event_node_skipped", result.issues[0].code)


if __name__ == "__main__":
    unittest.main()
