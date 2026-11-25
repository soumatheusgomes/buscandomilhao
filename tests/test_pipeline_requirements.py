from datetime import datetime, timezone

import shorts.pipeline as pipeline
from shorts.models import NewsItem
from shorts.storage import Storage


def valid_news() -> NewsItem:
    return NewsItem(
        title="CBS publica novas regras da reforma tributaria",
        url="https://example.com/cbs",
        source="Receita Federal",
        published_at=datetime.now(timezone.utc),
        summary="Nova orientacao oficial sobre CBS.",
    )


def configure_pipeline(monkeypatch, tmp_path, items, *, video_created=True, auto_publish=False, upload_status="uploaded"):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "collect", lambda _sources: items)
    monkeypatch.setattr(pipeline, "render_slides", lambda *_args: [])
    monkeypatch.setattr(pipeline, "synthesize", lambda *_args: False)

    def assemble(_slides, _audio, output_path, _duration):
        if video_created:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()
        return video_created

    monkeypatch.setattr(pipeline, "assemble_video", assemble)
    monkeypatch.setattr(pipeline, "credentials_present", lambda: auto_publish)
    monkeypatch.setattr(
        pipeline,
        "upload_short",
        lambda *_args: {"status": upload_status, "video_id": "video-id", "video_url": "https://youtube.com/shorts/video-id"},
    )
    config = {
        "news": {"sources": [], "keywords": ["CBS"], "window_hours": 24},
        "video": {"duration_seconds": 45},
        "publish": {
            "auto_publish": auto_publish,
            "max_daily_uploads": 2,
            "youtube_quota_upload_cost": 1600,
        },
    }
    return config


def test_pipeline_seleciona_conteudo_educativo_sem_noticia_valida(monkeypatch, tmp_path):
    config = configure_pipeline(monkeypatch, tmp_path, [])

    result = pipeline.run(config, "07:00")

    assert result["kind"] == "education"


def test_pipeline_prioriza_noticia_valida_sobre_conteudo_educativo(monkeypatch, tmp_path):
    config = configure_pipeline(monkeypatch, tmp_path, [valid_news()])

    result = pipeline.run(config, "07:00")

    assert result["kind"] == "news"


def test_noticia_so_e_registrada_apos_video_de_revisao_gerado(monkeypatch, tmp_path):
    item = valid_news()
    config = configure_pipeline(monkeypatch, tmp_path, [item], video_created=True)

    pipeline.run(config, "07:00")
    storage = Storage()
    is_seen = storage.seen_identity(item.identity)
    storage.close()

    assert is_seen


def test_noticia_nao_e_registrada_quando_video_de_revisao_falha(monkeypatch, tmp_path):
    item = valid_news()
    config = configure_pipeline(monkeypatch, tmp_path, [item], video_created=False)

    pipeline.run(config, "07:00")
    storage = Storage()
    is_seen = storage.seen_identity(item.identity)
    storage.close()

    assert not is_seen


def test_noticia_so_e_registrada_apos_upload_bem_sucedido(monkeypatch, tmp_path):
    item = valid_news()
    config = configure_pipeline(
        monkeypatch,
        tmp_path,
        [item],
        auto_publish=True,
        upload_status="uploaded",
    )

    pipeline.run(config, "07:00")
    storage = Storage()
    is_seen = storage.seen_identity(item.identity)
    storage.close()

    assert is_seen


def test_noticia_nao_e_registrada_quando_upload_falha(monkeypatch, tmp_path):
    item = valid_news()
    config = configure_pipeline(
        monkeypatch,
        tmp_path,
        [item],
        auto_publish=True,
        upload_status="failed",
    )

    pipeline.run(config, "07:00")
    storage = Storage()
    is_seen = storage.seen_identity(item.identity)
    storage.close()

    assert not is_seen
