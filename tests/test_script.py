from datetime import datetime, timezone

from shorts.models import NewsItem
from shorts.script import news_script


def test_news_script_has_source_and_disclaimer():
    item = NewsItem(
        title="Nova regra da reforma tributaria",
        url="https://www.gov.br/receitafederal",
        source="Receita Federal",
        published_at=datetime.now(timezone.utc),
    )
    script = news_script(item)
    assert "conte seu contador" not in script.lower()
    assert "Fonte: Receita Federal" in script
    assert "consulte seu contador" in script
    assert item.url in script
