from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re
import unicodedata
from collections.abc import Callable

from .models import NewsItem, canonical_url


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def _similar_text(left: str, right: str) -> bool:
    normalized_left = normalize(left)
    normalized_right = normalize(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    left_words = set(re.findall(r"\w+", normalized_left))
    right_words = set(re.findall(r"\w+", normalized_right))
    if min(len(left_words), len(right_words)) < 4:
        return False
    overlap = len(left_words & right_words) / min(len(left_words), len(right_words))
    return overlap >= 0.85 and SequenceMatcher(
        None, normalized_left, normalized_right
    ).ratio() >= 0.85


def is_duplicate(candidate: NewsItem, existing: NewsItem) -> bool:
    if candidate.url and existing.url:
        if canonical_url(candidate.url) == canonical_url(existing.url):
            return True
    return _similar_text(candidate.title, existing.title) or _similar_text(
        candidate.summary, existing.summary
    )


def curate(
    items: list[NewsItem],
    keywords: list[str],
    window_hours: int,
    seen: Callable[[str], bool],
    seen_item: Callable[[NewsItem], bool] | None = None,
) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    normalized_keywords = [normalize(keyword) for keyword in keywords]
    accepted: list[NewsItem] = []
    identities: set[str] = set()

    for item in items:
        if item.published_at is None:
            continue
        if item.published_at < cutoff:
            continue
        haystack = normalize(f"{item.title} {item.summary}")
        matches = [keyword for keyword in normalized_keywords if keyword in haystack]
        if not matches:
            continue
        if seen(item.identity) or (seen_item is not None and seen_item(item)):
            continue
        if item.identity in identities or any(
            is_duplicate(item, existing) for existing in accepted
        ):
            continue
        item.keywords = matches
        identities.add(item.identity)
        accepted.append(item)

    return sorted(
        accepted,
        key=lambda item: item.published_at,
        reverse=True,
    )
