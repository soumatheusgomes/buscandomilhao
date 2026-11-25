from datetime import datetime as RealDateTime, timedelta, timezone
from types import SimpleNamespace

import shorts.curator as curator
from shorts.collector import collect
from shorts.curator import curate
from shorts.models import NewsItem


FIXED_NOW = RealDateTime(2026, 11, 25, 16, 0, tzinfo=timezone.utc)
KEYWORDS = [
    "reforma tributaria",
    "CBS",
    "IBS",
    "Imposto Seletivo",
    "LC 214",
    "EC 132",
]


class FrozenDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW if tz else FIXED_NOW.replace(tzinfo=None)


def news(title: str, published_at, *, url="https://example.com/noticia", summary=""):
    return NewsItem(
        title=title,
        url=url,
        source="Receita Federal",
        published_at=published_at,
        summary=summary,
    )


def test_descarta_noticia_com_mais_de_24_horas(monkeypatch):
    monkeypatch.setattr(curator, "datetime", FrozenDateTime)
    old_news = news("CBS terá nova regra", FIXED_NOW - timedelta(hours=24, seconds=1))

    assert curate([old_news], KEYWORDS, 24, lambda _identity: False) == []


def test_inclui_noticia_exatamente_no_limite_de_24_horas(monkeypatch):
    # A janela é inclusiva: uma notícia exatamente no limite não é considerada antiga.
    monkeypatch.setattr(curator, "datetime", FrozenDateTime)
    boundary_news = news("Regra da CBS publicada", FIXED_NOW - timedelta(hours=24))

    assert curate([boundary_news], KEYWORDS, 24, lambda _identity: False) == [boundary_news]


def test_descarta_noticia_sem_data():
    undated = news("Reforma tributaria: nova regra", None)

    assert curate([undated], KEYWORDS, 24, lambda _identity: False) == []


def test_descarta_noticia_sem_palavra_chave():
    unrelated = news("Banco anuncia novo aplicativo", FIXED_NOW)

    assert curate([unrelated], KEYWORDS, 24, lambda _identity: False) == []


def test_palavras_chave_ignoram_maiusculas_e_acentos():
    accented = news("Reforma Tributária altera regras", FIXED_NOW)
    unaccented = news(
        "reforma tributaria atualiza regras",
        FIXED_NOW,
        url="https://example.com/outra",
    )

    assert len(curate([accented, unaccented], KEYWORDS, 24, lambda _identity: False)) == 2


def test_coleta_rejeita_feed_com_erro_e_feed_vazio_sem_perder_demais_fontes(monkeypatch):
    def fake_parse(url):
        if url.endswith("/erro"):
            raise OSError("feed indisponivel")
        if url.endswith("/vazio"):
            return SimpleNamespace(entries=[])
        return SimpleNamespace(
            entries=[
                SimpleNamespace(
                    title="CBS publicada",
                    link="https://example.com/cbs",
                    published="Wed, 25 Nov 2026 15:00:00 GMT",
                    summary="Atualizacao oficial",
                )
            ]
        )

    monkeypatch.setattr("shorts.collector.feedparser.parse", fake_parse)
    sources = [
        {"name": "Erro", "url": "https://example.com/erro"},
        {"name": "Vazio", "url": "https://example.com/vazio"},
        {"name": "Receita Federal", "url": "https://example.com/bom"},
    ]

    assert [item.title for item in collect(sources)] == ["CBS publicada"]


def test_feed_sem_data_produz_noticia_descartada(monkeypatch):
    monkeypatch.setattr(
        "shorts.collector.feedparser.parse",
        lambda _url: SimpleNamespace(
            entries=[
                SimpleNamespace(
                    title="Reforma tributaria: nova regra",
                    link="https://example.com/sem-data",
                    summary="",
                )
            ]
        ),
    )
    collected = collect([{"name": "Agencia Brasil", "url": "https://example.com/feed"}])

    assert curate(collected, KEYWORDS, 24, lambda _identity: False) == []

