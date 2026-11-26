from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import feedparser

from .models import NewsItem


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def collect(sources: Iterable[dict[str, object]]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for source in sources:
        name = str(source["name"])
        url = str(source["url"])
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for entry in getattr(feed, "entries", []):
            published = _parse_date(
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
            )
            items.append(
                NewsItem(
                    title=getattr(entry, "title", "").strip(),
                    url=getattr(entry, "link", "").strip(),
                    source=name,
                    published_at=published,
                    summary=getattr(entry, "summary", "").strip(),
                )
            )
    return items
