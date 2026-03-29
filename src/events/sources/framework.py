from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import HTTPRedirectHandler
from urllib.request import build_opener

from events.sources.models import ParseIssue
from events.sources.models import ParsePhase
from events.sources.models import ParseResult
from events.sources.models import ParseSeverity
from events.sources.models import SourceDocument
from events.sources.models import SourceRequest


if TYPE_CHECKING:
    from events.sources.models import SourceAdapter


FETCH_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 10
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


class _RedirectHandler(HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS


def _error_message(error: Exception, default: str) -> str:
    return str(error).strip() or default


def _issue(
    *,
    code: str,
    phase: ParsePhase,
    severity: ParseSeverity,
    message: str,
    source_ref: str | None = None,
) -> ParseIssue:
    return ParseIssue(
        code=code,
        phase=phase,
        severity=severity,
        message=message,
        source_ref=source_ref,
    )


def _response_headers(headers: Any) -> dict[str, str] | None:
    if not headers:
        return None
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not key.strip() or not value.strip():
            continue
        normalized[key] = value
    return normalized or None


def _decode_response_body(body: bytes, headers: Any) -> str:
    if not body:
        return ""
    charset = None
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()
    if not isinstance(charset, str) or not charset:
        charset = "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch(request: SourceRequest) -> SourceDocument:
    http_request = Request(
        url=request.requested_url,
        headers=dict(request.headers or {}),
    )
    try:
        opener = build_opener(_RedirectHandler)
        with opener.open(http_request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            headers = _response_headers(response.headers)
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=response.geturl(),
                content=_decode_response_body(response.read(), response.headers),
                content_type=response.headers.get_content_type(),
                status_code=response.getcode(),
                headers=headers,
                fetched_at=datetime.now(tz=UTC),
            )
    except HTTPError as error:
        if error.code in REDIRECT_STATUS_CODES:
            error.close()
            raise
        try:
            headers = _response_headers(error.headers)
            content = _decode_response_body(error.read(), error.headers) if error.fp is not None else ""
            return SourceDocument(
                source_name=request.source_name,
                requested_url=request.requested_url,
                fetched_url=error.geturl(),
                content=content,
                content_type=error.headers.get_content_type() if error.headers else None,
                status_code=error.code,
                headers=headers,
                fetched_at=datetime.now(tz=UTC),
            )
        finally:
            error.close()


def collect(
    adapter: SourceAdapter,
    *,
    fetcher: Any = fetch,
) -> ParseResult:
    try:
        request = adapter.build_request()
    except Exception as error:  # noqa: BLE001
        return ParseResult(
            candidates=(),
            issues=(
                _issue(
                    code="invalid_source_request",
                    phase=ParsePhase.FETCH,
                    severity=ParseSeverity.ERROR,
                    message=_error_message(error, "Failed to build source request"),
                ),
            ),
        )

    try:
        if not isinstance(request, SourceRequest):
            raise ValueError("build_request must return SourceRequest")
        if request.source_name != adapter.source_name:
            raise ValueError("request source_name must match adapter source_name")
        SourceRequest(
            source_name=request.source_name,
            requested_url=request.requested_url,
            headers=request.headers,
        )
    except Exception as error:  # noqa: BLE001
        return ParseResult(
            candidates=(),
            issues=(
                _issue(
                    code="invalid_source_request",
                    phase=ParsePhase.FETCH,
                    severity=ParseSeverity.ERROR,
                    message=_error_message(error, "Source request is invalid"),
                ),
            ),
        )

    try:
        source_document = fetcher(request)
        if not isinstance(source_document, SourceDocument):
            raise ValueError("fetcher must return SourceDocument")
        if source_document.source_name != request.source_name:
            raise ValueError("source_document source_name must match request source_name")
    except Exception as error:  # noqa: BLE001
        return ParseResult(
            candidates=(),
            issues=(
                _issue(
                    code="fetch_failed",
                    phase=ParsePhase.FETCH,
                    severity=ParseSeverity.ERROR,
                    message=_error_message(error, "Fetch failed"),
                ),
            ),
        )

    if source_document.status_code < 200 or source_document.status_code >= 300:
        return ParseResult(
            candidates=(),
            issues=(
                _issue(
                    code="http_non_2xx",
                    phase=ParsePhase.FETCH,
                    severity=ParseSeverity.ERROR,
                    message=f"Received HTTP {source_document.status_code}",
                    source_ref=source_document.fetched_url,
                ),
            ),
        )

    try:
        parse_result = adapter.parse(source_document)
        if not isinstance(parse_result, ParseResult):
            raise ValueError("parse must return ParseResult")
        for candidate in parse_result.candidates:
            if candidate.source_name != source_document.source_name:
                raise ValueError("candidate source_name must match source_document source_name")
        return parse_result
    except Exception as error:  # noqa: BLE001
        return ParseResult(
            candidates=(),
            issues=(
                _issue(
                    code="unexpected_parse_exception",
                    phase=ParsePhase.PARSE,
                    severity=ParseSeverity.ERROR,
                    message=_error_message(error, "Unexpected parse exception"),
                    source_ref=source_document.fetched_url,
                ),
            ),
        )
