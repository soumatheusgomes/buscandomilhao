from datetime import datetime, timezone

from shorts.curator import curate
from shorts.models import NewsItem
from shorts.storage import Storage


def article(title: str, url: str, summary: str = "") -> NewsItem:
    return NewsItem(
        title=title,
        url=url,
        source="Receita Federal",
        published_at=datetime.now(timezone.utc),
        summary=summary,
    )


def test_mesma_url_publicada_nao_e_selecionada_novamente():
    published = article("CBS: novas regras", "https://example.com/noticia")

    assert curate(
        [published],
        ["CBS"],
        24,
        lambda identity: identity == published.identity,
    ) == []


def test_parametros_de_rastreamento_nao_republicam_noticia():
    published = article("CBS: novas regras", "https://example.com/noticia")
    tracked_url = article(
        "CBS: novas regras atualizadas",
        "https://example.com/noticia?utm_source=boletim&utm_campaign=teste",
    )
    storage = Storage(":memory:")
    storage.mark_seen(
        published.identity,
        published.title,
        published.url,
        published.source,
        published.published_at.isoformat(),
    )
    result = curate(
        [tracked_url],
        ["CBS"],
        24,
        storage.seen_identity,
        storage.seen_item,
    )
    storage.close()

    assert result == []


def test_titulos_similares_de_fontes_diferentes_sao_deduplicados():
    articles = [
        article(
            "Comite gestor detalha regras de apuracao assistida da CBS",
            "https://migalhas.com.br/noticia-1",
        ),
        article(
            "Comite gestor detalha regras da apuracao assistida para CBS",
            "https://jota.info/noticia-2",
        ),
    ]

    assert len(curate(articles, ["CBS"], 24, lambda _identity: False)) == 1


def test_titulos_apenas_parecidos_mas_com_fatos_distintos_sao_preservados():
    articles = [
        article(
            "CBS define calendario de apuracao para empresas",
            "https://example.com/calendario",
        ),
        article(
            "CBS anuncia novas aliquotas para setores produtivos",
            "https://example.com/aliquotas",
        ),
    ]

    assert len(curate(articles, ["CBS"], 24, lambda _identity: False)) == 2


def test_historico_sqlite_persiste_apos_reabrir_conexao(tmp_path):
    database_path = tmp_path / "historico.sqlite3"
    first_connection = Storage(database_path)
    first_connection.mark_seen(
        "https://example.com/noticia",
        "CBS: novas regras",
        "https://example.com/noticia",
        "Receita Federal",
        "2026-11-25T15:00:00+00:00",
    )
    first_connection.close()
    reopened = Storage(database_path)
    is_seen = reopened.seen_identity("https://example.com/noticia")
    reopened.close()

    assert is_seen


def test_noticia_semelhante_a_item_persistido_e_identificada(tmp_path):
    storage = Storage(tmp_path / "historico.sqlite3")
    storage.mark_seen(
        "https://migalhas.com.br/noticia-1",
        "Comite gestor detalha regras de apuracao assistida da CBS",
        "https://migalhas.com.br/noticia-1",
        "Migalhas",
        "2026-11-25T15:00:00+00:00",
    )
    candidate = article(
        "Comite gestor detalha regras da apuracao assistida para CBS",
        "https://jota.info/noticia-2",
    )
    is_seen = storage.seen_item(candidate)
    storage.close()

    assert is_seen
