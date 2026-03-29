from __future__ import annotations

from urllib.parse import SplitResult, urlsplit


def require_absolute_url(url: str) -> SplitResult:
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise ValueError("url must be absolute and include a host")
    return parts
