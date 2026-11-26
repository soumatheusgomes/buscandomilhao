from datetime import datetime, timedelta, timezone

from shorts.curator import curate
from shorts.models import NewsItem


def item(title: str, hours_old: int, url: str = "https://example.com") -> NewsItem:
    return NewsItem(
        title=title,
        url=url,
        source="Receita Federal",
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
    )


def test_curates_only_matching_recent_items():
    seen = lambda identity: False
    items = [
        item("Receita publica regra da CBS", 2),
        item("Campeonato anuncia patrocinio", 2),
        item("Publicacao antiga sobre IBS", 30),
    ]
    result = curate(items, ["CBS", "IBS", "LC 214"], 24, seen)
    assert [news.title for news in result] == ["Receita publica regra da CBS"]
    assert result[0].keywords == ["cbs"]


def test_deduplicates_seen_and_url():
    news = item("LC 214 esclarece reforma tributaria", 1, "https://example.com/a")
    seen = lambda identity: identity == news.identity
    assert curate([news], ["reforma tributaria"], 24, seen) == []
