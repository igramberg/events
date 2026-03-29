from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from events.domain.models import EventCategory


class SourceContractTests(unittest.TestCase):
    def test_source_request_requires_absolute_http_url(self) -> None:
        from events.sources import SourceRequest

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="example_source",
                requested_url="/relative",
            )

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="example_source",
                requested_url="ftp://example.com/feed",
            )

    def test_source_request_rejects_invalid_headers(self) -> None:
        from events.sources import SourceRequest

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="example_source",
                requested_url="https://example.com/feed",
                headers=[("accept", "text/html")],
            )

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="example_source",
                requested_url="https://example.com/feed",
                headers={1: "text/html"},
            )

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="example_source",
                requested_url="https://example.com/feed",
                headers={"accept": 1},
            )

    def test_source_models_reject_invalid_source_name(self) -> None:
        from events.sources import (
            CandidateEventInput,
            SourceDocument,
            SourceRequest,
        )

        with self.assertRaises(ValueError):
            SourceRequest(
                source_name="Example Source",
                requested_url="https://example.com/feed",
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="Example Source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types=("MusicEvent",),
                starts_at=None,
                source_url="https://example.com/show",
                source_name="Example Source",
            )

    def test_source_document_requires_timezone_aware_utc_timestamp(
        self,
    ) -> None:
        from events.sources import SourceDocument

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(
                    2026, 3, 29, 12, 0, 0, tzinfo=ZoneInfo("America/New_York")
                ),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code="200",
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content=None,
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=[],
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers={1: "text/html"},
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at="2026-03-29T12:00:00Z",
            )

        with self.assertRaises(ValueError):
            SourceDocument(
                source_name="example_source",
                requested_url="https://example.com/feed",
                fetched_url="https://example.com/feed",
                content="<html></html>",
                content_type=123,
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

    def test_source_document_freezes_headers(self) -> None:
        from events.sources import SourceDocument

        document = SourceDocument(
            source_name="example_source",
            requested_url="https://example.com/feed",
            fetched_url="https://example.com/feed",
            content="<html></html>",
            content_type="text/html",
            status_code=200,
            headers={"accept": "text/html"},
            fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual({"accept": "text/html"}, dict(document.headers or {}))
        with self.assertRaises(TypeError):
            assert document.headers is not None
            document.headers["x-test"] = "1"

    def test_candidate_event_input_validates_source_url_and_starts_at(
        self,
    ) -> None:
        from events.sources import CandidateEventInput

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=EventCategory.CONCERT,
                schema_types=("MusicEvent",),
                starts_at="2026-03-29T20:00:00Z",
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category="concert",
                schema_types=("MusicEvent",),
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=EventCategory.CONCERT,
                schema_types=("MusicEvent",),
                starts_at=None,
                source_url="ftp://example.com/show",
                source_name="example_source",
            )

    def test_candidate_event_input_freezes_collections(self) -> None:
        from events.sources import CandidateEventInput

        candidate = CandidateEventInput(
            title="Example",
            category=None,
            schema_types=["MusicEvent", "Event", "MusicEvent"],
            starts_at=None,
            source_url="https://example.com/show",
            source_name="example_source",
            performers=["Artist A", "Artist A", "Artist B"],
            tags=["rock", "rock", "indie"],
        )

        self.assertEqual(("MusicEvent", "Event"), candidate.schema_types)
        self.assertEqual(("Artist A", "Artist B"), candidate.performers)
        self.assertEqual(("rock", "indie"), candidate.tags)

    def test_candidate_event_input_rejects_string_collections(self) -> None:
        from events.sources import CandidateEventInput

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types="MusicEvent",
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types={"MusicEvent": True},
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types={"MusicEvent"},
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types=("MusicEvent", " "),
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

        with self.assertRaises(ValueError):
            CandidateEventInput(
                title="Example",
                category=None,
                schema_types=("MusicEvent", 1),
                starts_at=None,
                source_url="https://example.com/show",
                source_name="example_source",
            )

    def test_collect_returns_invalid_source_request_when_build_request_raises(
        self,
    ) -> None:
        from events.sources import collect

        @dataclass
        class BrokenAdapter:
            source_name: str = "broken_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                raise ValueError()

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(BrokenAdapter())

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        issue = result.issues[0]
        self.assertEqual("invalid_source_request", issue.code)
        self.assertEqual("fetch", issue.phase.value)
        self.assertEqual("error", issue.severity.value)
        self.assertEqual("Failed to build source request", issue.message)

    def test_collect_returns_invalid_source_request_on_source_name_mismatch(
        self,
    ) -> None:
        from events.sources import SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name="other_source",
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(ExampleAdapter())

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        issue = result.issues[0]
        self.assertEqual("invalid_source_request", issue.code)
        self.assertEqual("fetch", issue.phase.value)
        self.assertEqual("error", issue.severity.value)

    def test_collect_returns_invalid_source_request_for_non_source_request_object(
        self,
    ) -> None:
        from events.sources import collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return object()

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(ExampleAdapter())
        self.assertEqual("invalid_source_request", result.issues[0].code)

    def test_collect_returns_invalid_source_request_for_request_like_object_with_bad_headers(
        self,
    ) -> None:
        from events.sources import collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return type(
                    "RequestLike",
                    (),
                    {
                        "source_name": self.source_name,
                        "requested_url": "https://example.com/feed",
                        "headers": [],
                    },
                )()

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(ExampleAdapter())
        self.assertEqual("invalid_source_request", result.issues[0].code)

    def test_collect_returns_fetch_failed_on_transport_exception(self) -> None:
        from events.sources import SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        def failing_fetch(request):
            raise OSError("network down")

        result = collect(ExampleAdapter(), fetcher=failing_fetch)

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        issue = result.issues[0]
        self.assertEqual("fetch_failed", issue.code)
        self.assertEqual("fetch", issue.phase.value)
        self.assertEqual("error", issue.severity.value)

    def test_collect_returns_fetch_failed_when_fetcher_returns_non_source_document(
        self,
    ) -> None:
        from events.sources import SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(ExampleAdapter(), fetcher=lambda request: object())
        self.assertEqual("fetch_failed", result.issues[0].code)

    def test_collect_returns_fetch_failed_when_source_document_source_name_mismatches_request(
        self,
    ) -> None:
        from events.sources import SourceDocument, SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None
            parse_called: bool = False

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                self.parse_called = True
                raise AssertionError("parse should not run")

        adapter = ExampleAdapter()

        def fetch_wrong_source(request):
            return SourceDocument(
                source_name="other_source",
                requested_url=request.requested_url,
                fetched_url=request.requested_url,
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        result = collect(adapter, fetcher=fetch_wrong_source)

        self.assertFalse(adapter.parse_called)
        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        self.assertEqual("fetch_failed", result.issues[0].code)
        self.assertIn(
            "source_document source_name must match request source_name",
            result.issues[0].message,
        )

    def test_collect_returns_fetch_failed_for_blank_transport_error_message(
        self,
    ) -> None:
        from events.sources import SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        result = collect(
            ExampleAdapter(),
            fetcher=lambda request: (_ for _ in ()).throw(OSError()),
        )
        self.assertEqual("fetch_failed", result.issues[0].code)
        self.assertEqual("Fetch failed", result.issues[0].message)

    def test_collect_returns_http_non_2xx_and_skips_parse(self) -> None:
        from events.sources import SourceDocument, SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None
            parse_called: bool = False

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                self.parse_called = True
                return None

        adapter = ExampleAdapter()

        def fetch_non_2xx(request):
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=request.requested_url,
                content="not found",
                content_type="text/html",
                status_code=404,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        result = collect(adapter, fetcher=fetch_non_2xx)

        self.assertFalse(adapter.parse_called)
        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        issue = result.issues[0]
        self.assertEqual("http_non_2xx", issue.code)
        self.assertEqual("fetch", issue.phase.value)
        self.assertEqual("error", issue.severity.value)
        self.assertEqual("https://example.com/feed", issue.source_ref)

    def test_collect_discards_partial_results_on_unexpected_parse_exception(
        self,
    ) -> None:
        from events.sources import SourceDocument, SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise RuntimeError("boom")

        def fetch_ok(request):
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=request.requested_url,
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        result = collect(ExampleAdapter(), fetcher=fetch_ok)

        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        issue = result.issues[0]
        self.assertEqual("unexpected_parse_exception", issue.code)
        self.assertEqual("parse", issue.phase.value)
        self.assertEqual("error", issue.severity.value)
        self.assertEqual("https://example.com/feed", issue.source_ref)

    def test_collect_rejects_non_parse_result_return(self) -> None:
        from events.sources import SourceDocument, SourceRequest, collect

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                return object()

        def fetch_ok(request):
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=request.requested_url,
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        result = collect(ExampleAdapter(), fetcher=fetch_ok)
        self.assertEqual("unexpected_parse_exception", result.issues[0].code)

    def test_collect_rejects_candidates_with_mismatched_source_name(
        self,
    ) -> None:
        from events.sources import (
            CandidateEventInput,
            SourceDocument,
            SourceRequest,
            collect,
        )

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                return type("ParseResultBox", (), {})()

        adapter = ExampleAdapter()

        def fetch_ok(request):
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=request.requested_url,
                content="<html></html>",
                content_type="text/html",
                status_code=200,
                headers=None,
                fetched_at=datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
            )

        def parse_with_bad_source(source_document):
            from events.sources import ParseResult

            return ParseResult(
                candidates=(
                    CandidateEventInput(
                        title="Example",
                        category=EventCategory.CONCERT,
                        schema_types=("MusicEvent",),
                        starts_at=datetime(2026, 3, 29, 20, 0, 0, tzinfo=UTC),
                        source_url="https://example.com/show",
                        source_name="other_source",
                    ),
                ),
                issues=(),
            )

        adapter.parse = parse_with_bad_source  # type: ignore[method-assign]
        result = collect(adapter, fetcher=fetch_ok)
        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(result.issues))
        self.assertEqual("unexpected_parse_exception", result.issues[0].code)

    def test_fetch_treats_redirect_http_error_as_transport_failure(
        self,
    ) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import fetch

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
        )

        redirect_error = HTTPError(
            url="https://example.com/feed",
            code=302,
            msg="Found",
            hdrs=None,
            fp=BytesIO(),
        )

        opener = Mock()
        opener.open.side_effect = redirect_error

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            with self.assertRaises(HTTPError):
                fetch(request)
        redirect_error.close()

    def test_fetch_handles_http_error_without_headers_or_body(self) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import fetch

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
        )
        http_error = HTTPError(
            url="https://example.com/feed",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        opener = Mock()
        opener.open.side_effect = http_error

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            document = fetch(request)

        self.assertEqual(404, document.status_code)
        self.assertIsNone(document.headers)
        self.assertEqual("", document.content)

    def test_fetch_handles_non_redirect_http_error_and_preserves_metadata(
        self,
    ) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import fetch

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
        )
        http_error = HTTPError(
            url="https://example.com/final",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b"missing"),
        )
        opener = Mock()
        opener.open.side_effect = http_error

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            document = fetch(request)

        self.assertEqual("example_source", document.source_name)
        self.assertEqual("https://example.com/feed", document.requested_url)
        self.assertEqual("https://example.com/final", document.fetched_url)
        self.assertEqual(404, document.status_code)
        self.assertEqual(0, document.fetched_at.utcoffset().total_seconds())

    def test_fetch_decodes_success_response_using_declared_charset(
        self,
    ) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import fetch

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
        )

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.headers = Mock()
        response.headers.items.return_value = [
            ("content-type", "text/html; charset=iso-8859-1")
        ]
        response.headers.get_content_type.return_value = "text/html"
        response.headers.get_content_charset.return_value = "iso-8859-1"
        response.read.return_value = "caf\xe9".encode("latin-1")
        response.getcode.return_value = 200
        response.geturl.return_value = "https://example.com/final"

        opener = Mock()
        opener.open.return_value = response

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            document = fetch(request)

        self.assertEqual("café", document.content)

    def test_fetch_decodes_http_error_response_using_declared_charset(
        self,
    ) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import fetch

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
        )
        headers = Mock()
        headers.items.return_value = [
            ("content-type", "text/html; charset=iso-8859-1")
        ]
        headers.get_content_type.return_value = "text/html"
        headers.get_content_charset.return_value = "iso-8859-1"
        http_error = HTTPError(
            url="https://example.com/final",
            code=404,
            msg="Not Found",
            hdrs=headers,
            fp=BytesIO("caf\xe9".encode("latin-1")),
        )
        opener = Mock()
        opener.open.side_effect = http_error

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            document = fetch(request)

        self.assertEqual("café", document.content)

    def test_parse_result_rejects_non_candidate_iterables(self) -> None:
        from events.sources import (
            ParseIssue,
            ParsePhase,
            ParseResult,
            ParseSeverity,
        )

        with self.assertRaises(ValueError):
            ParseResult(candidates="abc", issues=())

        with self.assertRaises(ValueError):
            ParseResult(
                candidates=(),
                issues=(
                    ParseIssue(
                        code="fetch_failed",
                        phase=ParsePhase.FETCH,
                        severity=ParseSeverity.ERROR,
                        message="bad",
                    ),
                    "not-an-issue",
                ),
            )

    def test_parse_issue_validates_phase_and_severity(self) -> None:
        from events.sources import ParseIssue, ParsePhase, ParseSeverity

        with self.assertRaises(ValueError):
            ParseIssue(
                code="fetch_failed",
                phase="fetch",
                severity="error",
                message="bad",
            )

        with self.assertRaises(ValueError):
            ParseIssue(
                code=" ",
                phase="fetch",
                severity="error",
                message="bad",
            )

        with self.assertRaises(ValueError):
            ParseIssue(
                code="fetch_failed",
                phase="fetch",
                severity="error",
                message=" ",
            )

        with self.assertRaises(ValueError):
            ParseIssue(
                code="fetch_failed",
                phase="fetch",
                severity="error",
                message="bad",
                source_ref=" ",
            )

        with self.assertRaises(ValueError):
            ParseIssue(
                code="fetch_failed",
                phase=ParsePhase.FETCH,
                severity=ParseSeverity.ERROR,
                message="bad",
                source_ref=" ",
            )

    def test_fetch_success_preserves_source_metadata_and_utc_timestamp(
        self,
    ) -> None:
        from events.sources import SourceRequest
        from events.sources.framework import (
            MAX_REDIRECTS,
            _RedirectHandler,
            fetch,
        )

        request = SourceRequest(
            source_name="example_source",
            requested_url="https://example.com/feed",
            headers={"accept": "text/html"},
        )

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.headers = Mock()
        response.headers.items.return_value = [("content-type", "text/html")]
        response.headers.get_content_type.return_value = "text/html"
        response.read.return_value = b"<html></html>"
        response.getcode.return_value = 200
        response.geturl.return_value = "https://example.com/final"

        opener = Mock()
        opener.open.return_value = response

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            document = fetch(request)

        self.assertEqual("example_source", document.source_name)
        self.assertEqual("https://example.com/feed", document.requested_url)
        self.assertEqual("https://example.com/final", document.fetched_url)
        self.assertEqual(0, document.fetched_at.utcoffset().total_seconds())
        self.assertEqual(MAX_REDIRECTS, _RedirectHandler.max_redirections)
        self.assertEqual(MAX_REDIRECTS, _RedirectHandler.max_repeats)

    def test_collect_classifies_redirect_http_error_as_fetch_failed(
        self,
    ) -> None:
        from events.sources import SourceRequest, collect
        from events.sources.framework import fetch

        @dataclass
        class ExampleAdapter:
            source_name: str = "example_source"
            default_tz: ZoneInfo | None = None

            def build_request(self):
                return SourceRequest(
                    source_name=self.source_name,
                    requested_url="https://example.com/feed",
                )

            def parse(self, source_document):
                raise AssertionError("parse should not run")

        redirect_error = HTTPError(
            url="https://example.com/feed",
            code=302,
            msg="Found",
            hdrs=None,
            fp=BytesIO(),
        )
        opener = Mock()
        opener.open.side_effect = redirect_error

        with patch(
            "events.sources.framework.build_opener", return_value=opener
        ):
            result = collect(ExampleAdapter(), fetcher=fetch)

        self.assertEqual("fetch_failed", result.issues[0].code)
        redirect_error.close()


if __name__ == "__main__":
    unittest.main()
