from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return url.strip().rstrip("/").casefold()
    hostname = (parts.hostname or "").casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    port = parts.port
    netloc = hostname if port is None else f"{hostname}:{port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme.casefold() or "https", netloc, parts.path.rstrip("/"), urlencode(query), "")
    )


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    source: str
    published_at: datetime | None
    summary: str = ""
    keywords: list[str] = field(default_factory=list)

    @property
    def identity(self) -> str:
        return canonical_url(self.url) if self.url else self.title.casefold().strip()
